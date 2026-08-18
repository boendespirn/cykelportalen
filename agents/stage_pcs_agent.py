"""
stage_pcs_agent.py
Scraper etapedata fra ProCyclingStats for UCI WorldTour-løb.
Bruger Playwright pga. Cloudflare-beskyttelse.

Krav: pip install playwright && playwright install chromium

Kør for ét løb:
  python stage_pcs_agent.py giro-d-italia
  python stage_pcs_agent.py tour-de-france

Kør for alle løb i listen:
  python stage_pcs_agent.py
"""

import os
import re
import sys
import io
import asyncio
import requests
from datetime import datetime
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
BASE_URL = "https://www.procyclingstats.com"
YEAR = 2026

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}

# PCS stage type icon class → vores DB-type
PROFILE_TYPE_MAP = {
    "p1": "flat",
    "p2": "hilly",
    "p3": "hilly",
    "p4": "mountain",
    "p5": "mountain",
    "p6": "mountain",
    "tt":  "tt",
    "itt": "itt",
    "ttt": "ttt",
}

# Løb der skal opdateres — tilføj flere ved behov
PCS_RACE_SLUGS = [
    "giro-d-italia",
    "tour-de-france",
    "vuelta-a-espana",
    "paris-nice",
    "tirreno-adriatico",
    "volta-a-catalunya",
    "criterium-du-dauphine",
    "tour-de-romandie",
    "tour-de-suisse",
    "tour-de-france-femmes",
    "tour-de-pologne",
    "tour-de-hongrie",
]


# ── Supabase helpers ─────────────────────────────────────────────────────────

def sb_get(table: str, params: str) -> list:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}?{params}",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
    )
    return res.json() if res.ok else []


def sb_upsert(table: str, records: list, conflict: str) -> bool:
    if not records:
        return True
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={conflict}",
        json=records,
        headers=SUPABASE_HEADERS,
    )
    if not res.ok:
        print(f"  [DB FEJL] {table}: {res.status_code} — {res.text[:300]}")
    return res.ok


# PCS-slug → vores DB-slug (når de afviger)
# Hardcoded start/finish cities for one-day classics (PCS main page never shows departure/arrival)
ONEDAY_CITIES: dict[str, tuple[str, str]] = {
    "omloop-het-nieuwsblad":           ("Gent",          "Ninove"),
    "strade-bianche":                  ("Siena",          "Siena"),
    "milan-san-remo":                  ("Milano",         "San Remo"),
    "e3-saxo-bank-classic":            ("Harelbeke",      "Harelbeke"),
    "ronde-van-brugge":                ("Brugge",         "Brugge"),
    "gent-wevelgem":                   ("Deinze",         "Wevelgem"),
    "dwars-door-vlaanderen":           ("Roeselare",      "Waregem"),
    "tour-of-flanders":                ("Brugge",         "Oudenaarde"),
    "paris-roubaix":                   ("Compiègne",      "Roubaix"),
    "amstel-gold-race":                ("Maastricht",     "Valkenburg"),
    "la-fleche-wallonne":              ("Charleroi",      "Huy"),
    "liege-bastogne-liege":            ("Liège",          "Liège"),
    "eschborn-frankfurt":              ("Eschborn",       "Frankfurt am Main"),
    "il-lombardia":                    ("Como",           "Bergamo"),
    "donostia-san-sebastian":          ("San Sebastián",  "San Sebastián"),
    "cyclassics-hamburg":              ("Hamburg",        "Hamburg"),
    "bretagne-classic":                ("Brest",          "Brest"),
    "grand-prix-cycliste-de-quebec":   ("Québec City",    "Québec City"),
    "grand-prix-cycliste-de-montreal": ("Montréal",       "Montréal"),
    "cadel-evans-great-ocean-road-race": ("Geelong",      "Geelong"),
    "tour-down-under":                 ("Adelaide",       "Adelaide"),
    "copenhagen-sprint":               ("Copenhagen",     "Copenhagen"),
}

