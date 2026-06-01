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

DELAY   = 2.5  # sekunder mellem PCS-sideindlæsninger
TOP_N   = 20   # gem top N i GC-klassementet
PCS_BASE = "https://www.procyclingstats.com"

MONTHS_EN = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


# ── Cloudflare-safe session ───────────────────────────────────────────────────

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def _playwright_get_cookies(url: str) -> dict:
    """Brug Playwright én gang til at skaffe cf_clearance cookie."""
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, channel="chrome")
        except Exception:
            browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 800})
        pw = ctx.new_page()
        pw.goto(url, wait_until="domcontentloaded", timeout=45_000)
        for _ in range(25):
            title = pw.title().lower()
            if "øjeblik" not in title and "moment" not in title and "cloudflare" not in title:
                break
            time.sleep(1.5)
        time.sleep(DELAY)
        html = pw.content()
        cookies = {c["name"]: c["value"] for c in ctx.cookies("https://www.procyclingstats.com")}
        ctx.close()
        browser.close()
    return cookies, html


def make_session(seed_url: str) -> tuple:
    """Opret requests.Session med gyldige Cloudflare-cookies. Returnerer (session, seed_html)."""
    print(f"  [Playwright] Henter cookies fra {seed_url}")
    cookies, html = _playwright_get_cookies(seed_url)
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA, "Referer": "https://www.procyclingstats.com/"})
    for name, val in cookies.items():
        sess.cookies.set(name, val, domain="www.procyclingstats.com")
    return sess, html


def fetch(sess: requests.Session, url: str, retries: int = 3) -> str:
    """Hent en PCS-side med requests. Håndterer timeouts og Cloudflare."""
    for attempt in range(retries + 1):
        try:
            r = sess.get(url, timeout=30)
            html = r.text
        except requests.exceptions.Timeout:
            if attempt < retries:
                wait = 5 * (attempt + 1)
                print(f"  [timeout] {url} — venter {wait}s og prøver igen ...")
                time.sleep(wait)
                continue
            print(f"  [timeout] Gav op efter {retries} forsøg: {url}")
            return ""
        except requests.exceptions.RequestException as e:
            print(f"  [fejl] {e}")
            return ""

        soup = BeautifulSoup(html, "html.parser")
        title = (soup.title.get_text() if soup.title else "").lower()
        if "øjeblik" not in title and "moment" not in title and "cloudflare" not in title:
            time.sleep(0.5)
            return html
        if attempt < retries:
            print(f"  [CF] Cloudflare på {url} — fornyer session ...")
            new_cookies, _ = _playwright_get_cookies(url)
            for name, val in new_cookies.items():
                sess.cookies.set(name, val, domain="www.procyclingstats.com")
            time.sleep(DELAY)
    print(f"  [CF] Cloudflare ikke løst for {url}")
    return html


# ── Rider lookup ──────────────────────────────────────────────────────────────

def get_rider_id(pcs_slug: str, name: str) -> str | None:
    """Slå rytter op i DB — prøv PCS-slug, derefter omvendt slug, derefter navn."""
    try:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/riders?slug=eq.{pcs_slug}&select=id&limit=1",
            headers=AUTH, timeout=15,
        )
        data = res.json()
        if res.ok and data:
            return data[0]["id"]

        parts = pcs_slug.split("-")
        if len(parts) >= 2:
            db_slug = "-".join(parts[1:] + [parts[0]])
            res2 = requests.get(
                f"{SUPABASE_URL}/rest/v1/riders?slug=eq.{db_slug}&select=id&limit=1",
                headers=AUTH, timeout=15,
            )
            data2 = res2.json()
            if res2.ok and data2:
                return data2[0]["id"]

        clean = requests.utils.quote(name.strip().upper())
        res3 = requests.get(
            f"{SUPABASE_URL}/rest/v1/riders?name=ilike.{clean}&select=id&limit=1",
            headers=AUTH, timeout=15,
        )
        data3 = res3.json()
        return data3[0]["id"] if res3.ok and data3 else None
    except requests.exceptions.RequestException:
        return None


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
    res = requests.get(url, headers=AUTH, timeout=15)
    return res.json() if res.ok and isinstance(res.json(), list) else []


def has_gc(race_id: str) -> bool:
    try:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/classifications"
            f"?race_id=eq.{race_id}&classification_type=eq.gc&limit=1",
            headers=AUTH, timeout=15,
        )
        data = res.json()
        return bool(res.ok and data)
    except requests.exceptions.RequestException:
        return False


def get_or_create_stage(race_id: str, sn: int, date: str | None = None) -> str | None:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages"
        f"?race_id=eq.{race_id}&stage_number=eq.{sn}&select=id&limit=1",
        headers=AUTH, timeout=15,
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
        timeout=15,
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
        headers=AUTH, timeout=15,
    )
    data = res.json()
    return data[0]["stage_number"] if res.ok and data else 1


