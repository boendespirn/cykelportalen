"""
hometown_agent.py
Scraper fødeby (Place of birth) fra PCS-rytterprofiler og klassificerer
til region via Claude (batch). Gemmer hometown + hometown_region i riders.

Kør: python hometown_agent.py --race giro-d-italia-2026
     python hometown_agent.py --race giro-d-italia-2026 --overwrite
"""

import os
import re
import sys
import io
import json
import asyncio
import argparse
import requests
import anthropic
from playwright.async_api import async_playwright
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")

CF_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

CONCURRENCY = 3

SB_AUTH = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}
SB_HEADERS = {
    **SB_AUTH,
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

_EXTRACT_JS = """() => {
    for (const li of document.querySelectorAll('ul.list li')) {
        const text = li.innerText || '';
        if (!text.includes('Place of birth')) continue;
        // Foretruk link-tekst (by-navn)
        const a = li.querySelector('a');
        if (a) return a.innerText.trim();
        // Fallback: tag alt efter ':'
        const m = text.match(/Place of birth[:\\s]+(.+)/i);
        return m ? m[1].trim() : null;
    }
    return null;
}"""


# ── Supabase ──────────────────────────────────────────────────────────────────

def get_race_startlist(race_slug: str, overwrite: bool) -> list[dict]:
    """Returnerer aktive ryttere i løbet med source_url."""
    race_res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?slug=eq.{race_slug}&select=id&limit=1",
        headers=SB_AUTH,
    )
    if not race_res.ok or not race_res.json():
        print(f"Løb ikke fundet: {race_slug}")
        return []
    race_id = race_res.json()[0]["id"]

    if overwrite:
        filter_part = ""
    else:
        filter_part = "&hometown=is.null"

    url = (
        f"{SUPABASE_URL}/rest/v1/startlists"
        f"?race_id=eq.{race_id}"
        f"&status=eq.active"
        f"&select=rider_id,riders(id,name,source_url,hometown)"
        f"&limit=200"
    )
    res = requests.get(url, headers=SB_AUTH)
    if not res.ok:
        print(f"DB fejl: {res.status_code}")
        return []

    riders = []
    for row in res.json():
        r = row.get("riders") or {}
        if not r.get("source_url"):
            continue
        if not overwrite and r.get("hometown"):
            continue
        riders.append({
            "id": r["id"],
            "name": r["name"],
            "source_url": r["source_url"],
        })
    return riders


def patch_rider(rider_id: str, hometown: str | None, region: str | None) -> None:
    data: dict = {}
    if hometown:
        data["hometown"] = hometown
    if region:
        data["hometown_region"] = region
    if not data:
        return
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/riders?id=eq.{rider_id}",
        json=data,
        headers=SB_HEADERS,
    )
    if not res.ok:
        print(f"  [DB FEJL] {res.status_code} {res.text[:120]}")


# ── PCS scraping ──────────────────────────────────────────────────────────────