PCS_TO_DB_SLUG: dict[str, str] = {
    "vuelta-a-espana":          "la-vuelta-ciclista-a-espana",
    "paris-roubaix":            "paris-roubaix-hauts-de-france",
    "gent-wevelgem":            "in-flanders-fields-from-middelkerke-to-wevelgem",
    "bretagne-classic":         "bretagne-classic-cic",
    "cyclassics-hamburg":       "adac-cyclassics",
    "san-sebastian":            "dssk-donostia-san-sebastian-klasikoa",
    "gp-quebec":                "grand-prix-cycliste-de-quebec",
    "gp-montreal":              "grand-prix-cycliste-de-montreal",
    "tour-of-flanders":         "ronde-van-vlaanderen",
    "omloop-het-nieuwsblad":    "omloop-nieuwsblad",
    "cadel-evans-great-ocean-road-race": "mapei-cadel-evans-great-ocean-road-race-men",
    "tour-down-under":          "santos-tour-down-under",
    "milan-san-remo":           "milano-sanremo",
    "tour-auvergne-rhone-alpes":  "criterium-du-dauphine",
    "dwars-door-vlaanderen":      "dwars-door-vlaanderen-a-travers-la-flandre",
    "e3-saxo-bank-classic":       "e3-saxo-classic",
    "ronde-van-brugge":           "ronde-van-brugge-tour-of-bruges",
}


def get_race_id(pcs_slug: str) -> str | None:
    db_base = PCS_TO_DB_SLUG.get(pcs_slug, pcs_slug)
    our_slug = f"{db_base}-{YEAR}"
    rows = sb_get("races", f"slug=eq.{our_slug}&select=id&limit=1")
    if rows:
        return rows[0]["id"]

    # Opret løbet med minimal data
    record = {
        "name": pcs_slug.replace("-", " ").title(),
        "slug": our_slug,
        "category": "UCI WorldTour",
        "start_date": f"{YEAR}-01-01",
        "pcs_url": f"{BASE_URL}/race/{pcs_slug}/{YEAR}",
        "source": "pcs",
    }
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/races?on_conflict=slug",
        json=[record],
        headers=SUPABASE_HEADERS,
    )
    if res.ok:
        rows = sb_get("races", f"slug=eq.{our_slug}&select=id&limit=1")
        return rows[0]["id"] if rows else None
    return None


# ── Parse helpers ─────────────────────────────────────────────────────────────

def parse_date_pcs(text: str) -> str | None:
    """Konverterer PCS-dato 'dd Month yyyy' til ISO-format."""
    text = text.strip()
    for fmt in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def extract_info(pairs: list[dict]) -> dict:
    """Parser liste af {title, value} par til et dict med nøgledata."""
    info: dict = {}
    for i, item in enumerate(pairs):
        label = item.get("title", "").lower()
        value = item.get("value", "").strip()
        if not value:
            continue
        if "distance" in label:
            m = re.search(r"[\d.]+", value)
            if m:
                info["distance_km"] = float(m.group())
        elif "vertical" in label or "elevation" in label:
            m = re.search(r"\d+", value)
            if m:
                info["elevation_gain_m"] = int(m.group())
        elif "profile" in label and "score" in label:
            m = re.search(r"\d+", value)
            if m:
                info["profile_score"] = int(m.group())
        elif "departure" in label:
            info["start_location"] = value
        elif "arrival" in label:
            info["finish_location"] = value
        elif "date" in label and ":" in label:
            info["date"] = parse_date_pcs(value)

    return info


# ── Playwright scraper ────────────────────────────────────────────────────────

