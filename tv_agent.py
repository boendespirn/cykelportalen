"""
tv_agent.py
Scraper for TV/streaming-udsendelsestider fra cykelkalenderen.dk
Viser alle steder man kan se cykling: Eurosport, HBO Max, Discovery+, TV 2 m.fl.
Gemmer i broadcast_schedule tabel i Supabase.

Kør: python tv_agent.py
     python tv_agent.py --dry-run
"""

import os
import re
import time
import argparse
import requests
from datetime import datetime, date
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

HEADERS = {
    "apikey":          SUPABASE_KEY,
    "Authorization":   f"Bearer {SUPABASE_KEY}",
    "Content-Type":    "application/json",
    "Prefer":          "return=minimal",
}
AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

SOURCE_URL = "https://cykelkalenderen.dk"

# TV-logo filnavn → visningsnavn i DB/frontend
LOGO_MAP = {
    "max-logo.png":    "HBO Max",
    "kanal-5.svg":     "Discovery+",
    "eurosport-1.svg": "Eurosport 1",
    "eurosport-2.svg": "Eurosport 2",
    "tv2-sport.svg":   "TV 2 Sport",
    "tv2-sport-x.svg": "TV 2 Sport X",
    "tv2-sport-2.svg": "TV 2 Sport X",
    "tv-2-sport.svg":  "TV 2 Sport",
    "tv2play.svg":     "TV 2 Play",
    "gcn.svg":         "GCN+",
    "gcn-plus.svg":    "GCN+",
    "viaplay.svg":     "Viaplay",
    "dplay.svg":       "Discovery+",
}

# Nøgleord i løbstitel → DB slug (opdater ved ny sæson)
RACE_KEYWORDS = {
    "giro":        "giro-d-italia-2026",
    "tour de fra": "tour-de-france-2026",
    "vuelta":      "vuelta-a-espana-2026",
    "flandern":    "ronde-van-vlaanderen-2026",
    "roubaix":     "paris-roubaix-2026",
    "liège":       "liege-bastogne-liege-2026",
    "liege":       "liege-bastogne-liege-2026",
    "amstel":      "amstel-gold-race-2026",
    "dauphine":    "criterium-du-dauphine-2026",
    "auvergne":    "criterium-du-dauphine-2026",
    "schweiz":     "tour-de-suisse-2026",
    "suisse":      "tour-de-suisse-2026",
    "lombardia":   "il-lombardia-2026",
    "san remo":    "milano-san-remo-2026",
    "tirreno":     "tirreno-adriatico-2026",
    "strade":      "strade-bianche-2026",
    "denmark":     "postnord-tour-of-denmark-2026",
    "danmark":     "postnord-tour-of-denmark-2026",
}

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "maj": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dec": 12,
}

# JS-kode der kører i browseren og trækker alle programmer ud
EXTRACT_JS = """() => {
    const LOGO_MAP = {
        'max-logo.png':    'HBO Max',
        'kanal-5.svg':     'Discovery+',
        'eurosport-1.svg': 'Eurosport 1',
        'eurosport-2.svg': 'Eurosport 2',
        'tv2-sport.svg':   'TV 2 Sport',
        'tv2-sport-x.svg': 'TV 2 Sport X',
        'tv2-sport-2.svg': 'TV 2 Sport X',
        'tv-2-sport.svg':  'TV 2 Sport',
        'tv2play.svg':     'TV 2 Play',
        'gcn.svg':         'GCN+',
        'gcn-plus.svg':    'GCN+',
        'viaplay.svg':     'Viaplay',
        'dplay.svg':       'Discovery+',
    };
    const results = [];

    function parseTbodies(container, dateStr) {
        container.querySelectorAll('tbody').forEach(tbody => {
            const timeEl = tbody.querySelector('.tv-from b');
            const titleEl = tbody.querySelector('.race-title');
            if (!timeEl || !titleEl) return;
            const logos = [...tbody.querySelectorAll('.tv-logo')].map(el => {
                const m = el.style.backgroundImage.match(/tv-logos\\/([^"')\\s]+)/);
                return m ? m[1] : null;
            }).filter(Boolean);
            results.push({
                date: dateStr,
                time: timeEl.innerText.trim(),
                race: titleEl.innerText.replace(/\\s+/g, ' ').trim(),
                channels: logos.map(l => LOGO_MAP[l] || l)
            });
        });
    }

    // "I dag"-sektionen øverst
    const todayH2 = [...document.querySelectorAll('h2')]
        .find(h => h.innerText.includes('i dag'));
    if (todayH2) {
        let el = todayH2.nextElementSibling;
        while (el && el.tagName !== 'H2') {
            parseTbodies(el, 'I dag');
            el = el.nextElementSibling;
        }
    }

    // Kommende dage — .day-tr-holder.elem
    document.querySelectorAll('.day-tr-holder.elem').forEach(dayDiv => {
        const dateStr = dayDiv.innerText.trim();
        let sib = dayDiv.nextElementSibling;
        while (sib && !sib.classList.contains('day-tr-holder')) {
            parseTbodies(sib, dateStr);
            sib = sib.nextElementSibling;
        }
    });

    return results;
}"""


