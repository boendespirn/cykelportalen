"""
historical_race_agent.py

Scraper UCI WorldTour løb fra PCS for historiske år og gemmer dem i Supabase.
Henter KUN løbslisten (ét sideload per år) — dato og type udtrækkes herfra.
Stages oprettes on-demand af historical_results_agent.py.

PCS table format: Date | Date | Race | Previous winner | Category
  Eks: "16.01 - 21.01 | 16.01 | Santos Tour Down Under | WILLIAMS | 2.UWT"

Kør:
  python historical_race_agent.py               # 2021–2025
  python historical_race_agent.py --year 2024
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

AUTH  = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
DB    = {**AUTH, "Content-Type": "application/json", "Prefer": "return=minimal"}

PCS_BASE = "https://www.procyclingstats.com"
CIRCUIT  = 1      # 1 = UCI WorldTour
DELAY    = 2.5    # sekunder efter sideindlæsning


# ── Cloudflare-safe page fetch ────────────────────────────────────────────────

def fetch(pw_page, url: str) -> str:
    pw_page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    # Vent på at Cloudflare-challenge løser sig (kan hedde "Just a moment...",
    # "Et øjeblik...", "Un momento..." afhængigt af browsersprog)
    for _ in range(25):
        title = pw_page.title().lower()
        if "øjeblik" not in title and "moment" not in title and "cloudflare" not in title:
            break
        time.sleep(1.5)
    time.sleep(DELAY)
    return pw_page.content()


# ── Supabase helpers ──────────────────────────────────────────────────────────

def get_existing_slugs() -> set:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?select=slug&limit=2000",
        headers=AUTH,
    )
    return {r["slug"] for r in res.json()} if res.ok and isinstance(res.json(), list) else set()


def save_race(data: dict) -> str | None:
    """Gem løb og returner race_id, eller None hvis det allerede eksisterede."""
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/races",
        json=data,
        headers={**DB, "Prefer": "resolution=ignore-duplicates,return=representation"},
    )
    if res.ok and res.text and res.text not in ("[]", ""):
        rows = res.json()
        if isinstance(rows, list) and rows:
            return rows[0]["id"]
    return None


# ── PCS list-page parsing ─────────────────────────────────────────────────────

def parse_race_list(html: str, year: int) -> list:
    """
    Parser PCS løbliste-tabel.
    Kolonne 0: "DD.MM - DD.MM" (datoer)
    Kolonne 2+: race-link
    Kolonne 4: UCI-kategori ("1.UWT" = enkeltdag, "2.UWT" = etapeløb)

    Returnerer [{name, pcs_slug, pcs_url, start_date, end_date, race_type}].
    """
    soup = BeautifulSoup(html, "html.parser")
    link_pat   = re.compile(rf"^/?race/([a-z0-9\-]+)/{year}(?:/.*)?$")
    date_range = re.compile(r"^(\d{1,2})\.(\d{1,2})(?:\s*[-–]\s*(\d{1,2})\.(\d{1,2}))?")

    seen, races = set(), []

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            tds = row.find_all("td")
            if not tds:
                continue

            # Find race-link
            race_a = row.find("a", href=link_pat)
            if not race_a:
                continue
            m = link_pat.match(race_a["href"].strip())
            if not m:
                continue
            pcs_slug = m.group(1)
            if pcs_slug in seen:
                continue

            name = race_a.get_text(strip=True)
            if not name or len(name) < 3:
                continue

            # Parse dato fra kolonne 0
            start_date = end_date = f"{year}-01-01"
            date_text = tds[0].get_text(strip=True)
            dm = date_range.match(date_text)
            if dm:
                sd, sm = int(dm.group(1)), int(dm.group(2))
                start_date = f"{year}-{sm:02d}-{sd:02d}"
                if dm.group(3) and dm.group(4):
                    ed, em = int(dm.group(3)), int(dm.group(4))
                    end_date = f"{year}-{em:02d}-{ed:02d}"
                else:
                    end_date = start_date

            # UCI-kategori: 1.UWT = enkeltdag, 2.UWT = etapeløb
            cat_text = tds[-1].get_text(strip=True) if tds else ""
            race_type = "one_day" if cat_text.startswith("1.") else "stage_race"

            seen.add(pcs_slug)
            races.append({
                "name":       name,
                "pcs_slug":   pcs_slug,
                "pcs_url":    f"{PCS_BASE}/race/{pcs_slug}/{year}",
                "start_date": start_date,
                "end_date":   end_date,
                "race_type":  race_type,
            })

    return races


# ── Main ──────────────────────────────────────────────────────────────────────

def run(years: list) -> None:
    print(f"historical_race_agent.py — år: {years}")
    existing = get_existing_slugs()
    print(f"Løb i DB allerede: {len(existing)}\n")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, channel="chrome")
        except Exception:
            browser = p.chromium.launch(headless=True)

        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()
        total_new = 0

        for year in sorted(years):
            print(f"══ {year} ══════════════════════════════════")
            list_url = f"{PCS_BASE}/races.php?year={year}&circuit={CIRCUIT}"
            print(f"Henter: {list_url}")

            html = fetch(page, list_url)
            race_list = parse_race_list(html, year)
            print(f"Fundet: {len(race_list)} løb\n")

            if not race_list:
                print(f"  OBS: Ingen løb fundet — siden kan have Cloudflare-udfordring")
                print(f"  Prøv at øge DELAY eller køre scriptet igen\n")
                continue

            year_new = 0
            for rc in race_list:
                db_slug = slugify(f"{rc['name']}-{year}")

                if db_slug in existing:
                    print(f"  [SKIP] {rc['name']}")
                    continue

                race_id = save_race({
                    "name":       rc["name"],
                    "slug":       db_slug,
                    "category":   "UCI WorldTour",
                    "start_date": rc["start_date"],
                    "end_date":   rc["end_date"],
                    "pcs_url":    rc["pcs_url"],
                    "source":     "pcs_historical",
                    "race_type":  rc["race_type"],
                })

                if race_id:
                    existing.add(db_slug)
                    year_new += 1
                    total_new += 1
                    label = "enkeltdag" if rc["race_type"] == "one_day" else "etapeløb"
                    print(f"  -> {rc['name']} {year} ({rc['start_date']} → {rc['end_date']}, {label})")
                else:
                    print(f"  -> FEJL/DUPLIKAT: {rc['name']} {year}")

            print(f"\n{year}: {year_new} nye løb\n")

        ctx.close()
        browser.close()

    print(f"Færdig: {total_new} løb oprettet i alt")
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
