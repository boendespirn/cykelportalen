"""
results_agent.py
Scraper etaperesultater og GC-klassement fra PCS for igangvaerende loeb.
Gemmer i startlists-tabellen (status, dnf_stage_number) og opdaterer
gc_position / gc_time_gap i en separat klassementer-tabel hvis den eksisterer.

Korer: python results_agent.py
       python results_agent.py --race giro-d-italia-2026
       python results_agent.py --race giro-d-italia-2026 --stage 15
"""

import os
import re
import sys
import time
import argparse
import requests
from datetime import date
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
DB   = {**AUTH, "Content-Type": "application/json", "Prefer": "return=minimal"}

DELAY = 1.5


# ── Supabase helpers ──────────────────────────────────────────────────────────

def get_ongoing_races() -> list[dict]:
    today = date.today().isoformat()
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races"
        f"?start_date=lte.{today}&end_date=gte.{today}"
        f"&select=id,name,slug,pcs_url"
        f"&order=start_date.desc&limit=5",
        headers=AUTH,
    )
    return res.json() if res.ok else []


def get_race(slug: str) -> dict | None:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?slug=eq.{slug}&select=id,name,slug,pcs_url&limit=1",
        headers=AUTH,
    )
    data = res.json()
    return data[0] if res.ok and data else None


def get_latest_finished_stage(race_id: str) -> dict | None:
    today = date.today().isoformat()
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages"
        f"?race_id=eq.{race_id}&date=lte.{today}"
        f"&select=id,stage_number,pcs_stage_url,date"
        f"&order=stage_number.desc&limit=1",
        headers=AUTH,
    )
    data = res.json()
    return data[0] if res.ok and data else None


def get_rider_id_by_slug(slug: str) -> str | None:
    # Prøv direkte slug
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/riders?slug=eq.{slug}&select=id&limit=1",
        headers=AUTH,
    )
    data = res.json()
    if res.ok and data:
        return data[0]["id"]
    # PCS bruger firstname-[middlename-]lastname, DB bruger lastname-[middlename-]firstname
    # Flyt første ord til slutningen: "ben-o-connor" → "o-connor-ben"
    parts = slug.split("-")
    if len(parts) >= 2:
        db_slug = "-".join(parts[1:] + [parts[0]])
        res2 = requests.get(
            f"{SUPABASE_URL}/rest/v1/riders?slug=eq.{db_slug}&select=id&limit=1",
            headers=AUTH,
        )
        data2 = res2.json()
        if res2.ok and data2:
            return data2[0]["id"]
    return None


def get_rider_id_by_name(name: str) -> str | None:
    clean = name.strip().upper()
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/riders?name=ilike.{requests.utils.quote(clean)}&select=id&limit=1",
        headers=AUTH,
    )
    data = res.json()
    return data[0]["id"] if res.ok and data else None


def get_rider_id(slug: str, name: str) -> str | None:
    """Prøv slug-opslag først, fallback til navn."""
    return get_rider_id_by_slug(slug) or get_rider_id_by_name(name)


def mark_dnf(race_id: str, rider: dict, stage_number: int) -> None:
    rid = get_rider_id(rider["slug"], rider["name"])
    if not rid:
        return
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/startlists?race_id=eq.{race_id}&rider_id=eq.{rid}",
        json={"status": "DNF", "dnf_stage_number": stage_number},
        headers=DB,
    )


def upsert_classification(race_id: str, stage_number: int, classif_type: str, standings: list[dict]) -> None:
    """Gemmer klassement i classifications-tabellen (gc, points, mountains, youth)."""
    requests.delete(
        f"{SUPABASE_URL}/rest/v1/classifications"
        f"?race_id=eq.{race_id}&after_stage_number=eq.{stage_number}&classification_type=eq.{classif_type}",
        headers=DB,
    )
    rows = []
    for entry in standings:
        rid = get_rider_id(entry["slug"], entry["name"])
        if not rid:
            continue
        row = {
            "race_id":             race_id,
            "after_stage_number":  stage_number,
            "classification_type": classif_type,
            "rider_id":            rid,
            "position":            entry.get("position"),
        }
        if "time_gap_seconds" in entry:
            row["time_gap_seconds"] = entry["time_gap_seconds"]
        if "points" in entry:
            row["points"] = entry["points"]
        rows.append(row)
    if rows:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/classifications",
            json=rows,
            headers={**DB, "Prefer": "resolution=ignore-duplicates,return=minimal"},
        )