async def scrape_race_stages(pcs_slug: str) -> list[dict]:
    """
    Scraper alle etaper for ét løb fra PCS.
    Bruger en ny browserside per etape for at undgå Cloudflare-detektion
    (PCS blokerer navigationer fra race-oversigt til stage-sider).
    """
    from playwright.async_api import async_playwright

    stages = []
    CF_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        for stage_num in range(1, 30):
            url = f"{BASE_URL}/race/{pcs_slug}/{YEAR}/stage-{stage_num}"
            print(f"    Etape {stage_num}: {url}")

            # Ny side per etape — undgår Cloudflare session-tracking
            page = await browser.new_page(user_agent=CF_UA)

            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2500)

            page_title = await page.title()

            # Stop ved 404, Cloudflare-challenge eller "not found"
            if ("not found" in page_title.lower() or "404" in page_title
                    or "just a moment" in page_title.lower()):
                await page.close()
                if "just a moment" in page_title.lower():
                    print(f"    Cloudflare-challenge pa etape {stage_num} — afbryder")
                else:
                    print(f"    Etape {stage_num} ikke fundet — fardigt")
                break

            await page.evaluate("document.querySelectorAll('[id*=cmp],[class*=cmpbox]').forEach(e=>e.remove())")

            # Udtræk data via JavaScript
            stage_data = await page.evaluate("""() => {
                const result = {};

                // Titel: "Stage 1   »   Nessebar  ›  Burgas   (147km)"
                const titleEl = document.querySelector('.titleCont, .page-title');
                result.title = titleEl ? titleEl.innerText.trim() : '';

                // Profil-billede URL — scan alle images under /profiles/, men vælg
                // KUN dem, der faktisk er højdeprofilen. PCS-siderne indeholder også
                // rutekort ('-map-') og mål-zoom ('-final-km-') under samme sti, og
                // DOM-rækkefølgen varierer pr. etape, så et simpelt "første match"
                // kan gribe det forkerte billede (bug: TdF 2026 etape 1/2/3/12 fik map/
                // final-km i stedet for højdeprofilen).
                const allImgs = [...document.querySelectorAll('img')];
                const profileCandidates = allImgs.filter(img => img.src && img.src.includes('/profiles/'));
                const isElevationProfile = (src) => {
                    const fname = src.split('/').pop();
                    return (fname.includes('profile') || fname.includes('sprint'))
                        && !fname.includes('final-km')
                        && !fname.includes('map');
                };
                const profileImg = profileCandidates.find(img => isElevationProfile(img.src));
                result.elevation_image_url = profileImg ? profileImg.src : null;

                // Stage type fra icon class (p1, p2, ... p6, tt)
                const iconEl = document.querySelector('span.icon.profile');
                result.icon_class = iconEl ? iconEl.className : '';

                // Race info pairs — find container via nøgleord, derefter sekvensielt scan
                const pairs = [];
                const allTitleEls = [...document.querySelectorAll('.title')];

                // Find info-containeren ved at lokalisere et .title-element med 'Distance' eller 'Date'
                let infoContainer = null;
                for (const t of allTitleEls) {
                    const txt = t.innerText.trim();
                    if (txt.includes('Distance') || txt.includes('Departure') || txt.includes('Date:')) {
                        // Gå op til nærmeste container
                        infoContainer = t.closest('.borderbox, .right, .left, section, article, form')
                                     || t.parentElement?.parentElement;
                        break;
                    }
                }

                if (infoContainer) {
                    const els = [...infoContainer.querySelectorAll('.title, .value')];
                    let pendingTitle = null;
                    for (const el of els) {
                        const cls = [...el.classList];
                        if (cls.includes('title')) {
                            pendingTitle = el.innerText.trim();
                        } else if (cls.includes('value') && pendingTitle !== null) {
                            pairs.push({ title: pendingTitle, value: el.innerText.trim() });
                            pendingTitle = null;
                        }
                    }
                }

                result.pairs = pairs;
                return result;
            }""")

            # Stop hvis siden ikke indeholder etapedata (PCS serverer tomme sider for ikke-eksisterende etaper)
            title_text = stage_data.get("title", "")
            if not stage_data or not stage_data.get("elevation_image_url") and not stage_data.get("pairs"):
                await page.close()
                print(f"    Ingen etapedata pa {stage_num} — fardigt")
                break

            # Parse stage type fra icon class
            icon_class = stage_data.get("icon_class", "")
            stage_type = None
            for cls in icon_class.split():
                if cls in PROFILE_TYPE_MAP:
                    stage_type = PROFILE_TYPE_MAP[cls]
                    break

            # Parse info fra pairs
            info = extract_info(stage_data.get("pairs", []))

            # Fallback: parse titel for start/finish og distance
            if not info.get("start_location") or not info.get("finish_location"):
                # "Stage 1   »   Nessebar  ›  Burgas   (147km)"
                route_m = re.search(r"»\s*(.+?)\s*›\s*(.+?)\s*\(", title_text)
                if route_m:
                    info.setdefault("start_location", route_m.group(1).strip())
                    info.setdefault("finish_location", route_m.group(2).strip())

            if not info.get("distance_km"):
                dist_m = re.search(r"\((\d+(?:\.\d+)?)\s*km\)", title_text)
                if dist_m:
                    info["distance_km"] = float(dist_m.group(1))

            stage_name = f"Etape {stage_num}"
            if info.get("start_location") and info.get("finish_location"):
                stage_name = f"{info['start_location']} – {info['finish_location']}"

            has_img = bool(stage_data.get("elevation_image_url"))
            print(f"      OK {stage_name} | {info.get('distance_km','?')}km | +{info.get('elevation_gain_m','?')}m | {stage_type or '?'} | img:{has_img}")

            stages.append({
                "stage_number": stage_num,
                "name": stage_name,
                "date": info.get("date"),
                "distance_km": info.get("distance_km"),
                "start_location": info.get("start_location"),
                "finish_location": info.get("finish_location"),
                "elevation_gain_m": info.get("elevation_gain_m"),
                "profile_score": info.get("profile_score"),
                "stage_type": stage_type,
                "elevation_image_url": stage_data.get("elevation_image_url"),
                "pcs_stage_url": url,
                "source": "pcs",
                "source_url": url,
            })

            await page.close()

        await browser.close()

    print(f"  Scraped {len(stages)} etaper")
    return stages


