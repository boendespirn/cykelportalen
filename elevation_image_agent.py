"""
elevation_image_agent.py
Downloader højdeprofil-billeder fra PCS via Playwright (omgår Cloudflare)
og gemmer dem i Supabase Storage, så vi undgår PCS's hotlink-blokering.

Kør: python elevation_image_agent.py                    # alle løb
     python elevation_image_agent.py --race criterium-du-dauphine-2026
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
BUCKET = "stage-profiles"

SB_AUTH = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}
SB_HEADERS = {**SB_AUTH, "Content-Type": "application/json", "Prefer": "return=minimal"}

CF_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

PCS_PATTERN = "procyclingstats.com"


def upload_image(path: str, data: bytes, content_type: str = "image/jpeg") -> str | None:
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{path}"
    res = requests.post(
        url,
        data=data,
        headers={**SB_AUTH, "Content-Type": content_type, "x-upsert": "true"},
    )
    if not res.ok:
        print(f"    Upload fejl {res.status_code}: {res.text[:120]}")
        return None
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{path}"


def patch_stage(stage_id: str, image_url: str) -> bool:
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/stages?id=eq.{stage_id}",
        json={"elevation_image_url": image_url},
        headers=SB_HEADERS,
    )
    return res.ok


def get_stages(race_slug: str | None) -> list[dict]:
    if race_slug:
        race_res = requests.get(
            f"{SUPABASE_URL}/rest/v1/races?slug=eq.{race_slug}&select=id&limit=1",
            headers=SB_AUTH,
        )
        if not race_res.ok or not race_res.json():
            print(f"Løb ikke fundet: {race_slug}")
            return []
        race_id = race_res.json()[0]["id"]
        filter_q = f"race_id=eq.{race_id}&"
    else:
        filter_q = ""

    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages"
        f"?{filter_q}elevation_image_url=not.is.null"
        f"&select=id,race_id,stage_number,source_url,elevation_image_url"
        f"&limit=500",
        headers=SB_AUTH,
    )
    if not res.ok:
        print(f"DB fejl: {res.status_code}")
        return []

    return [
        s for s in res.json()
        if PCS_PATTERN in (s.get("elevation_image_url") or "")
        and s.get("source_url")
    ]


async def capture_sprint_profile(context, pcs_stage_url: str) -> tuple[str | None, bytes | None]:
    """
    Navigér til PCS /info/profiles-siden og opsnappr sprint-profilbilledet
    (det er elevationsprofilen med sprint-markeringer — det bedste vi kan få fra PCS).
    Returnerer (ny_url, bytes) eller (None, None).

    Filnavns-mønstre alene ('profile', 'sprint' vs. 'map') er IKKE nok til at
    skelne en ægte højdeprofil fra et rutekort — PCS bruger 'profile' i filnavnet
    for begge typer billeder (bekræftet bug: TdF 2026 etape 5/9 fik et rutekort på
    ~880-905 KB gemt som "elevation_image_url"). Ægte højdeprofil-billeder (simpel
    linjegraf) er observeret at være 60-120 KB; rutekort (detaljeret terræn/veje)
    er 300 KB+. Vi indsamler derfor ALLE filnavns-matchende kandidater og vælger
    den mindste inden for et fornuftigt størrelsesinterval, i stedet for "første match".
    """
    profiles_url = pcs_stage_url.rstrip("/") + "/info/profiles"
    MIN_BYTES = 10_000
    MAX_BYTES = 250_000  # ægte profiler er typisk <130 KB; rutekort er typisk 300 KB+
    candidates: list[tuple[str, bytes]] = []

    page = await context.new_page()

    async def on_response(response):
        url = response.url
        fname = url.split("/")[-1]
        # Tag elevationsprofil-billed-kandidater: enten '-sprint-' eller '-profile-'
        # Spring '-map-', '-finish-', '-climb' over (filnavns-heuristik, ikke tilstrækkelig alene)
        is_candidate = (
            "procyclingstats.com/images/profiles" in url
            and response.ok
            and ("sprint" in fname or ("profile" in fname and "climb" not in fname))
            and "map" not in fname
            and "finish" not in fname
            and "climb" not in fname
        )
        if is_candidate:
            try:
                data = await response.body()
                if MIN_BYTES < len(data) < MAX_BYTES:
                    candidates.append((url, data))
            except Exception:
                pass

    page.on("response", on_response)

    try:
        await page.goto(profiles_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
    except Exception as e:
        print(f"    Navigation fejl: {e}")
    finally:
        await page.close()

    if candidates:
        # Vælg mindste kandidat — ægte højdeprofiler er markant mindre end rutekort
        return min(candidates, key=lambda c: len(c[1]))
    return None, None


async def run_async(race_slug: str | None) -> None:
    stages = get_stages(race_slug)
    label = race_slug or "alle løb"
    print(f"elevation_image_agent.py — {label}")
    print(f"Fandt {len(stages)} etaper med PCS-billeder\n")
    if not stages:
        print("Ingen at opdatere.")
        return

    updated = 0
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        for i, stage in enumerate(stages):
            if i > 0:
                await asyncio.sleep(2)

            # Frisk context per etape — undgår Cloudflare-blokering
            context = await browser.new_context(user_agent=CF_UA, locale="en-US")
            new_url, data = await capture_sprint_profile(context, stage["source_url"])
            await context.close()

            if not data:
                print(f"  ✗ E{stage['stage_number']} — ingen profilbillede fundet")
                continue

            filename = new_url.split("/")[-1]
            storage_path = f"{stage['race_id']}/{filename}"

            public_url = upload_image(storage_path, data, "image/jpeg")
            if not public_url:
                continue

            if patch_stage(stage["id"], public_url):
                print(f"  ✓ E{stage['stage_number']} ({len(data)//1024} KB) — {filename}")
                updated += 1
            else:
                print(f"  [DB fejl] E{stage['stage_number']}")

        await browser.close()

    print(f"\nFærdig: {updated}/{len(stages)} billeder migreret")


def run(race_slug: str | None) -> None:
    asyncio.run(run_async(race_slug))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--race", default=None, help="Løb-slug (udelad for alle løb)")
    args = parser.parse_args()
    run(args.race)
