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
    "tt": "tt",
    "itt": "tt",
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
PCS_TO_DB_SLUG: dict[str, str] = {
    "vuelta-a-espana":  "la-vuelta-ciclista-a-espana",
    "paris-roubaix":    "paris-roubaix-hauts-de-france",
    "gent-wevelgem":    "in-flanders-fields-from-middelkerke-to-wevelgem",
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

                // Profil-billede URL — scan alle images
                const allImgs = [...document.querySelectorAll('img')];
                const profileImg = allImgs.find(img => img.src && img.src.includes('/profiles/'));
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


# ── Gem til DB ────────────────────────────────────────────────────────────────

def save_stages(race_id: str, stages: list[dict]) -> None:
    records = [{"race_id": race_id, **s} for s in stages]
    ok = sb_upsert("stages", records, "race_id,stage_number")
    if ok:
        print(f"  Gemt {len(records)} etaper i DB")


# ── Hovedprogram ──────────────────────────────────────────────────────────────

async def run(target_slug: str | None = None):
    slugs = [target_slug] if target_slug else PCS_RACE_SLUGS

    for pcs_slug in slugs:
        print(f"\n{'='*50}")
        print(f"Løb: {pcs_slug}")

        race_id = get_race_id(pcs_slug)
        if not race_id:
            print("  FEJL: Kunne ikke finde/oprette løb i DB")
            continue

        try:
            stages = await scrape_race_stages(pcs_slug)
        except Exception as e:
            print(f"  SCRAPE FEJL: {e}")
            import traceback
            traceback.print_exc()
            continue

        if stages:
            save_stages(race_id, stages)
        else:
            print("  Ingen etapedata (løbet er måske endags eller ikke annonceret endnu)")

    print("\n\nFærdig!")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(run(target))
