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
    "6eren.svg":       "6'eren",
}

# Nøgleord i løbstitel → DB slug (opdater ved ny sæson)
RACE_KEYWORDS = {
    "giro":        "giro-d-italia-2026",
    "tour de fra": "tour-de-france-2026",
    "vuelta":      "la-vuelta-ciclista-a-espana-2026",
    "flandern":    "ronde-van-vlaanderen-2026",
    "roubaix":     "paris-roubaix-hauts-de-france-2026",
    "liège":       "liege-bastogne-liege-2026",
    "liege":       "liege-bastogne-liege-2026",
    "amstel":      "amstel-gold-race-2026",
    "dauphine":    "criterium-du-dauphine-2026",
    "auvergne":    "criterium-du-dauphine-2026",
    "schweiz":     "tour-de-suisse-2026",
    "suisse":      "tour-de-suisse-2026",
    "lombardia":   "il-lombardia-2026",
    "san remo":    "milano-sanremo-2026",
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
        '6eren.svg':       "6'eren",
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


def parse_stage_number(race_str: str, oneday: bool = False) -> int | None:
    """'Giro d'Italia [M] - 16. etape' → 16.

    Et ENDAGSLØB har intet etapenummer i programtitlen — der står bare
    "Il Lombardia [M]". Før 2026-10-06 returnerede funktionen None på dem, og
    kaldstedet kasserede programmet. Det betød, at tv_agent aldrig kunne gemme
    en sending for et endagsløb overhovedet: 2026-10-06 fandt den 12 programmer
    og gemte 0, fordi oktober kun rummer endagsløb. Vores database modellerer
    et endagsløb som etape 1, så det er dét, vi returnerer.
    """
    m = re.search(r"(\d+)\.\s*etape", race_str, re.IGNORECASE)
    if m:
        return int(m.group(1))
    if "prolog" in race_str.lower():
        return 0
    return 1 if oneday else None


def match_race_slug(race_str: str, race_slugs: set[str]) -> str | None:
    low = race_str.lower()
    for keyword, slug in RACE_KEYWORDS.items():
        if keyword in low:
            return slug if (slug and slug in race_slugs) else None
    return None


# ── Supabase helpers ──────────────────────────────────────────────────────────

def _pent_kanalnavn(raa: str, ukendte: set[str]) -> str:
    """Kanalnavnet, som det skal staa paa sitet.

    LOGO_MAP oversaetter logo-filnavnet til et visningsnavn, men faldt foer
    tilbage til det RAA filnavn, naar et logo ikke stod i kortet. 2026-10-06 var
    "6eren.svg" paa vej i databasen som kanalnavn. Vi fjerner derfor endelsen,
    saa en manglende post aldrig kan vise en filsti paa sitet — og raaber op om
    den, saa kortet kan udvides i stedet for at degradere stille.
    """
    if not raa.lower().endswith((".svg", ".png", ".jpg", ".jpeg", ".webp")):
        return raa
    ukendte.add(raa)
    return raa.rsplit(".", 1)[0].replace("-", " ").strip()


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

    # limit=1000, ikke 200: databasen rummer over 200 loeb, og med det gamle
    # loft kunne et loeb falde uden for listen og blive tavst kasseret af
    # match_race_slug(). Vi henter ogsaa race_type, fordi etapenummeret for et
    # endagsloeb ikke staar i programtitlen og maa udledes af loebstypen.
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?select=slug,race_type&limit=1000", headers=AUTH
    )
    raekker = res.json() if res.ok else []
    race_slugs = {r["slug"] for r in raekker}
    # Begge stavemaader findes i kolonnen ("oneday" fra 2026, "one_day" foer).
    oneday_slugs = {r["slug"] for r in raekker
                    if (r.get("race_type") or "").startswith("one")}
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
    # Hvorfor et program blev kasseret, samles op og skrives til sidst.
    # "0 gemt, 12 sprunget over" uden en grund er praecis den tavse fejl,
    # run_validator.py blev bygget for at fange (tv_agent, 2026-09-09) — og den
    # gentog sig 2026-10-06, hvor samtlige 12 programmer var endagsloeb. Naar
    # agenten selv siger hvorfor, staar svaret i loggen med det samme.
    grunde: dict[str, list[str]] = {}
    ukendte_logoer: set[str] = set()

    def spring_over(grund: str, prog: dict) -> None:
        nonlocal skipped
        skipped += 1
        grunde.setdefault(grund, []).append(prog.get("race", "?"))

    for prog in programs:
        d = parse_date(prog["date"])
        if not d:
            spring_over("ulaeselig dato", prog)
            continue

        # Loebet foerst: uden at vide HVILKET loeb det er, kan vi ikke afgoere,
        # om en manglende "N. etape" betyder "endagsloeb" eller "uforstaaelig".
        slug = match_race_slug(prog["race"], race_slugs)
        if not slug:
            spring_over("loebet kendes ikke (se RACE_KEYWORDS)", prog)
            continue

        stage_num = parse_stage_number(prog["race"], oneday=slug in oneday_slugs)
        if stage_num is None:
            spring_over("intet etapenummer, og loebet er ikke et endagsloeb", prog)
            continue

        race_id = get_race_id(slug, race_id_cache)
        if not race_id:
            spring_over("loebet findes ikke i databasen", prog)
            continue

        start_time = f"{prog['time']}:00"
        date_str = d.isoformat()

        channels = [_pent_kanalnavn(c, ukendte_logoer) for c in prog["channels"]]
        if not channels:
            spring_over("ingen kanal angivet", prog)
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
                    spring_over("databasen afviste raekken", prog)
            else:
                saved += 1

    if dry_run:
        print(f"\nDry-run: {saved} poster fundet (ikke gemt)")
    else:
        print(f"\nFærdig: {saved} gemt, {skipped} sprunget over")
    if ukendte_logoer:
        print("\nUkendte TV-logoer — tilfoej dem i LOGO_MAP (begge kopier):")
        for logo in sorted(ukendte_logoer):
            print(f"  {logo}")
    if grunde:
        print("\nSprunget over, fordelt på grund:")
        for grund, loeb in sorted(grunde.items(), key=lambda kv: -len(kv[1])):
            print(f"  {len(loeb):>3}x  {grund}")
            for navn in sorted(set(loeb))[:4]:
                print(f"         - {navn}")


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