# ── PCS scraping ──────────────────────────────────────────────────────────────

def parse_time_to_seconds(s: str) -> int | None:
    """'1:23:45' eller '+0:45' → sekunder."""
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


def _parse_pcs_row(row) -> dict | None:
    """Udtræk position, slug og navn fra en PCS tabelrække."""
    tds = row.find_all("td", recursive=False)
    if not tds:
        return None
    try:
        pos = int(tds[0].get_text(strip=True))
    except (ValueError, IndexError):
        return None
    rider_td = row.find("td", class_="ridername")
    if not rider_td:
        return None
    rider_link = rider_td.find("a", href=True)
    if not rider_link:
        return None
    slug = rider_link["href"].replace("rider/", "").strip("/")
    name = rider_link.get_text(separator=" ", strip=True).upper()
    return {"pos": pos, "slug": slug, "name": name}


def _extract_time(td) -> str:
    """Udtræk tid fra PCS td — fjern dublet fra skjult span."""
    if not td:
        return ""
    font = td.find("font")
    raw = font.get_text(strip=True) if font else td.get_text(strip=True)
    # PCS duplikerer tekst via skjult span: "1:561:56" → "1:56"
    m = re.match(r"(\d+:\d+(?::\d+)?)", raw)
    return m.group(1) if m else raw


