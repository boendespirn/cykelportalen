"""
historical_results_agent.py

Scraper endelige GC-klassementer + etapevindere fra PCS for historiske løb.
Gemmer i classifications (gc) og results (etapevinder position=1).

Krav: Kør historical_race_agent.py først for at oprette løb i DB.

Kør:
  python historical_results_agent.py                          # Alle uden resultater
  python historical_results_agent.py --race tour-de-france-2024
  python historical_results_agent.py --year 2024              # Alle løb fra 2024
  python historical_results_agent.py --force                  # Overskrivb eksisterende
"""

import io
import os
import re
import sys
import time
import argparse
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

AUTH  = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
DB    = {**AUTH, "Content-Type": "application/json", "Prefer": "return=minimal"}

DELAY = 2.0   # sekunder mellem PCS-sideindlæsninger
TOP_N = 20    # gem top N i GC-klassementet

MONTHS_EN = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


# ── Rider lookup ──────────────────────────────────────────────────────────────

def get_rider_id(pcs_slug: str, name: str) -> str | None:
    """Slå rytter op i DB — prøv PCS-slug, derefter omvendt slug, derefter navn."""
    # Direkte PCS slug
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/riders?slug=eq.{pcs_slug}&select=id&limit=1",
        headers=AUTH,
    )
    data = res.json()
    if res.ok and data:
        return data[0]["id"]

    # PCS: firstname-lastname → DB: lastname-firstname
    parts = pcs_slug.split("-")
    if len(parts) >= 2:
        db_slug = "-".join(parts[1:] + [parts[0]])
        res2 = requests.get(
            f"{SUPABASE_URL}/rest/v1/riders?slug=eq.{db_slug}&select=id&limit=1",
            headers=AUTH,
        )
        data2 = res2.json()
        if res2.ok and data2:
            return data2[0]["id"]

    # Navn-fallback
    clean = requests.utils.quote(name.strip().upper())
    res3 = requests.get(
        f"{SUPABASE_URL}/rest/v1/riders?name=ilike.{clean}&select=id&limit=1",
        headers=AUTH,
    )
    data3 = res3.json()
    return data3[0]["id"] if res3.ok and data3 else None


# ── Supabase helpers ──────────────────────────────────────────────────────────

def get_historical_races(year: int | None, race_slug: str | None) -> list:
    if race_slug:
        url = (
            f"{SUPABASE_URL}/rest/v1/races"
            f"?slug=eq.{race_slug}"
            f"&select=id,name,slug,pcs_url,start_date,end_date,race_type"
            f"&limit=1"
        )
    elif year:
        url = (
            f"{SUPABASE_URL}/rest/v1/races"
            f"?start_date=gte.{year}-01-01&start_date=lt.{year+1}-01-01"
            f"&select=id,name,slug,pcs_url,start_date,end_date,race_type"
            f"&order=start_date.asc&limit=200"
        )
    else:
        url = (
            f"{SUPABASE_URL}/rest/v1/races"
            f"?start_date=lt.2026-01-01"
            f"&select=id,name,slug,pcs_url,start_date,end_date,race_type"
            f"&order=start_date.asc&limit=1000"
        )
    res = requests.get(url, headers=AUTH)
    return res.json() if res.ok and isinstance(res.json(), list) else []


def has_gc(race_id: str) -> bool:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/classifications"
        f"?race_id=eq.{race_id}&classification_type=eq.gc&limit=1",
        headers=AUTH,
    )
    data = res.json()
    return bool(res.ok and data)


def get_or_create_stage(race_id: str, sn: int, date: str | None = None) -> str | None:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages"
        f"?race_id=eq.{race_id}&stage_number=eq.{sn}&select=id&limit=1",
        headers=AUTH,
    )
    data = res.json()
    if res.ok and data:
        return data[0]["id"]

    payload = {
        "race_id":      race_id,
        "stage_number": sn,
        "name":         "Prolog" if sn == 0 else f"Etape {sn}",
        "source":       "pcs_historical",
    }
    if date:
        payload["date"] = date

    cr = requests.post(
        f"{SUPABASE_URL}/rest/v1/stages",
        json=payload,
        headers={**DB, "Prefer": "resolution=ignore-duplicates,return=representation"},
    )
    if cr.ok and cr.text and cr.text not in ("[]", ""):
        rows = cr.json()
        if isinstance(rows, list) and rows:
            return rows[0]["id"]
    return None


def get_max_stage(race_id: str) -> int:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages"
        f"?race_id=eq.{race_id}&select=stage_number&order=stage_number.desc&limit=1",
        headers=AUTH,
    )
    data = res.json()
    return data[0]["stage_number"] if res.ok and data else 1


