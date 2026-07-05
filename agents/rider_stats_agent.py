"""
rider_stats_agent.py
Scraper vægt og højde fra PCS-rytterprofiler.
Kør: python rider_stats_agent.py --race giro-d-italia-2026
     python rider_stats_agent.py --all   (alle ryttere i DB)
"""

import os
import re
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

CF_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
CONCURRENCY = 4

SB_AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
SB_HEADERS = {**SB_AUTH, "Content-Type": "application/json", "Prefer": "return=minimal"}

_EXTRACT_JS = """() => {
    let weight = null, height = null;
    for (const li of document.querySelectorAll('ul.list li')) {
        const text = li.innerText || '';
        if (text.includes('Weight')) {
            const m = text.match(/(\\d{2,3})\\s*kg/i);
            if (m) weight = parseInt(m[1]);
        }
        if (text.includes('Height')) {
            const m = text.match(/(1[.,]\\d+)\\s*m/i);
            if (m) height = Math.round(parseFloat(m[1].replace(',', '.')) * 100);
        }
    }
    return [weight, height];
}"""


def get_riders(race_slug: str | None) -> list[dict]:
    if race_slug:
        race_res = requests.get(
            f"{SUPABASE_URL}/rest/v1/races?slug=eq.{race_slug}&select=id&limit=1",
            headers=SB_AUTH,
        )
        if not race_res.ok or not race_res.json():
            return []
        race_id = race_res.json()[0]["id"]
        url = (
            f"{SUPABASE_URL}/rest/v1/startlists"
            f"?race_id=eq.{race_id}&status=eq.active"
            f"&select=riders(id,name,source_url,weight_kg,height_cm)"
            f"&limit=200"
        )
        rows = requests.get(url, headers=SB_AUTH).json()
        return [
            row["riders"] for row in rows
            if row.get("riders") and row["riders"].get("source_url")
            and not (row["riders"].get("weight_kg") and row["riders"].get("height_cm"))
        ]
    else:
        url = (
            f"{SUPABASE_URL}/rest/v1/riders"
            f"?source_url=not.is.null&weight_kg=is.null"
            f"&select=id,name,source_url&limit=1000"
        )
        return requests.get(url, headers=SB_AUTH).json()


async def scrape_one(browser, rider: dict) -> tuple[int | None, int | None]:
    page = await browser.new_page(user_agent=CF_UA)
    try:
        await page.goto(rider["source_url"], wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(1200)
        title = await page.title()
        if any(s in title.lower() for s in ["just a moment", "403", "404"]):
            return None, None
        result = await page.evaluate(_EXTRACT_JS)
        if isinstance(result, list) and len(result) == 2:
            return result[0], result[1]
        return None, None
    except Exception as e:
        print(f"    FEJL ({rider['name']}): {e}")
        return None, None
    finally:
        await page.close()


def patch_rider(rider_id: str, weight: int | None, height: int | None) -> None:
    data: dict = {}
    if weight:
        data["weight_kg"] = weight
    if height:
        data["height_cm"] = height
    if not data:
        return
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/riders?id=eq.{rider_id}",
        json=data,
        headers=SB_HEADERS,
    )
    if not res.ok:
        print(f"  [DB FEJL] {res.status_code}")


async def run(race_slug: str | None) -> None:
    riders = get_riders(race_slug)
    total = len(riders)
    label = race_slug or "alle ryttere"
    print(f"rider_stats_agent.py — {label}")
    print(f"Fandt {total} ryttere uden vægt/højde\n")
    if not riders:
        print("Ingen ryttere at opdatere.")
        return

    updated = 0
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        for i in range(0, total, CONCURRENCY):
            batch = riders[i : i + CONCURRENCY]
            results = await asyncio.gather(*[scrape_one(browser, r) for r in batch])
            for rider, (weight, height) in zip(batch, results):
                idx = i + batch.index(rider) + 1
                if weight or height:
                    patch_rider(rider["id"], weight, height)
                    print(f"  [{idx}/{total}] {rider['name']} → {height} cm / {weight} kg")
                    updated += 1
                else:
                    print(f"  [{idx}/{total}] {rider['name']} → ingen data")
        await browser.close()

    print(f"\nFærdig: {updated}/{total} opdateret")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--race")
    group.add_argument("--all", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(None if args.all else args.race))