# ── One-day race scraper ──────────────────────────────────────────────────────

async def scrape_oneday_race(pcs_slug: str) -> list[dict]:
    """
    Scraper profil og ruteinformation for et endagsløb fra PCS-løbets hovedside.
    URL: /race/{slug}/{year}  (ingen /stage-N)
    """
    from playwright.async_api import async_playwright

    url = f"{BASE_URL}/race/{pcs_slug}/{YEAR}"
    print(f"    One-day: {url}")
    CF_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=CF_UA)
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2500)

        page_title = await page.title()
        if ("not found" in page_title.lower() or "404" in page_title
                or "just a moment" in page_title.lower()):
            await browser.close()
            print(f"    Ingen data (404 eller Cloudflare)")
            return []

        await page.evaluate("document.querySelectorAll('[id*=cmp],[class*=cmpbox]').forEach(e=>e.remove())")

        race_data = await page.evaluate("""() => {
            const result = {};

            const titleEl = document.querySelector('.titleCont, .page-title, h1');
            result.title = titleEl ? titleEl.innerText.trim() : '';

            // Se kommentar i scrape_race_stages() — vælg kun ægte højdeprofil-billeder,
            // ikke rutekort ('-map-') eller mål-zoom ('-final-km-').
            const allImgs = [...document.querySelectorAll('img')];
            const profileCandidates = allImgs.filter(img => img.src && img.src.includes('/profiles/'));
            const isElevationProfile = (src) => {
                const fname = src.split('/').pop();
                return (fname.includes('profile') || fname.includes('sprint'))
                    && !fname.includes('final-km')
                    && !fname.includes('map');
            };
            const profileImg = profileCandidates.find(img => isElevationProfile(img.src));
            result.elevation_image_url = profileImg ? profileImg.src : null;

            const iconEl = document.querySelector('span.icon.profile');
            result.icon_class = iconEl ? iconEl.className : '';

            // Global scan — PCS main race page has title/value pairs spread across DOM
            const pairs = [];
            const allEls = [...document.querySelectorAll('.title, .value')];
            let pendingTitle = null;
            for (const el of allEls) {
                if (el.classList.contains('title')) {
                    pendingTitle = el.innerText.trim();
                } else if (el.classList.contains('value') && pendingTitle !== null) {
                    pairs.push({ title: pendingTitle, value: el.innerText.trim() });
                    pendingTitle = null;
                }
            }
            result.pairs = pairs;
            return result;
        }""")

        await browser.close()

    if not race_data or (not race_data.get("elevation_image_url") and not race_data.get("pairs")):
        # PCS har ikke annonceret løbet endnu — gem stadig byer fra hardkodet dict
        if pcs_slug in ONEDAY_CITIES:
            start_city, finish_city = ONEDAY_CITIES[pcs_slug]
            print(f"    Ingen profildata — hardkodet: {start_city} – {finish_city}")
            return [{
                "stage_number": 1,
                "name": f"{start_city} – {finish_city}",
                "start_location": start_city,
                "finish_location": finish_city,
                "source": "pcs",
                "source_url": url,
            }]
        print("    Ingen profildata på siden")
        return []

    icon_class = race_data.get("icon_class", "")
    stage_type = None
    for cls in icon_class.split():
        if cls in PROFILE_TYPE_MAP:
            stage_type = PROFILE_TYPE_MAP[cls]
            break

    title_text = race_data.get("title", "")
    info = extract_info(race_data.get("pairs", []))

    # Fallback: hardcoded cities (PCS main page never shows departure/arrival for one-day races)
    if not info.get("start_location") or not info.get("finish_location"):
        if pcs_slug in ONEDAY_CITIES:
            start_city, finish_city = ONEDAY_CITIES[pcs_slug]
            info.setdefault("start_location", start_city)
            info.setdefault("finish_location", finish_city)

    if not info.get("distance_km"):
        dist_m = re.search(r"\((\d+(?:\.\d+)?)\s*km\)", title_text)
        if dist_m:
            info["distance_km"] = float(dist_m.group(1))

    has_img = bool(race_data.get("elevation_image_url"))
    stage_name = f"{info['start_location']} – {info['finish_location']}" if info.get("start_location") and info.get("finish_location") else pcs_slug.replace("-", " ").title()
    print(f"      OK {stage_name} | {info.get('distance_km','?')}km | +{info.get('elevation_gain_m','?')}m | {stage_type or '?'} | img:{has_img}")

    return [{
        "stage_number": 1,
        "name": stage_name,
        "date": info.get("date"),
        "distance_km": info.get("distance_km"),
        "start_location": info.get("start_location"),
        "finish_location": info.get("finish_location"),
        "elevation_gain_m": info.get("elevation_gain_m"),
        "profile_score": info.get("profile_score"),
        "stage_type": stage_type,
        "elevation_image_url": race_data.get("elevation_image_url"),
        "pcs_stage_url": url,
        "source": "pcs",
        "source_url": url,
    }]