def save_gc(race_id: str, after_stage: int, standings: list) -> int:
    # Slet evt. eksisterende GC for dette løb
    requests.delete(
        f"{SUPABASE_URL}/rest/v1/classifications"
        f"?race_id=eq.{race_id}&classification_type=eq.gc",
        headers=DB,
    )
    rows, matched = [], 0
    for e in standings:
        rid = get_rider_id(e["pcs_slug"], e["name"])
        if not rid:
            continue
        matched += 1
        rows.append({
            "race_id":             race_id,
            "after_stage_number":  after_stage,
            "classification_type": "gc",
            "rider_id":            rid,
            "position":            e["position"],
            "time_gap_seconds":    e.get("time_gap_seconds", 0),
        })
    if rows:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/classifications",
            json=rows,
            headers={**DB, "Prefer": "resolution=ignore-duplicates,return=minimal"},
        )
    return matched


def save_stage_winner(race_id: str, stage_id: str, pcs_slug: str, name: str) -> bool:
    rid = get_rider_id(pcs_slug, name)
    if not rid:
        return False
    # Slet eksisterende vinderpost for denne etape
    requests.delete(
        f"{SUPABASE_URL}/rest/v1/results"
        f"?race_id=eq.{race_id}&stage_id=eq.{stage_id}&position=eq.1",
        headers=DB,
    )
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/results",
        json=[{"race_id": race_id, "stage_id": stage_id, "rider_id": rid, "position": 1}],
        headers={**DB, "Prefer": "resolution=ignore-duplicates,return=minimal"},
    )
    return r.ok


# ── PCS scraping ──────────────────────────────────────────────────────────────

def parse_time_to_seconds(s: str) -> int | None:
    s = s.strip().lstrip("+")
    parts = s.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        pass
    return None


def scrape_gc(html: str) -> list:
    """
    Parse GC-tabel fra PCS /gc eller /result side.
    Returnerer [{position, pcs_slug, name, time_gap_seconds}].
    """
    soup = BeautifulSoup(html, "html.parser")
    standings = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 3:
            continue

        # Tjek at første datarække har position 1
        is_gc = False
        for row in rows[1:5]:
            tds = row.find_all("td", recursive=False)
            try:
                if int(tds[0].get_text(strip=True)) == 1:
                    is_gc = True
                    break
            except (ValueError, IndexError):
                pass
        if not is_gc:
            continue

        for row in rows[1:TOP_N + 1]:
            tds = row.find_all("td", recursive=False)
            try:
                pos = int(tds[0].get_text(strip=True))
            except (ValueError, IndexError):
                continue

            rider_a = row.find("a", href=re.compile(r"^/?rider/"))
            if not rider_a:
                continue
            pcs_slug = rider_a["href"].lstrip("/").replace("rider/", "").strip("/")
            name = rider_a.get_text(separator=" ", strip=True).upper()

            # Tidsgab
            time_td = row.find("td", class_="time")
            gap = 0
            if time_td:
                raw = (time_td.find("font") or time_td).get_text(strip=True)
                # PCS duplikerer tekst via skjult span: "1:561:56" → "1:56"
                m = re.match(r"(\d+:\d+(?::\d+)?)", raw)
                if m and pos > 1:
                    gap = parse_time_to_seconds(m.group(1)) or 0

            standings.append({
                "position":         pos,
                "pcs_slug":         pcs_slug,
                "name":             name,
                "time_gap_seconds": gap,
            })

        if standings:
            break

    return standings


def scrape_stage_winners(html: str, year: int) -> list:
    """
    Udtræk etapevindere fra PCS løb-oversigtsside.
    Returnerer [{stage_number, pcs_slug, name, date}].
    """
    soup = BeautifulSoup(html, "html.parser")
    seen, winners = set(), []

    stage_re = re.compile(rf"/race/[^/]+/{year}/stage-(\d+)")

    for row in soup.find_all("tr"):
        # Find etape-link
        a_stage = row.find("a", href=stage_re)
        if not a_stage:
            continue
        m = stage_re.search(a_stage["href"])
        if not m:
            continue
        sn = int(m.group(1))
        if sn in seen:
            continue

        # Find vinder-link
        a_rider = row.find("a", href=re.compile(r"^/?rider/"))
        if not a_rider:
            continue
        pcs_slug = a_rider["href"].lstrip("/").replace("rider/", "").strip("/")
        name = a_rider.get_text(separator=" ", strip=True).upper()

        # Dato
        date_str = None
        row_text = row.get_text(" ")
        dm = re.search(
            r"(\d{1,2})\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
            r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
            r"Nov(?:ember)?|Dec(?:ember)?)",
            row_text, re.IGNORECASE,
        )
        if dm:
            day = int(dm.group(1))
            mon_key = dm.group(2).lower()[:3]
            mon = MONTHS_EN.get(mon_key, 0)
            if mon:
                date_str = f"{year}-{mon:02d}-{day:02d}"

        seen.add(sn)
        winners.append({
            "stage_number": sn,
            "pcs_slug":     pcs_slug,
            "name":         name,
            "date":         date_str,
        })

    return sorted(winners, key=lambda x: x["stage_number"])


