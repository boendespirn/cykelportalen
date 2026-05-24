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
    "giro":        "giro-ditalia-2026",
    "tour de fra": "tour-de-france-2026",
    "vuelta":      "vuelta-a-espana-2026",
    "flandern":    "ronde-van-vlaanderen-2026",
    "paris-rouba": "paris-roubaix-2026",
    "liège":       "liege-bastogne-liege-2026",
    "amstel":      "amstel-gold-race-2026",
    "dauphine":    "criterium-du-dauphine-2026",
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

    # Dato-mønstre: "mandag d. 26. maj", "tirsdag 27. maj 2025" osv.
    date_pattern = re.compile(
        r"(mandag|tirsdag|onsdag|torsdag|fredag|lørdag|søndag)[,\s]+(?:d\.\s*)?(\d{1,2})\.\s*"
        r"(januar|februar|marts|april|maj|juni|juli|august|september|oktober|november|december)"
        r"(?:\s+\d{4})?",
        re.IGNORECASE,
    )

    MONTH_MAP = {
        "januar": 1, "februar": 2, "marts": 3, "april": 4, "maj": 5, "juni": 6,
        "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "december": 12,
    }

    # Udtræk tekst-blokke fra HTML
    # Fjern HTML-tags for at arbejde med ren tekst
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)

    current_date: date | None = None
    year = datetime.now().year

    # Split i sætninger/segmenter ved nøgleord
    segments = re.split(r"(?=(?:mandag|tirsdag|onsdag|torsdag|fredag|lørdag|søndag))", text, flags=re.IGNORECASE)

    for seg in segments:
        # Prøv at parse dato fra segmentet
        dm = date_pattern.search(seg)
        if dm:
            try:
                day = int(dm.group(2))
                month = MONTH_MAP[dm.group(3).lower()]
                current_date = date(year, month, day)
            except (ValueError, KeyError):
                pass

        if not current_date:
            continue

        # Find alle cykling-programmer i dette segment
        # Se efter: titel med "Giro/Tour/Vuelta..." + tidsangivelse + kanal
        prog_blocks = re.findall(
            r"((?:Giro|Tour|Vuelta|Classic|Paris|Flandern|Liège|Amstel|Critérium|Dauphine|Schweiz|WorldTour|UCI)\S*[^•·\n]{0,80}?)"
            r"\s+kl\.\s*(\d{1,2}[\.]\d{2})"
            r"(?:\s*[-–]\s*kl\.\s*(\d{1,2}[\.]\d{2}))?"
            r"[^•·]{0,60}?"
            r"(TV\s*2\s*Sport\s*X?|Kanal\s*5|HBO\s*Max|GCN\+|Eurosport\s*\d?)",
            seg,
            re.IGNORECASE,
        )

        for title, start_raw, end_raw, channel_raw in prog_blocks:
            slug = match_race_slug(title, races)
            if not slug:
                continue

            start_time = parse_time(start_raw)
            end_time   = parse_time(end_raw) if end_raw else None
            broadcaster = normalize_broadcaster(channel_raw)
            date_str = current_date.isoformat()

            entry = {
                "race_id":        None,  # sættes nedenfor
                "broadcast_date": date_str,
                "start_time":     start_time,
                "end_time":       end_time,
                "broadcaster":    broadcaster,
                "is_live":        True,
                "notes":          title.strip()[:200],
            }

            # Hent race_id fra slug
            res = requests.get(
                f"{SUPABASE_URL}/rest/v1/races?slug=eq.{slug}&select=id&limit=1",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            )
            if res.ok and res.json():
                entry["race_id"] = res.json()[0]["id"]

                entries_found.append(entry)
                print(f"  [{date_str}] {broadcaster} {start_time} — {title.strip()[:50]}")

                if not dry_run:
                    if upsert_broadcast(entry):
                        saved += 1
                    else:
                        skipped += 1
            else:
                skipped += 1

    if dry_run:
        print(f"\nDry-run: {len(entries_found)} poster fundet (ikke gemt)")
    else:
        print(f"\nFærdig: {saved} gemt, {skipped} sprunget over")

    if not entries_found:
        print("\nIngen programposter fundet — siden kan kræve tilpasning af regex")
        print("Tip: Kør med --dry-run og inspicér html-output")


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
