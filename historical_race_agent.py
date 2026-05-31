"""
historical_race_agent.py

Scraper UCI WorldTour løb fra PCS for historiske år og gemmer races + stages i Supabase.
Springer automatisk over løb der allerede eksisterer (slug-baseret).

PCS URL-format:
  Løbliste: https://www.procyclingstats.com/races.php?year={year}&circuit=1
  Løbside:  https://www.procyclingstats.com/race/{pcs-slug}/{year}

Kør:
  python historical_race_agent.py               # 2021–2025
  python historical_race_agent.py --year 2024   # Ét år
  python historical_race_agent.py --years 2023 2024 2025
"""

import io
import os
import re
import sys
import time
import argparse
import requests
from bs4 import BeautifulSoup
from slugify import slugify
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

AUTH   = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
DB     = {**AUTH, "Content-Type": "application/json", "Prefer": "return=minimal"}
REPR   = {**AUTH, "Content-Type": "application/json",
          "Prefer": "resolution=ignore-duplicates,return=representation"}

PCS_BASE = "https://www.procyclingstats.com"
CIRCUIT  = 1      # 1 = UCI WorldTour
DELAY    = 1.5    # sekunder mellem PCS-sideindlæsninger

MONTHS_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


# ── Supabase helpers ──────────────────────────────────────────────────────────

def get_existing_slugs() -> set:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?select=slug&limit=1000",
        headers=AUTH,
    )
    return {r["slug"] for r in res.json()} if res.ok and isinstance(res.json(), list) else set()


def save_race(data: dict) -> str | None:
    """Gem løb og returner race_id, eller None hvis det allerede eksisterede."""
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/races",
        json=data,
        headers=REPR,
    )
    if res.ok and res.text and res.text not in ("[]", ""):
        rows = res.json()
        if isinstance(rows, list) and rows:
            return rows[0]["id"]
    return None


def get_race_id(slug: str) -> str | None:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?slug=eq.{slug}&select=id&limit=1",
        headers=AUTH,
    )
    data = res.json()
    return data[0]["id"] if res.ok and data else None


def save_stages(stages: list) -> None:
    if not stages:
        return
    requests.post(
        f"{SUPABASE_URL}/rest/v1/stages",
        json=stages,
        headers={**DB, "Prefer": "resolution=ignore-duplicates,return=minimal"},
    )


# ── PCS parsing ───────────────────────────────────────────────────────────────

def fetch(pw_page, url: str) -> str:
    pw_page.goto(url, wait_until="networkidle", timeout=35_000)
    time.sleep(DELAY)
    return pw_page.content()


def parse_race_list(html: str, year: int) -> list:
    """
    Udtræk løb fra PCS races.php.
    Returnerer [{name, pcs_slug, pcs_url}].
    """
    soup = BeautifulSoup(html, "html.parser")
    seen, races = set(), []

    # PCS-links til løb er på formen /race/{slug}/{year} eller race/{slug}/{year}
    pattern = re.compile(rf"^/?race/([a-z0-9\-]+)/{year}$")

    for a in soup.find_all("a", href=True):
        m = pattern.match(a["href"].strip())
        if not m:
            continue
        pcs_slug = m.group(1)
        if pcs_slug in seen:
            continue
        name = a.get_text(strip=True)
        if not name or len(name) < 3:
            continue
        seen.add(pcs_slug)
        races.append({
            "name":     name,
            "pcs_slug": pcs_slug,
            "pcs_url":  f"{PCS_BASE}/race/{pcs_slug}/{year}",
        })
    return races


