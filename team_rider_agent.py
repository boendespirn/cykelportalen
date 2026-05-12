"""
team_rider_agent.py
Scraper UCI WorldTeam holds og ryttere fra ProCyclingStats.
Kør: python team_rider_agent.py
"""

import os
import re
import sys
import io
import time
import requests
from bs4 import BeautifulSoup
from slugify import slugify
from dotenv import load_dotenv
from datetime import datetime

# Sørg for UTF-8 output i Windows-terminal
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
BASE_URL = "https://www.procyclingstats.com"
YEAR = 2026

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "da-DK,da;q=0.9,en;q=0.8",
}

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}


# ── Hjælpefunktioner ────────────────────────────────────────────────────────

def get_soup(url: str) -> BeautifulSoup:
    res = requests.get(url, headers=HEADERS, timeout=15)
    if res.status_code == 403 or "cf-browser-verification" in res.text:
        raise RuntimeError(
            f"Adgang nægtet (Cloudflare) for {url}\n"
            "Installer Playwright: pip install playwright && playwright install chromium\n"
            "Og brug playwright_agent.py i stedet."
        )
    res.raise_for_status()
    return BeautifulSoup(res.text, "html.parser")


def upsert(table: str, records: list, conflict_col: str = "slug") -> None:
    url = f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={conflict_col}"
    res = requests.post(url, json=records, headers=SUPABASE_HEADERS)
    if not res.ok:
        print(f"  [DB FEJL] {table}: {res.status_code} — {res.text[:200]}")
    res.raise_for_status()


def parse_flag_code(el) -> str | None:
    if not el:
        return None
    for cls in el.get("class", []):
        if cls != "flag" and len(cls) == 2:
            return cls.upper()
    return None


def parse_date(text: str) -> str | None:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        return m.group(1)
    for fmt in ("%d %B %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text.strip()[:20], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def get_team_id(slug: str) -> str | None:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/teams?slug=eq.{slug}&select=id",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
    )
    data = res.json()
    return data[0]["id"] if data else None


# ── Scrapers ─────────────────────────────────────────────────────────────────

def scrape_worldteam_list() -> list[dict]:
    """Henter liste over alle UCI WorldTeams fra PCS."""
    print(f"Henter WorldTeams {YEAR} fra PCS...")
    soup = get_soup(f"{BASE_URL}/teams/UCI-worldteams/{YEAR}")

    seen = set()
    teams = []
    # PCS bruger relative URLs uden foranstillet skråstreg
    for a in soup.select("ul.list li a"):
        href = a.get("href", "")
        name = a.get_text(strip=True)
        if not name or not href.startswith("team/"):
            continue
        pcs_slug = href.split("team/")[1]
        if pcs_slug in seen:
            continue
        seen.add(pcs_slug)
        teams.append({
            "name": name,
            "pcs_slug": pcs_slug,
            "slug": slugify(name),
        })

    print(f"  Fandt {len(teams)} hold")
    return teams


COUNTRY_NAME_TO_CODE = {
    "netherlands": "NL", "france": "FR", "belgium": "BE", "italy": "IT",
    "spain": "ES", "germany": "DE", "denmark": "DK", "norway": "NO",
    "sweden": "SE", "switzerland": "CH", "great britain": "GB", "usa": "US",
    "australia": "AU", "colombia": "CO", "slovenia": "SI", "portugal": "PT",
    "austria": "AT", "luxembourg": "LU", "ireland": "IE", "poland": "PL",
    "kazakhstan": "KZ", "uae": "AE", "bahrain": "BH", "israel": "IL",
    "new zealand": "NZ", "ecuador": "EC", "south africa": "ZA",
}


