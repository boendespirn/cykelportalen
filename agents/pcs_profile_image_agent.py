"""
pcs_profile_image_agent.py
Henter bedre elevation profile billeder fra PCS /info/profiles sider.
Finder den officielle/store altimetria-URL og opdaterer stages.elevation_image_url.

Kør: python pcs_profile_image_agent.py --race tour-de-france-2026
     python pcs_profile_image_agent.py --race criterium-du-dauphine-2026 --overwrite
"""

import os
import sys
import io
import asyncio
import argparse
import requests
from playwright.async_api import async_playwright
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
CONCURRENCY = 3
DELAY_MS = 1500

SB_AUTH = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}
SB_HEADERS = {
    **SB_AUTH,
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

# Forsøger at finde profilbilledet fra PCS /info/profiles siden.
# PCS-profilsider har typisk en stor <img> med profilbilledet i .content eller lignende.
EXTRACT_JS = """() => {
    const imgs = Array.from(document.querySelectorAll('img'));
    // Prioritér officielle race-billeder (ASO, RCS, etc.) og PCS's egne profiler
    const candidates = imgs
        .map(i => i.src || '')
        .filter(s => s && (
            s.includes('profile') ||
            s.includes('altimetri') ||
            s.includes('letour') ||
            s.includes('tdf') ||
            s.includes('procyclingstats.com/images')
        ))
        .filter(s => !s.includes('icon') && !s.includes('logo') && !s.includes('thumb'));

    // Foretruk den største: check naturalWidth hvis muligt
    let best = null;
    let bestW = 0;
    for (const img of imgs) {
        const s = img.src || '';
        if (!candidates.includes(s)) continue;
        const w = img.naturalWidth || 0;
        if (w > bestW) { bestW = w; best = s; }
    }
    if (best) return best;
    return candidates[0] || null;
}"""


def get_stages(race_slug: str, overwrite: bool) -> list[dict]:
    race = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?slug=eq.{race_slug}&select=id&limit=1",
        headers=SB_AUTH,
    ).json()
    if not race:
        print(f"Løb ikke fundet: {race_slug}")
        return []
    race_id = race[0]["id"]
    stages = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages"
        f"?race_id=eq.{race_id}&pcs_stage_url=not.is.null"
        f"&select=id,stage_number,pcs_stage_url,elevation_image_url"
        f"&order=stage_number.asc",
        headers=SB_AUTH,
    ).json()
    if not overwrite:
        # Kun etaper der ikke allerede har et high-res billede (> 500px bredde i URL typisk)
        # Vi kører altid overwrite for at opdatere til bedste version
        pass
    return stages if isinstance(stages, list) else []


async def scrape_one(browser, stage: dict, sem: asyncio.Semaphore) -> tuple[str, int, str | None]:
    profile_url = stage["pcs_stage_url"] + "/info/profiles"
    async with sem:
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        page = await ctx.new_page()
        try:
            await page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(DELAY_MS)
            img_url = await page.evaluate(EXTRACT_JS)
            return stage["id"], stage["stage_number"], img_url
        except Exception as e:
            print(f"  [Fejl] E{stage['stage_number']}: {e}")
            return stage["id"], stage["stage_number"], None
        finally:
            await ctx.close()


async def run(race_slug: str, overwrite: bool) -> None:
    stages = get_stages(race_slug, overwrite)
    if not stages:
        return

    print(f"pcs_profile_image_agent — {race_slug}")
    print(f"Behandler {len(stages)} etaper\n")

    sem = asyncio.Semaphore(CONCURRENCY)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        results = await asyncio.gather(*[scrape_one(browser, s, sem) for s in stages])
        await browser.close()

    updated = 0
    for stage_id, n, img_url in sorted(results, key=lambda x: x[1]):
        stage = next(s for s in stages if s["id"] == stage_id)
        old_url = stage.get("elevation_image_url") or ""
        if img_url and img_url != old_url:
            res = requests.patch(
                f"{SUPABASE_URL}/rest/v1/stages?id=eq.{stage_id}",
                json={"elevation_image_url": img_url},
                headers=SB_HEADERS,
            )
            status = "✓ opdateret" if res.ok else f"DB fejl {res.status_code}"
            print(f"E{n}: {status}")
            print(f"     {img_url}")
            if res.ok:
                updated += 1
        elif img_url == old_url:
            print(f"E{n}: uændret (samme URL)")
        else:
            print(f"E{n}: ingen bedre billede fundet")

    print(f"\nFærdig: {updated}/{len(stages)} opdateret")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--race", required=True, help="DB-slug for løbet")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.race, args.overwrite))