def save_gc(race_id: str, after_stage: int, standings: list) -> int:
    # Slet evt. eksisterende GC for dette løb
    requests.delete(
        f"{SUPABASE_URL}/rest/v1/classifications"
        f"?race_id=eq.{race_id}&classification_type=eq.gc",
        headers=DB, timeout=15,
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
            timeout=15,
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
        headers=DB, timeout=15,
    )
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/results",
        json=[{"race_id": race_id, "stage_id": stage_id, "rider_id": rid, "position": 1}],
        headers={**DB, "Prefer": "resolution=ignore-duplicates,return=minimal"},
        timeout=15,
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


def _parse_time_gap(row) -> int:
    """
    Udtræk tidsgab i sekunder fra en tabelrække.
    Prøver class="time" td først, derefter alle td-elementer.
    Bruger ikke-forankret regex da PCS dublerer tekst via skjulte spans.
    """
    # Primær: class="time" td med font-element (PCS-format)
    time_td = row.find("td", class_="time")
    if time_td:
        raw = (time_td.find("font") or time_td).get_text(strip=True).lstrip("+")
        m = re.search(r"(\d+:\d{2}(?::\d{2})?)", raw)
        if m:
            parsed = parse_time_to_seconds(m.group(1)) or 0
            if parsed > 0:
                return parsed

    # Fallback: scan alle td-elementer
    for td in row.find_all("td", recursive=False):
        raw = td.get_text(strip=True).lstrip("+")
        m = re.search(r"(\d+:\d{2}(?::\d{2})?)", raw)
        if m:
            parsed = parse_time_to_seconds(m.group(1)) or 0
            if parsed > 0:
                return parsed
    return 0


def _is_active_tab(table) -> bool:
    """
    Returnerer True hvis tabellen er i det AKTIVE PCS-faneblad (class='resTab' uden 'hide').
    På /gc-sider er kun GC-tabellen aktiv — alle andre (youth, points, kom) er skjulte.
    """
    node = table
    for _ in range(6):
        node = node.parent
        if node is None or node.name == "body":
            break
        if "resTab" in (node.get("class") or []):
            return "hide" not in (node.get("class") or [])
    return False  # Ikke i et resTab-element → ukendt struktur


def _table_heading(table) -> str:
    """
    Find overskriftsteksten tættest på tabellen (søg opad i DOM).
    Returnerer lowercased tekst eller tom streng.
    """
    heading_tags = {"h1", "h2", "h3", "h4", "h5", "h6"}
    node = table
    for _ in range(8):
        prev = node.find_previous_sibling()
        if prev:
            if prev.name in heading_tags:
                return prev.get_text(separator=" ", strip=True).lower()
            found = prev.find(heading_tags)
            if found:
                return found.get_text(separator=" ", strip=True).lower()
        node = node.parent
        if node is None or node.name == "body":
            break
    return ""


def _parse_table_standings(table) -> tuple[int, list]:
    """
    Parse en enkelt tabel til (p2_gap_seconds, standings_list).
    p2_gap_seconds bruges til at skelne GC-tabel (stor gap) fra sprint-tabel (gap=0).
    """
    rider_re = re.compile(r"^/?rider/")
    rows = table.find_all("tr")
    if len(rows) < 3:
        return 0, []

    start_idx = None
    for idx, row in enumerate(rows[:6]):
        tds = row.find_all("td", recursive=False)
        try:
            if int(tds[0].get_text(strip=True)) == 1:
                start_idx = idx
                break
        except (ValueError, IndexError):
            pass
    if start_idx is None:
        return 0, []

    standings = []
    p2_gap = 0
    for row in rows[start_idx:start_idx + TOP_N]:
        tds = row.find_all("td", recursive=False)
        try:
            pos = int(tds[0].get_text(strip=True))
        except (ValueError, IndexError):
            continue

        rider_a = row.find("a", href=rider_re)
        if not rider_a:
            continue
        pcs_slug = rider_a["href"].lstrip("/").replace("rider/", "").strip("/")
        name = rider_a.get_text(separator=" ", strip=True).upper()

        gap = _parse_time_gap(row) if pos > 1 else 0
        if pos == 2:
            p2_gap = gap

        standings.append({
            "position":         pos,
            "pcs_slug":         pcs_slug,
            "name":             name,
            "time_gap_seconds": gap,
        })

    return p2_gap, standings