def parse_race_dates(html: str, year: int) -> tuple:
    """
    Udtræk start- og slutdato fra PCS løbside.
    Returnerer (start_date_iso, end_date_iso).
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ")

    # Match "3 July 2025" eller "3 Jul 2025"
    pat = re.compile(
        r"(\d{1,2})\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"\s+(\d{4})",
        re.IGNORECASE,
    )
    dates = []
    for day, month, yr in pat.findall(text):
        if int(yr) == year:
            mn = MONTHS_EN.get(month.lower()[:3], 0) or MONTHS_EN.get(month.lower(), 0)
            if mn:
                iso = f"{yr}-{mn:02d}-{int(day):02d}"
                if iso not in dates:
                    dates.append(iso)

    if len(dates) >= 2:
        return dates[0], dates[-1]
    if len(dates) == 1:
        return dates[0], dates[0]
    return f"{year}-01-01", f"{year}-12-31"


def parse_stages(html: str, race_id: str, year: int, pcs_base: str) -> list:
    """
    Udtræk etapeliste fra PCS løbside.
    Returnerer [{race_id, stage_number, name, date, pcs_stage_url, source}].
    """
    soup = BeautifulSoup(html, "html.parser")
    seen, stages = set(), []

    stage_pat = re.compile(rf"^/?race/[^/]+/{year}/stage-(\d+)$", re.IGNORECASE)
    prolog_pat = re.compile(rf"^/?race/[^/]+/{year}/prologue$", re.IGNORECASE)

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        stage_m = stage_pat.match(href)
        prolog_m = prolog_pat.match(href)

        if stage_m:
            sn = int(stage_m.group(1))
        elif prolog_m:
            sn = 0
        else:
            continue

        if sn in seen:
            continue
        seen.add(sn)

        result_url = f"{PCS_BASE}/{href.lstrip('/')}/result"

        # Forsøg at hente dato fra omgivende tabel-række
        row = a.find_parent("tr") or a.find_parent("li")
        date_str = None
        if row:
            row_text = row.get_text(" ")
            dm = re.search(
                r"(\d{1,2})\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
                r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
                r"Nov(?:ember)?|Dec(?:ember)?)",
                row_text, re.IGNORECASE,
            )
            if dm:
                day = int(dm.group(1))
                mon = MONTHS_EN.get(dm.group(2).lower()[:3], 0) or MONTHS_EN.get(dm.group(2).lower(), 0)
                if mon:
                    date_str = f"{year}-{mon:02d}-{day:02d}"

        stages.append({
            "race_id":       race_id,
            "stage_number":  sn,
            "name":          "Prolog" if sn == 0 else f"Etape {sn}",
            "date":          date_str,
            "pcs_stage_url": result_url,
            "source":        "pcs_historical",
        })

    return sorted(stages, key=lambda x: x["stage_number"])


# ── Main ──────────────────────────────────────────────────────────────────────

def run(years: list) -> None:
    print(f"historical_race_agent.py — behandler år: {years}")
    existing = get_existing_slugs()
    print(f"Løb i DB allerede: {len(existing)}\n")

    total_new = total_stages = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

        for year in sorted(years):
            print(f"══ {year} ══════════════════════════════════")
            list_url = f"{PCS_BASE}/races.php?year={year}&circuit={CIRCUIT}"
            print(f"Henter løbliste: {list_url}")

            html = fetch(page, list_url)
            race_list = parse_race_list(html, year)
            print(f"Fundet {len(race_list)} løb\n")

            year_new = 0
            for rc in race_list:
                db_slug = slugify(f"{rc['name']}-{year}")

                if db_slug in existing:
                    print(f"  [SKIP] {rc['name']} {year}")
                    continue

                print(f"  [{rc['name']} {year}] Henter side...")
                race_html = fetch(page, rc["pcs_url"])

                start_date, end_date = parse_race_dates(race_html, year)
                is_one_day = start_date == end_date

                race_id = save_race({
                    "name":       rc["name"],
                    "slug":       db_slug,
                    "category":   "UCI WorldTour",
                    "start_date": start_date,
                    "end_date":   end_date,
                    "pcs_url":    rc["pcs_url"],
                    "source":     "pcs_historical",
                    "race_type":  "one_day" if is_one_day else "stage_race",
                })

                if not race_id:
                    # Kan allerede eksistere (løb der matcher slugify men ikke eksakt)
                    race_id = get_race_id(db_slug)
                    if not race_id:
                        print(f"  -> FEJL ved gemning")
                        continue

                existing.add(db_slug)
                year_new += 1
                total_new += 1

                stages = parse_stages(race_html, race_id, year, rc["pcs_url"])
                save_stages(stages)
                total_stages += len(stages)

                label = "enkeltdagsløb" if is_one_day else f"{len(stages)} etaper"
                print(f"  -> Gemt: {rc['name']} {year} ({start_date}–{end_date}, {label})")

            print(f"\n{year}: {year_new} nye løb\n")
        browser.close()

    print(f"Færdig: {total_new} løb + {total_stages} etaper oprettet")
    print("Kør nu: python historical_results_agent.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--year",  type=int, help="Ét år")
    grp.add_argument("--years", type=int, nargs="+", help="Liste af år")
    args = parser.parse_args()

    if args.year:
        run([args.year])
    elif args.years:
        run(args.years)
    else:
        run([2021, 2022, 2023, 2024, 2025])