def scrape_team_detail(pcs_slug: str) -> dict:
    """Henter detaljer og rytterliste fra en enkelt holdside."""
    soup = get_soup(f"{BASE_URL}/team/{pcs_slug}")

    country_code = None
    uci_code = None
    category = "WorldTeam"
    founded_year = None

    for li in soup.select("ul.infolist li"):
        divs = li.select("div")
        if len(divs) < 2:
            continue
        label = divs[0].get_text(strip=True).lower()
        value = divs[-1].get_text(strip=True)

        if "abbreviation" in label:
            uci_code = value
        elif "status" in label:
            category = value
        elif "license country" in label or "country" in label:
            country_code = COUNTRY_NAME_TO_CODE.get(value.lower())
        elif "founded" in label or "since" in label:
            m = re.search(r"\d{4}", value)
            if m:
                founded_year = int(m.group())

    # Rytterliste — PCS bruger ul.teamlist med relative href-links
    seen = set()
    riders = []
    for li in soup.select("ul.teamlist li"):
        a = li.select_one("a")
        if not a:
            continue
        href = a.get("href", "")
        if not href.startswith("rider/"):
            continue
        pcs_rider_slug = href.split("rider/")[1]
        if pcs_rider_slug in seen:
            continue
        seen.add(pcs_rider_slug)

        rider_name = a.get_text(strip=True)
        # Nationalitet kan læses direkte fra flag-span i li'en
        nationality = parse_flag_code(li.select_one("span.flag"))

        riders.append({
            "name": rider_name,
            "pcs_slug": pcs_rider_slug,
            "slug": slugify(rider_name),
            "nationality": nationality,
        })

    return {
        "country_code": country_code,
        "uci_team_code": uci_code,
        "category": category,
        "founded_year": founded_year,
        "riders": riders,
    }


def scrape_rider_detail(pcs_slug: str) -> dict:
    """Henter nationalitet, fødselsdato og specialitet for én rytter."""
    soup = get_soup(f"{BASE_URL}/rider/{pcs_slug}")

    nationality = None
    date_of_birth = None
    speciality = None

    for li in soup.select("ul.infolist li"):
        divs = li.select("div")
        if len(divs) < 2:
            continue
        label = divs[0].get_text(strip=True).lower()
        value = divs[-1].get_text(strip=True)

        if "nationality" in label:
            nationality = parse_flag_code(divs[-1].select_one("span.flag"))
        elif "date of birth" in label or "born" in label:
            date_of_birth = parse_date(value)
        elif "speciality" in label:
            speciality = value if value else None

    return {
        "nationality": nationality,
        "date_of_birth": date_of_birth,
        "speciality": speciality,
    }


# ── Hovedprogram ─────────────────────────────────────────────────────────────

def run():
    raw_teams = scrape_worldteam_list()

    for raw in raw_teams:
        print(f"\n[{raw['name']}]")

        # Holddetaljer
        try:
            detail = scrape_team_detail(raw["pcs_slug"])
            time.sleep(1.5)
        except Exception as e:
            print(f"  FEJL (holdside): {e}")
            continue

        # Gem hold
        team_record = {
            "name": raw["name"],
            "slug": raw["slug"],
            "country_code": detail["country_code"],
            "category": detail["category"],
            "uci_team_code": detail["uci_team_code"],
            "founded_year": detail["founded_year"],
            "source_url": f"{BASE_URL}/team/{raw['pcs_slug']}",
        }
        upsert("teams", [team_record])
        print(f"  Hold gemt: {raw['name']}")

        team_id = get_team_id(raw["slug"])
        if not team_id:
            print("  FEJL: Kunne ikke hente team_id fra DB")
            continue

        # Ryttere
        print(f"  Henter {len(detail['riders'])} ryttere...")
        rider_records = []

        for r in detail["riders"]:
            try:
                rd = scrape_rider_detail(r["pcs_slug"])
                time.sleep(1.0)
            except Exception as e:
                print(f"    FEJL ({r['name']}): {e}")
                rd = {}

            # Nationalitet fra teamliste, DOB + specialitet fra rytterside
            nationality = r.get("nationality") or rd.get("nationality")
            rider_records.append({
                "name": r["name"],
                "slug": r["slug"],
                "nationality": nationality,
                "date_of_birth": rd.get("date_of_birth"),
                "speciality": rd.get("speciality"),
                "team_id": team_id,
                "source_url": f"{BASE_URL}/rider/{r['pcs_slug']}",
            })
            print(f"    {r['name']} ({nationality or '?'})")

        if rider_records:
            upsert("riders", rider_records)
            print(f"  {len(rider_records)} ryttere gemt")

    print("\nFærdig!")


if __name__ == "__main__":
    run()