def scrape_stage_result(pcs_stage_url: str) -> dict:
    """
    Scraper etaperesultat + alle 4 klassementer fra PCS med BeautifulSoup.
    Returnerer: {top10, dnf, gc, points, mountains, youth}
    """
    result = {"top10": [], "dnf": [], "gc": [], "points": [], "mountains": [], "youth": []}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            page.goto(pcs_stage_url, wait_until="networkidle", timeout=25_000)
            time.sleep(2)
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            return result

        # ── Tabel 0: Etaperesultat (sorteret efter etapeplacering) ───────────
        for row in tables[0].find_all("tr")[1:11]:
            parsed = _parse_pcs_row(row)
            if not parsed:
                continue
            time_td = row.find("td", class_="time")
            time_str = ""
            if time_td:
                font = time_td.find("font")
                if font:
                    time_str = font.get_text(strip=True)
            result["top10"].append({
                "position": parsed["pos"],
                "slug":     parsed["slug"],
                "name":     parsed["name"],
                "time":     time_str,
            })

        # ── DNF: rækker i tabel 0 efter DNF-header ───────────────────────────
        in_dnf = False
        for row in tables[0].find_all("tr"):
            cells = row.find_all("td")
            if cells and any("DNF" in c.get_text() for c in cells[:2]):
                in_dnf = True
                continue
            if in_dnf:
                parsed = _parse_pcs_row(row)
                if parsed:
                    result["dnf"].append({"slug": parsed["slug"], "name": parsed["name"]})

        # ── Tabel 1: GC-klassement ────────────────────────────────────────────
        if len(tables) > 1:
            for row in tables[1].find_all("tr")[1:21]:
                parsed = _parse_pcs_row(row)
                if not parsed:
                    continue
                time_str = _extract_time(row.find("td", class_="time"))
                gap = 0 if parsed["pos"] == 1 else (parse_time_to_seconds(time_str) or 0)
                result["gc"].append({
                    "position": parsed["pos"], "slug": parsed["slug"],
                    "name": parsed["name"], "time_gap_seconds": gap,
                })

        # ── Tabel 2: Pointsklassement (pnt-kolonne = td[9]) ──────────────────
        if len(tables) > 2:
            for row in tables[2].find_all("tr")[1:21]:
                parsed = _parse_pcs_row(row)
                if not parsed:
                    continue
                tds = row.find_all("td", recursive=False)
                try:
                    pts = int(tds[9].get_text(strip=True)) if len(tds) > 9 else 0
                except (ValueError, IndexError):
                    pts = 0
                result["points"].append({
                    "position": parsed["pos"], "slug": parsed["slug"],
                    "name": parsed["name"], "points": pts,
                })

        # ── Tabel 6: Bjergklassement (pnt-kolonne = td[9]) ───────────────────
        if len(tables) > 6:
            for row in tables[6].find_all("tr")[1:21]:
                parsed = _parse_pcs_row(row)
                if not parsed:
                    continue
                tds = row.find_all("td", recursive=False)
                try:
                    pts = int(tds[9].get_text(strip=True)) if len(tds) > 9 else 0
                except (ValueError, IndexError):
                    pts = 0
                result["mountains"].append({
                    "position": parsed["pos"], "slug": parsed["slug"],
                    "name": parsed["name"], "points": pts,
                })

        # ── Tabel 7: Ungdomsklassement (time-kolonne = td[9]) ────────────────
        if len(tables) > 7:
            for row in tables[7].find_all("tr")[1:21]:
                parsed = _parse_pcs_row(row)
                if not parsed:
                    continue
                tds = row.find_all("td", recursive=False)
                time_str = _extract_time(tds[9]) if len(tds) > 9 else ""
                gap = 0 if parsed["pos"] == 1 else (parse_time_to_seconds(time_str) or 0)
                result["youth"].append({
                    "position": parsed["pos"], "slug": parsed["slug"],
                    "name": parsed["name"], "time_gap_seconds": gap,
                })

    except Exception as e:
        print(f"  [Scrape fejl: {e}]")

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def process(race_slug: str | None, stage_number: int | None) -> None:
    if race_slug:
        races = [get_race(race_slug)]
        races = [r for r in races if r]
    else:
        races = get_ongoing_races()

    print(f"results_agent.py — {date.today().isoformat()}")
    print(f"Behandler {len(races)} loeb\n")

    for race in races:
        print(f"[{race['name']}]")
        race_id  = race["id"]
        pcs_base = race.get("pcs_url", "")

        if stage_number:
            # Hent specifik etapes URL fra DB
            res = requests.get(
                f"{SUPABASE_URL}/rest/v1/stages"
                f"?race_id=eq.{race_id}&stage_number=eq.{stage_number}"
                f"&select=id,stage_number,pcs_stage_url,date&limit=1",
                headers=AUTH,
            )
            stages = res.json() if res.ok else []
        else:
            stage = get_latest_finished_stage(race_id)
            stages = [stage] if stage else []

        if not stages:
            print("  Ingen etaper at opdatere")
            continue

        for stage in stages:
            sn       = stage["stage_number"]
            pcs_url  = stage.get("pcs_stage_url")

            if not pcs_url:
                # Byg URL fra race-URL
                if pcs_base:
                    pcs_url = f"{pcs_base.rstrip('/')}/stage-{sn}/result"
                else:
                    print(f"  E{sn}: Ingen PCS-URL")
                    continue

            # Tilfoej /result hvis ikke allerede der
            if not pcs_url.endswith("/result"):
                pcs_url = pcs_url.rstrip("/") + "/result"

            print(f"  E{sn}: Scraper {pcs_url}")
            data = scrape_stage_result(pcs_url)

            if data["top10"]:
                print(f"  -> Top 3: " + " | ".join(
                    f"{r['position']}. {r['name'].split()[-1]}" for r in data["top10"][:3]
                ))
            else:
                print("  -> Ingen etaperesultat fundet (muligvis ikke koert endnu)")

            if data["dnf"]:
                print(f"  -> DNF: {', '.join(r['name'] for r in data['dnf'][:5])}")
                for rider in data["dnf"]:
                    mark_dnf(race_id, rider, sn)

            if data["gc"]:
                print(f"  -> GC top3: " + " | ".join(
                    f"{r['position']}. {r['name'].split()[-1]}" for r in data["gc"][:3]
                ))
                upsert_classification(race_id, sn, "gc", data["gc"])

            if data["points"]:
                print(f"  -> Points top3: " + " | ".join(
                    f"{r['position']}. {r['name'].split()[-1]}" for r in data["points"][:3]
                ))
                upsert_classification(race_id, sn, "points", data["points"])

            if data["mountains"]:
                print(f"  -> Bjerge top3: " + " | ".join(
                    f"{r['position']}. {r['name'].split()[-1]}" for r in data["mountains"][:3]
                ))
                upsert_classification(race_id, sn, "mountains", data["mountains"])

            if data["youth"]:
                print(f"  -> Ungdom top3: " + " | ".join(
                    f"{r['position']}. {r['name'].split()[-1]}" for r in data["youth"][:3]
                ))
                upsert_classification(race_id, sn, "youth", data["youth"])

            time.sleep(DELAY)

    print("\nFaerdig.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--race",  help="Loeb-slug (default: alle igangvaerende)", default=None)
    parser.add_argument("--stage", type=int, help="Specifik etape (default: seneste afsluttede)", default=None)
    args = parser.parse_args()
    process(args.race, args.stage)
