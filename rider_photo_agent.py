"""
rider_photo_agent.py
Finder og gemmer foto-URL for ryttere ved at scrape PCS-rytterprofiler.
PCS bruger nu et hash-baseret URL-mønster der ikke kan forudsiges, så vi
besøger hver side med Playwright og udtrækker den faktiske billed-URL.

Kør: python rider_photo_agent.py --race criterium-du-dauphine-2026
     python rider_photo_agent.py           # alle ryttere med manglende/brudt foto
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
CONCURRENCY = 4
DELAY_MS = 1200

SB_AUTH = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}
SB_HEADERS = {**SB_AUTH, "Content-Type": "application/json", "Prefer": "return=minimal"}

CF_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

EXTRACT_JS = """() => {
    const imgs = Array.from(document.querySelectorAll('img'));
    for (const img of imgs) {
        const s = img.src || '';
        if (s.includes('/images/riders/') && !s.includes('flag') && !s.includes('logo') && !s.includes('jersey')) {
            return s;
        }
    }
    return null;
}"""

OLD_PATTERN = "/images/riders/100x100/"


def is_broken_url(url: str | None) -> bool:
    return not url or OLD_PATTERN in url


def get_riders(race_slug: str | None) -> list[dict]:
    if race_slug:
        race_res = requests.get(
            f"{SUPABASE_URL}/rest/v1/races?slug=eq.{race_slug}&select=id&limit=1",
            headers=SB_AUTH,
        )
        if not race_res.ok or not race_res.json():
            print(f"Løb ikke fundet: {race_slug}")
            return []
        race_id = race_res.json()[0]["id"]
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/startlists"
            f"?race_id=eq.{race_id}&status=eq.active"
            f"&select=riders(id,name,source_url,photo_url)"
            f"&limit=250",
            headers=SB_AUTH,
        )
        rows = res.json() if res.ok else []
        seen = set()
        riders = []
        for row in rows:
            r = row.get("riders") or {}
            if not r.get("source_url") or r["id"] in seen:
                continue
            if is_broken_url(r.get("photo_url")):
                seen.add(r["id"])
                riders.append(r)
    else:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/riders"
            f"?source_url=not.is.null"
            f"&select=id,name,source_url,photo_url"
            f"&order=uci_ranking.asc.nullslast"
            f"&limit=2000",
            headers=SB_AUTH,
        )
        rows = res.json() if res.ok else []
        riders = [r for r in rows if is_broken_url(r.get("photo_url"))]

    return riders


def patch_photo(rider_id: str, photo_url: str) -> bool:
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/riders?id=eq.{rider_id}",
        json={"photo_url": photo_url},
        headers=SB_HEADERS,
    )
    return res.ok


async def scrape_photo(browser, rider: dict, sem: asyncio.Semaphore) -> tuple[str, str | None]:
    async with sem:
        page = await browser.new_page(user_agent=CF_UA)
        try:
            await page.goto(rider["source_url"], wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(DELAY_MS)
            url = await page.evaluate(EXTRACT_JS)
            return rider["id"], url if isinstance(url, str) and url else None
        except Exception as e:
            print(f"  [Fejl] {rider['name']}: {e}")
            return rider["id"], None
        finally:
            await page.close()


async def run(race_slug: str | None) -> None:
    riders = get_riders(race_slug)
    label = race_slug or "alle ryttere"
    print(f"rider_photo_agent.py — {label}")
    print(f"Fandt {len(riders)} ryttere med manglende/brudt foto\n")
    if not riders:
        print("Ingen at opdatere.")
        return

    sem = asyncio.Semaphore(CONCURRENCY)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        tasks = [scrape_photo(browser, r, sem) for r in riders]
        results = await asyncio.gather(*tasks)
        await browser.close()

    updated = 0
    for rider_id, photo_url in results:
        rider = next(r for r in riders if r["id"] == rider_id)
        if photo_url:
            if patch_photo(rider_id, photo_url):
                print(f"  ✓ {rider['name']}")
                updated += 1
            else:
                print(f"  [DB fejl] {rider['name']}")
        else:
            print(f"  ✗ {rider['name']} — ingen foto fundet")

    print(f"\nFærdig: {updated}/{len(riders)} fotos opdateret")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--race", default=None, help="Løb-slug (udelad for alle ryttere)")
    args = parser.parse_args()
    asyncio.run(run(args.race))
