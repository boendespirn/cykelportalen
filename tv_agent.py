"""
tv_agent.py
Scraper for TV-udsendelsestider fra sport.tv2.dk/cykling/sendeplan
Gemmer i broadcast_schedule tabel i Supabase

Kør: python tv_agent.py
     python tv_agent.py --dry-run
"""

import os
import re
import sys
import io
import time
import argparse
import requests
from datetime import datetime, date, timezone
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

TV2_URL = "https://sport.tv2.dk/cykling/sendeplan"


# ── Supabase helpers ──────────────────────────────────────────────────────────

def get_races() -> dict[str, str]:
    """Returnerer {lowercase name: slug} for alle løb."""
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?select=name,slug&limit=100",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
    )
    return {r["name"].lower(): r["slug"] for r in (res.json() if res.ok else [])}


def upsert_broadcast(entry: dict) -> bool:
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/broadcast_schedule",
        json=entry,
        headers={
            **HEADERS,
            "Prefer": "resolution=merge-duplicates,return=minimal",
            "on_conflict": "race_id,broadcast_date,start_time,broadcaster",
        },
    )
    return res.ok


# ── Scraping ──────────────────────────────────────────────────────────────────

BROADCASTER_MAP = {
    "tv 2 sport":    "TV 2 Sport",
    "tv2 sport":     "TV 2 Sport",
    "tv 2 sport x":  "TV 2 Sport X",
    "tv2 sport x":   "TV 2 Sport X",
    "kanal 5":       "Kanal 5 / HBO Max",
    "hbo max":       "Kanal 5 / HBO Max",
    "gcn+":          "GCN+",
    "eurosport":     "Eurosport",
    "eurosport 1":   "Eurosport",
    "eurosport 2":   "Eurosport 2",
}

RACE_KEYWORDS = {
    "giro":        "giro-d-italia-2026",
    "tour de fra": "tour-de-france-2026",
    "vuelta":      "vuelta-a-espana-2026",
    "flandern":    "ronde-van-vlaanderen-2026",
    "paris-rouba": "paris-roubaix-2026",
    "liège":       "liege-bastogne-liege-2026",
    "amstel":      "amstel-gold-race-2026",
    "dauphine":    "criterium-du-dauphine-2026",
    "auvergne":    "criterium-du-dauphine-2026",
    "schweiz":     "tour-de-suisse-2026",
}


def normalize_broadcaster(raw: str) -> str:
    low = raw.lower().strip()
    for key, val in BROADCASTER_MAP.items():
        if key in low:
            return val
    return raw.strip()


def match_race_slug(title: str, races: dict[str, str]) -> str | None:
    """Matcher en programtitel til et løb-slug."""
    low = title.lower()

    # Direkte nøgleord-match
    for keyword, slug in RACE_KEYWORDS.items():
        if keyword in low:
            # Tjek om løbet faktisk eksisterer i DB
            if slug in races.values():
                return slug

    # Fuzzy match mod DB-navne
    for race_name, slug in races.items():
        if any(word in low for word in race_name.split() if len(word) > 4):
            return slug

    return None


def parse_time(raw: str) -> str | None:
    """Parser 'kl. 14.00' eller '14:00' til 'HH:MM:SS'."""
    m = re.search(r"(\d{1,2})[\.:](\d{2})", raw)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}:00"
    return None