async def scrape_hometown(browser, rider: dict) -> str | None:
    page = await browser.new_page(user_agent=CF_UA)
    try:
        await page.goto(rider["source_url"], wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(1500)
        title = await page.title()
        if any(s in title.lower() for s in ["just a moment", "403", "404", "access denied"]):
            return None
        result = await page.evaluate(_EXTRACT_JS)
        return result if isinstance(result, str) and result else None
    except Exception as e:
        print(f"    FEJL ({rider['name']}): {e}")
        return None
    finally:
        await page.close()


# ── Claude: by → region ───────────────────────────────────────────────────────

REGION_PROMPT = """You are given a list of cyclist hometowns (city names, sometimes with country).
For each, return the region/area using these rules:

Italy: return the Italian administrative region (e.g. "Lombardia", "Veneto", "Toscana", "Sicilia", "Abruzzo", "Piemonte", "Campania", "Emilia-Romagna", "Lazio", "Sardegna", "Puglia", "Calabria", "Liguria", "Friuli-Venezia Giulia", "Trentino-Alto Adige", "Valle d'Aosta", "Umbria", "Marche", "Molise", "Basilicata").

France: return the French administrative region (e.g. "Auvergne-Rhône-Alpes", "Provence-Alpes-Côte d'Azur", "Occitanie", "Nouvelle-Aquitaine", "Bretagne", "Normandie", "Île-de-France", "Grand Est", "Bourgogne-Franche-Comté", "Hauts-de-France", "Pays de la Loire", "Centre-Val de Loire", "Corse").

Switzerland: return the canton name in English (e.g. "Valais", "Graubünden", "Bern", "Vaud", "Ticino") or "Switzerland" if uncertain.

Other countries: return the country name in English (e.g. "Slovenia", "Spain", "Colombia", "Belgium", "Australia").
If unknown or uncertain, return null.

Return ONLY a JSON array matching the input order:
[{"name": "Rider Name", "hometown": "...", "region": "..." or null}, ...]

Input:"""


def classify_regions(riders_with_hometowns: list[dict]) -> dict[str, str]:
    """
    Kalder Claude med batches af ryttere+hjembyer.
    Returnerer {rider_id: region}.
    """
    if not riders_with_hometowns or not ANTHROPIC_KEY:
        return {}

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    result_map: dict[str, str] = {}
    batch_size = 25

    for i in range(0, len(riders_with_hometowns), batch_size):
        batch = riders_with_hometowns[i : i + batch_size]
        items = [{"name": r["name"], "hometown": r["hometown"]} for r in batch]
        prompt = REGION_PROMPT + "\n" + json.dumps(items, ensure_ascii=False)

        try:
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            parsed = json.loads(raw)

            for entry, rider in zip(parsed, batch):
                region = entry.get("region")
                if region:
                    result_map[rider["id"]] = region

        except Exception as e:
            print(f"  [Claude batch fejl]: {e}")

    return result_map


# ── Hoved ─────────────────────────────────────────────────────────────────────

async def run(race_slug: str, overwrite: bool) -> None:
    riders = get_race_startlist(race_slug, overwrite)
    total = len(riders)
    print(f"hometown_agent.py — {race_slug}")
    print(f"Fandt {total} ryttere der skal opdateres\n")

    if not riders:
        print("Ingen ryttere at opdatere.")
        return

    # Fase 1: Scraping
    hometown_map: dict[str, str] = {}  # rider_id → hometown

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        for batch_start in range(0, total, CONCURRENCY):
            batch = riders[batch_start : batch_start + CONCURRENCY]
            tasks = [scrape_hometown(browser, r) for r in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for rider, result in zip(batch, results):
                idx = batch_start + batch.index(rider) + 1
                if isinstance(result, Exception) or not result:
                    print(f"  [{idx}/{total}] {rider['name']} -> ingen by fundet")
                else:
                    hometown_map[rider["id"]] = result
                    print(f"  [{idx}/{total}] {rider['name']} -> {result}")

        await browser.close()

    print(f"\nFase 1 færdig: {len(hometown_map)}/{total} hjembyer fundet\n")

    if not hometown_map:
        return

    # Fase 2: Region-klassificering via Claude
    print("Klassificerer regioner med Claude...")
    to_classify = [
        {"id": rid, "name": next(r["name"] for r in riders if r["id"] == rid), "hometown": ht}
        for rid, ht in hometown_map.items()
    ]
    region_map = classify_regions(to_classify)
    print(f"Klassificerede {len(region_map)} regioner\n")

    # Fase 3: Gem i DB
    saved = 0
    for rider_id, hometown in hometown_map.items():
        region = region_map.get(rider_id)
        patch_rider(rider_id, hometown, region)
        saved += 1

    print(f"Færdig: {saved} ryttere opdateret med hjemby/region")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--race", required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.race, args.overwrite))