def scrape_gc(html: str) -> list:
    """
    Parse GC-tabel fra PCS /gc eller /result side.
    Returnerer [{position, pcs_slug, name, time_gap_seconds}].

    Strategi: indsaml ALLE kandidat-tabeller med position=1.
    Sorter: størst P2-gap (GC) → senest i dokumentet (PCS viser altid stage-resultat
    FØR selve GC-tabellen på /gc-sider, så sidst-vinder ved ens gap).
    """
    soup = BeautifulSoup(html, "html.parser")
    # candidates: (p2_gap, table_index, standings)
    candidates: list[tuple[int, int, list]] = []

    for table_idx, table in enumerate(soup.find_all("table")):
        p2_gap, standings = _parse_table_standings(table)
        if standings:
            heading = _table_heading(table)
            active = _is_active_tab(table)
            # Er dette sandsynligvis GC-tabellen? Aktiv fane på /gc-URL er altid GC
            is_gc_heading = any(w in heading for w in ("general", "klassement général", "classifica generale"))
            is_gc = active or is_gc_heading
            # Intermediate classifications (sprint/KOM-checkpoints) har altid overskrift
            is_intermediate = bool(heading) and not is_gc_heading
            candidates.append((p2_gap, table_idx, is_gc, is_intermediate, len(standings), standings))

    if not candidates:
        return []

    # Gap > 7200s (2 timer) er fejlparsning af akkumuleret tid — behandl som 0
    MAX_REALISTIC_GAP = 7200

    def sort_key(c):
        p2_gap, table_idx, is_gc, is_intermediate, n_rows, standings = c
        gap = p2_gap if p2_gap <= MAX_REALISTIC_GAP else 0
        # Frasortér intermediate-tabeller (sprint/KOM checkpoints med specifik overskrift)
        if is_intermediate:
            return (-1, 0, 0, 0, 0)
        # Prioritér: aktiv PCS-fane (=GC på /gc-URL) > størst realistisk gap > flest ryttere
        return (int(is_gc), gap, n_rows, table_idx)

    candidates.sort(key=sort_key, reverse=True)
    valid = [c for c in candidates if not c[3]]
    if not valid:
        valid = candidates
    return valid[0][5]


def collect_stage_links(html: str, pcs_url_base: str, year: int) -> list[tuple[int, str]]:
    """
    Udtræk etape-URLs fra løb-oversigtsside.
    Returnerer [(stage_number, full_url)] sorteret stigende.
    """
    soup = BeautifulSoup(html, "html.parser")
    stage_re = re.compile(rf"race/[^/]+/{year}/stage-(\d+)$")
    seen = {}
    for a in soup.find_all("a", href=True):
        m = stage_re.search(a["href"].strip("/"))
        if m:
            sn = int(m.group(1))
            if sn not in seen:
                href = a["href"].strip()
                full = href if href.startswith("http") else f"{PCS_BASE}/{href.lstrip('/')}"
                seen[sn] = full
    return sorted(seen.items())


def scrape_winner_from_stage_page(html: str) -> tuple[str, str] | None:
    """
    Udtræk position-1 rytter fra en enkelt etapeside.
    Returnerer (pcs_slug, name) eller None.
    """
    soup = BeautifulSoup(html, "html.parser")
    rider_re = re.compile(r"^/?rider/")
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows[:6]:
            tds = row.find_all("td", recursive=False)
            try:
                if int(tds[0].get_text(strip=True)) != 1:
                    continue
            except (ValueError, IndexError):
                continue
            a = row.find("a", href=rider_re)
            if a:
                slug = a["href"].lstrip("/").replace("rider/", "").strip("/")
                name = a.get_text(separator=" ", strip=True).upper()
                return slug, name
    return None


def process_race(race: dict, sess: requests.Session, force: bool) -> dict:
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
    gc_url = f"{pcs_url}/result" if is_one_day else f"{pcs_url}/gc"
    print(f"  GC: {gc_url}")

    gc_html = fetch(sess, gc_url)
    standings = scrape_gc(gc_html)

    if not standings and not is_one_day:
        result_url = f"{pcs_url}/result"
        print(f"  GC tom — prøver {result_url}")
        standings = scrape_gc(fetch(sess, result_url))

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
        overview_html = fetch(sess, pcs_url)
        stage_links = collect_stage_links(overview_html, pcs_url, year)
        stage_wins = 0

        for sn, stage_url in stage_links:
            stage_html = fetch(sess, stage_url)
            winner = scrape_winner_from_stage_page(stage_html)
            if not winner:
                continue
            pcs_slug, name = winner
            sid = get_or_create_stage(race_id, sn)
            if sid and save_stage_winner(race_id, sid, pcs_slug, name):
                stage_wins += 1

        result["wins"] = stage_wins
        if stage_wins:
            print(f"  -> {stage_wins} etapevindere gemt")
        else:
            print(f"  -> Ingen etapevindere ({len(stage_links)} etaper fundet)")

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

    # Bootstrap: Playwright henter cf_clearance én gang, derefter bruges requests
    seed_url = races[0]["pcs_url"].rstrip("/") + ("/gc" if races[0].get("race_type") != "one_day" else "/result")
    sess, seed_html = make_session(seed_url)

    for i, race in enumerate(races, 1):
        print(f"[{i}/{len(races)}] {race['name']} ({race['start_date'][:4]})")
        try:
            res = process_race(race, sess, force)
        except requests.exceptions.RequestException as e:
            print(f"  [NETFEJL] {e.__class__.__name__} — springer over")
            total_skipped += 1
            time.sleep(5)
            continue

        if res["skipped"]:
            total_skipped += 1
        else:
            total_gc   += res["gc"]
            total_wins += res["wins"]

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