def scrape_tv2(dry_run: bool) -> None:
    races = get_races()
    print(f"tv_agent.py — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Hentede {len(races)} løb fra DB\n")

    saved = skipped = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 Klassementet/1.0"})

        print(f"Henter {TV2_URL} ...")
        page.goto(TV2_URL, wait_until="networkidle", timeout=30_000)
        time.sleep(2)

        html = page.content()
        browser.close()

    # Parse med regex — siden har strukturerede program-blokke
    # Søger efter: dato-header, program-titel, tidspunkt, kanal
    # Strukturen på TV2 Sport sendeplan:
    # Dato → [blok med program, tid, kanal]

    # Find alle program-blokke — tilpasning nødvendig til sidens faktiske HTML
    # Vi prøver at udtrække: titel, dato, starttid, sluttid, kanal

    # Simpelt regex-pass — siden bruger en del JavaScript rendering
    # Vi leder efter mønstre som "kl. 14.00" og kanalnavne

    entries_found = []

    MONTH_MAP = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "maj": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dec": 12,
    }

    # TV2 Sport sendeplan-format (2025/2026):
    # "Tirsdag 26. maj Tir 26. maj kl. 14.00 Cykling Giro d'Italia: 16. etape ..."
    # Ingen explicit kanalmarkering — broadcaster er TV 2 Sport / TV 2 Play

    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    year = datetime.now().year

    # Match alle blokke: dato + kl. + løbsnavn
    pattern = re.compile(
        r"(?:man|tir|ons|tor|fre|lør|søn)\s+(\d{1,2})\.\s*"
        r"(jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec)\w*"
        r"\s+kl\.\s*(\d{1,2})\.(\d{2})"
        r"\s+Cykling\s+"
        r"(Giro[^:]+|Tour[^:]+|Vuelta[^:]+|Paris[^:]+|Flandern[^:]+|"
        r"Amstel[^:]+|Li[eè]ge[^:]+|Dauphine[^:]+|Crit[eé]rium[^:]+|"
        r"Schweiz[^:]+|Auvergne[^:]+|WorldTour[^:]+)"
        r":\s*(\d+)\.\s*etape",
        re.IGNORECASE,
    )

    race_id_cache: dict[str, str | None] = {}

    for m in pattern.finditer(text):
        day       = int(m.group(1))
        mon_str   = m.group(2).lower()[:3]
        hour      = int(m.group(3))
        minute    = m.group(4)
        race_name = m.group(5).strip()
        stage_num = int(m.group(6))

        month = MONTH_MAP.get(mon_str)
        if not month:
            continue

        try:
            broadcast_date = date(year, month, day)
        except ValueError:
            continue

        slug = match_race_slug(race_name, races)
        if not slug:
            skipped += 1
            continue

        # Vælg broadcaster baseret på løb
        if "giro" in race_name.lower():
            broadcaster = "TV 2 Sport X"
        elif "tour de france" in race_name.lower():
            broadcaster = "TV 2 Sport"
        else:
            broadcaster = "TV 2 Play"

        start_time = f"{hour:02d}:{minute}:00"
        date_str   = broadcast_date.isoformat()

        entry = {
            "broadcast_date": date_str,
            "stage_number":   stage_num,
            "start_time":     start_time,
            "broadcaster":    broadcaster,
            "is_live":        True,
            "notes":          f"{race_name}: etape {stage_num}",
        }

        if slug not in race_id_cache:
            res = requests.get(
                f"{SUPABASE_URL}/rest/v1/races?slug=eq.{slug}&select=id&limit=1",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            )
            race_id_cache[slug] = res.json()[0]["id"] if (res.ok and res.json()) else None

        race_id = race_id_cache[slug]
        if not race_id:
            skipped += 1
            continue

        entry["race_id"] = race_id
        entries_found.append(entry)
        print(f"  [{date_str}] {broadcaster} {start_time} — {race_name} E{stage_num}")

        if not dry_run:
            if upsert_broadcast(entry):
                saved += 1
            else:
                skipped += 1

    if dry_run:
        print(f"\nDry-run: {len(entries_found)} poster fundet (ikke gemt)")
    else:
        print(f"\nFærdig: {saved} gemt, {skipped} sprunget over")

    if not entries_found:
        print("\nIngen programposter fundet — siden kan kræve tilpasning af regex")


# ── Manuelt tilføj udsendelser ────────────────────────────────────────────────

def add_manual(race_slug: str, entries: list[dict]) -> None:
    """Tilføjer manuelle udsendelsestider — bruges som fallback."""
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?slug=eq.{race_slug}&select=id&limit=1",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
    )
    if not res.ok or not res.json():
        print(f"Løb ikke fundet: {race_slug}")
        return

    race_id = res.json()[0]["id"]
    saved = 0
    for e in entries:
        e["race_id"] = race_id
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/broadcast_schedule",
            json=e,
            headers={
                **HEADERS,
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )
        if r.ok:
            saved += 1
            print(f"  Gemt: {e['broadcast_date']} {e['start_time']} {e['broadcaster']}")
        else:
            print(f"  FEJL: {r.status_code} {r.text[:100]}")
    print(f"Gemt {saved}/{len(entries)} poster")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Vis kun hvad der ville blive gemt")
    parser.add_argument("--race",    help="Løb-slug (filtrér output)")
    args = parser.parse_args()

    scrape_tv2(dry_run=args.dry_run)
