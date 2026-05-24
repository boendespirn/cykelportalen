"""
rider_photo_agent.py
Finder og gemmer foto-URL for alle ryttere der mangler det.

PCS host fotos på et forudsigeligt URL-mønster:
  https://www.procyclingstats.com/images/riders/100x100/{slug}.jpg

Vi udtrækker slug fra source_url og laver en HEAD-request for at verificere
at billedet eksisterer, inden vi gemmer det.

Kør: python rider_photo_agent.py
Re-run er sikkert: henter kun ryttere med photo_url = NULL.
"""

import os
import sys
import io
import time
import requests
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

DB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

PCS_PHOTO_BASE = "https://www.procyclingstats.com/images/riders/100x100"
REQUEST_DELAY = 0.15  # sekunder mellem requests for ikke at overbelaste PCS


def get_riders_without_photo() -> list[dict]:
    url = (
        f"{SUPABASE_URL}/rest/v1/riders"
        "?photo_url=is.null"
        "&source_url=not.is.null"
        "&select=id,name,slug,source_url"
        "&order=uci_ranking.asc.nullslast"
        "&limit=2000"
    )
    res = requests.get(url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
    res.raise_for_status()
    return res.json()


def extract_pcs_slug(source_url: str) -> str | None:
    # source_url: https://www.procyclingstats.com/rider/tadej-pogacar
    parts = source_url.rstrip("/").split("/")
    return parts[-1] if parts else None


def photo_url_exists(url: str) -> bool:
    try:
        r = requests.head(url, timeout=8, allow_redirects=True)
        return r.status_code == 200
    except Exception:
        return False


def patch_rider_photo(rider_id: str, photo_url: str) -> None:
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/riders?id=eq.{rider_id}",
        json={"photo_url": photo_url},
        headers=DB_HEADERS,
    )
    if not res.ok:
        print(f"  [DB FEJL] {res.status_code} {res.text[:120]}")


def run() -> None:
    riders = get_riders_without_photo()
    total = len(riders)
    print(f"Fandt {total} ryttere uden foto\n")

    if not riders:
        print("Alle ryttere har allerede et foto!")
        return

    found = 0
    missing = 0

    for i, rider in enumerate(riders, 1):
        pcs_slug = extract_pcs_slug(rider["source_url"])
        if not pcs_slug:
            print(f"  [{i}/{total}] {rider['name']} -> ingen slug")
            missing += 1
            continue

        photo_url = f"{PCS_PHOTO_BASE}/{pcs_slug}.jpg"

        if photo_url_exists(photo_url):
            patch_rider_photo(rider["id"], photo_url)
            print(f"  [{i}/{total}] {rider['name']} -> {photo_url}")
            found += 1
        else:
            print(f"  [{i}/{total}] {rider['name']} -> foto ikke fundet ({pcs_slug})")
            missing += 1

        time.sleep(REQUEST_DELAY)

    print(f"\nFærdig: {found} fotos gemt, {missing} uden foto")


if __name__ == "__main__":
    run()