# ── Dato-parsing ──────────────────────────────────────────────────────────────

def parse_date(date_str: str) -> date | None:
    """'Tirsdag d. 26/05' eller 'I dag' → date."""
    today = date.today()
    if "i dag" in date_str.lower():
        return today
    m = re.search(r"(\d{1,2})/(\d{1,2})", date_str)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = today.year
        if month < today.month - 1:
            year += 1
        try:
            return date(year, month, day)
        except ValueError:
            pass
    return None


def parse_stage_number(race_str: str) -> int | None:
    """'Giro d'Italia [M] - 16. etape' → 16."""
    m = re.search(r"(\d+)\.\s*etape", race_str, re.IGNORECASE)
    if m:
        return int(m.group(1))
    if "prolog" in race_str.lower():
        return 0
    return None


def match_race_slug(race_str: str, race_slugs: set[str]) -> str | None:
    low = race_str.lower()
    for keyword, slug in RACE_KEYWORDS.items():
        if keyword in low:
            return slug if (slug and slug in race_slugs) else None
    return None


# ── Supabase helpers ──────────────────────────────────────────────────────────

def get_race_id(slug: str, cache: dict) -> str | None:
    if slug in cache:
        return cache[slug]
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?slug=eq.{slug}&select=id&limit=1",
        headers=AUTH,
    )
    race_id = res.json()[0]["id"] if (res.ok and res.json()) else None
    cache[slug] = race_id
    return race_id


def save_broadcast(entry: dict) -> bool:
    # Slet eksisterende entry for samme etape+kanal (tid kan have ændret sig)
    requests.delete(
        f"{SUPABASE_URL}/rest/v1/broadcast_schedule"
        f"?race_id=eq.{entry['race_id']}"
        f"&stage_number=eq.{entry['stage_number']}"
        f"&broadcaster=eq.{requests.utils.quote(entry['broadcaster'])}",
        headers=HEADERS,
    )
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/broadcast_schedule",
        json=entry,
        headers=HEADERS,
    )
    return res.ok


# ── Scraping ──────────────────────────────────────────────────────────────────

def scrape(dry_run: bool) -> None:
    print(f"tv_agent.py — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Kilde: {SOURCE_URL}\n")

    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?select=slug&limit=200", headers=AUTH
    )
    race_slugs = {r["slug"] for r in (res.json() if res.ok else [])}
    race_id_cache: dict[str, str | None] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 Klassementet/1.0"})
        print(f"Henter {SOURCE_URL} ...")
        page.goto(SOURCE_URL, wait_until="networkidle", timeout=30_000)
        time.sleep(2)
        programs = page.evaluate(EXTRACT_JS)
        browser.close()

    print(f"Fandt {len(programs)} programmer på siden\n")

    saved = skipped = 0
    for prog in programs:
        d = parse_date(prog["date"])
        if not d:
            skipped += 1
            continue

        stage_num = parse_stage_number(prog["race"])
        if stage_num is None:
            skipped += 1
            continue

        slug = match_race_slug(prog["race"], race_slugs)
        if not slug:
            skipped += 1
            continue

        race_id = get_race_id(slug, race_id_cache)
        if not race_id:
            skipped += 1
            continue

        start_time = f"{prog['time']}:00"
        date_str = d.isoformat()

        channels = prog["channels"]
        if not channels:
            skipped += 1
            continue

        for channel in channels:
            entry = {
                "race_id":        race_id,
                "stage_number":   stage_num,
                "broadcast_date": date_str,
                "start_time":     start_time,
                "broadcaster":    channel,
                "is_live":        True,
                "notes":          prog["race"],
            }
            print(f"  [{date_str}] E{stage_num:02d} {prog['time']} {channel}")
            if not dry_run:
                if save_broadcast(entry):
                    saved += 1
                else:
                    skipped += 1
            else:
                saved += 1

    if dry_run:
        print(f"\nDry-run: {saved} poster fundet (ikke gemt)")
    else:
        print(f"\nFærdig: {saved} gemt, {skipped} sprunget over")


# ── Manuel tilføjelse som fallback ────────────────────────────────────────────

def add_manual(race_slug: str, entries: list[dict]) -> None:
    """Tilføjer manuelle udsendelsestider — bruges som fallback."""
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?slug=eq.{race_slug}&select=id&limit=1",
        headers=AUTH,
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
            headers={**HEADERS, "Prefer": "resolution=merge-duplicates,return=minimal"},
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
    args = parser.parse_args()
    scrape(dry_run=args.dry_run)