# ── Gem til DB ────────────────────────────────────────────────────────────────

def get_generated_stage_numbers(race_id: str) -> set[int]:
    """Etapenumre hvis højdeprofil VI selv har genereret (stage_profile_generator.py)."""
    rows = sb_get(
        "stages",
        f"race_id=eq.{race_id}&elevation_image_source=eq.generated&select=stage_number",
    )
    return {r["stage_number"] for r in rows if r.get("stage_number") is not None}


def strip_generated_image_urls(records: list[dict], protected: set[int]) -> int:
    """Fjern elevation_image_url fra etaper med egengenereret profil (in-place).

    Rør ALDRIG en etape, hvis profil vi selv har genereret. Upserten skriver
    kun elevation_image_url og lader elevation_image_source stå — uden dette
    filter ville en genkørsel erstatte vores eget PNG med en PCS-URL, mens
    source stadig sagde "generated". Frontenden gater netop på
    source === "generated" (LEG-001), så resultatet blev et PCS-billede vist
    som vores eget — og da PCS svarer 403 på hotlinks, kunne det slet ikke
    indlæses (STG-030, ramte 20 af 21 Vuelta 2026-etaper).

    Samme beskyttelse som pcs_profile_image_agent.py's get_stages() allerede
    har; den manglede kun her i trin 2 af race_prep_pipeline.py.

    Returnerer antal rækker der blev beskyttet.
    """
    stripped = 0
    for record in records:
        if record.get("stage_number") in protected and "elevation_image_url" in record:
            record.pop("elevation_image_url")
            stripped += 1
    return stripped