def process_race(race: dict, pw, force: bool) -> dict:
    """Behandl ét historisk løb: scraper GC + etapevindere fra PCS."""
    race_id = race["id"]
    pcs_url = (race.get("pcs_url") or "").rstrip("/")
    year    = int(race["start_date"][:4])
    is_one_day = race.get("race_type") == "one_day"

    if not pcs_url:
        print(f"  Ingen pcs_url — springer over")
        return {"gc": 0, "wins": 0, "skipped": True}

    if not force and has_gc(race_id):
        print(f"  GC findes allerede (brug --force for at overskrive)")
        return {"gc": 0, "wins": 0, "skipped": True}

    result = {"gc": 0, "wins": 0, "skipped": False}

    # ── GC ────────────────────────────────────────────────────────────────────
    # Enkeltdagsløb bruger /result; etapeløb bruger /gc
    gc_url = f"{pcs_url}/result" if is_one_day else f"{pcs_url}/gc"
    print(f"  GC: {gc_url}")

    pw.goto(gc_url, wait_until="networkidle", timeout=35_000)
    time.sleep(DELAY)
    gc_html = pw.content()
    standings = scrape_gc(gc_html)

    if not standings and not is_one_day:
        # Fallback: prøv /result
        result_url = f"{pcs_url}/result"
        print(f"  GC tom — prøver {result_url}")
        pw.goto(result_url, wait_until="networkidle", timeout=35_000)
        time.sleep(DELAY)
        standings = scrape_gc(pw.content())

    if standings:
        after_stage = get_max_stage(race_id) if not is_one_day else 1
        if after_stage == 0:
            after_stage = 1
        matched = save_gc(race_id, after_stage, standings)
        result["gc"] = matched
        winner = standings[0]["name"].split()[-1] if standings else "?"
        print(f"  -> GC: {len(standings)} fundet, {matched} matchet (vinder: {winner})")
    else:
        print(f"  -> GC: ingen data")

    # ── Etapevindere (kun etapeløb) ───────────────────────────────────────────
    if not is_one_day:
        print(f"  Etapevindere: {pcs_url}")
        pw.goto(pcs_url, wait_until="networkidle", timeout=35_000)
        time.sleep(DELAY)
        overview_html = pw.content()

        winners = scrape_stage_winners(overview_html, year)
        stage_wins = 0
        for w in winners:
            sid = get_or_create_stage(race_id, w["stage_number"], w.get("date"))
            if sid and save_stage_winner(race_id, sid, w["pcs_slug"], w["name"]):
                stage_wins += 1
        result["wins"] = stage_wins
        if stage_wins:
            print(f"  -> {stage_wins} etapevindere gemt")

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def run(race_slug: str | None, year: int | None, force: bool) -> None:
    races = get_historical_races(year, race_slug)

    print(f"historical_results_agent.py")
    print(f"Løb at behandle: {len(races)}")
    if not races:
        print("Ingen løb fundet — kør historical_race_agent.py først")
        return
    print()

    total_gc = total_wins = total_skipped = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pw = browser.new_page()
        pw.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

        for i, race in enumerate(races, 1):
            print(f"[{i}/{len(races)}] {race['name']} ({race['start_date'][:4]})")
            res = process_race(race, pw, force)

            if res["skipped"]:
                total_skipped += 1
            else:
                total_gc   += res["gc"]
                total_wins += res["wins"]

            time.sleep(DELAY)

        browser.close()

    print(f"\nFærdig:")
    print(f"  GC-poster gemt:     {total_gc}")
    print(f"  Etapevindere gemt:  {total_wins}")
    print(f"  Sprunget over:      {total_skipped}")
    print()
    print("Kør nu: se resultater på klassementet.dk/riders/[slug]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--race", help="Enkelt løb-slug (fx tour-de-france-2024)")
    grp.add_argument("--year", type=int, help="Alle løb fra ét år")
    parser.add_argument("--force", action="store_true", help="Overskrivb eksisterende data")
    args = parser.parse_args()
    run(args.race, args.year, args.force)