def save_stages(race_id: str, stages: list[dict]) -> None:
    records = []
    for s in stages:
        record = {"race_id": race_id, **s}
        # Udelad elevation_image_url fra upsert-payloaden når PCS ikke fandt
        # noget denne kørsel (None) — merge-duplicates SÆTTER ellers kolonnen
        # til NULL for alle felter i payloaden, hvilket ville overskrive et
        # eksisterende billede (fx et selv-genereret fallback-billede fra
        # stage_profile_generator.py, se STG-002) med intet, hver gang PCS
        # stadig mangler profilet. Kolonner der udelades fra payloaden
        # bevares uændret af PostgREST's merge-duplicates.
        if record.get("elevation_image_url") is None:
            record.pop("elevation_image_url", None)
        records.append(record)

    # ...og udelad den ligeledes for etaper, hvor VI selv har genereret
    # profilen — ellers overskriver PCS-URL'en vores eget billede, mens
    # elevation_image_source stadig siger "generated" (STG-030).
    protected = strip_generated_image_urls(records, get_generated_stage_numbers(race_id))
    if protected:
        print(f"  Bevarer {protected} egengenereret profilbillede(r) "
              f"(elevation_image_source='generated')")

    # PostgREST kræver identisk nøglesæt på tværs af ALLE objekter i én
    # batch-POST ("All object keys must match", PGRST102) — ellers afvises
    # HELE batchen, stille, uden at nogen af etaperne bliver gemt (STG-022).
    # Da nogle rækker mangler elevation_image_url-nøglen (se ovenfor) og
    # andre ikke, splitter vi i homogene sub-batches efter nøglesæt i stedet
    # for én blandet batch.
    saved = 0
    by_keyset: dict[tuple, list[dict]] = {}
    for record in records:
        by_keyset.setdefault(tuple(sorted(record.keys())), []).append(record)
    all_ok = True
    for batch in by_keyset.values():
        ok = sb_upsert("stages", batch, "race_id,stage_number")
        all_ok = all_ok and ok
        if ok:
            saved += len(batch)
    if all_ok:
        print(f"  Gemt {saved} etaper i DB")
    else:
        print(f"  Gemt {saved}/{len(records)} etaper i DB (én eller flere sub-batches fejlede — se [DB FEJL] ovenfor)")


# ── Hovedprogram ──────────────────────────────────────────────────────────────

async def run(target_slug: str | None = None, oneday: bool = False):
    slugs = [target_slug] if target_slug else PCS_RACE_SLUGS

    for pcs_slug in slugs:
        print(f"\n{'='*50}")
        print(f"Løb: {pcs_slug} {'[endagsløb]' if oneday else ''}")

        race_id = get_race_id(pcs_slug)
        if not race_id:
            print("  FEJL: Kunne ikke finde/oprette løb i DB")
            continue

        try:
            if oneday:
                stages = await scrape_oneday_race(pcs_slug)
            else:
                stages = await scrape_race_stages(pcs_slug)
        except Exception as e:
            print(f"  SCRAPE FEJL: {e}")
            import traceback
            traceback.print_exc()
            continue

        if stages:
            save_stages(race_id, stages)
        else:
            print("  Ingen profildata (løbet er endnu ikke annonceret på PCS)")

    print("\n\nFærdig!")


if __name__ == "__main__":
    import argparse as _ap
    p = _ap.ArgumentParser()
    p.add_argument("slug", nargs="?", default=None)
    p.add_argument("--oneday", action="store_true", help="Scraper løbets hovedside (endagsløb)")
    p.add_argument("--year", type=int, default=YEAR, help="Sæsonår, fx 2023 (default: indeværende sæson)")
    args = p.parse_args()
    YEAR = args.year
    asyncio.run(run(args.slug, oneday=args.oneday))
