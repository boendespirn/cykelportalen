"""
article_image_backfill.py
Sætter image_url på artikler ved at matche rytternavne i titlen mod riders.photo_url.
Kør én gang: python article_image_backfill.py
"""
import os, io, sys, requests
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

URL = os.getenv("SUPABASE_URL", "").rstrip("/")
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
AUTH = {"apikey": KEY, "Authorization": f"Bearer {KEY}"}
HDRS = {**AUTH, "Content-Type": "application/json", "Prefer": "return=minimal"}


def get_articles():
    res = requests.get(
        f"{URL}/rest/v1/news_articles?image_url=is.null&select=id,slug,title",
        headers=AUTH,
    )
    return res.json() if res.ok else []


def get_riders():
    res = requests.get(
        f"{URL}/rest/v1/riders?select=id,name,slug,photo_url&photo_url=not.is.null",
        headers=AUTH,
    )
    return res.json() if res.ok else []


def find_rider_photo(title: str, riders: list[dict]) -> tuple[str | None, str | None]:
    title_lower = title.lower()
    for rider in riders:
        # Match på for- og/eller efternavn
        parts = rider["name"].lower().split()
        for part in parts:
            if len(part) > 3 and part in title_lower:
                return rider["photo_url"], rider["id"]
    return None, None


def update_article(article_id: str, photo_url: str, rider_id: str) -> bool:
    res = requests.patch(
        f"{URL}/rest/v1/news_articles?id=eq.{article_id}",
        json={"image_url": photo_url, "rider_id": rider_id},
        headers=HDRS,
    )
    return res.ok


def run():
    articles = get_articles()
    riders = get_riders()
    print(f"{len(articles)} artikler uden billede, {len(riders)} ryttere med foto\n")

    updated = 0
    for a in articles:
        photo, rider_id = find_rider_photo(a["title"], riders)
        if photo:
            ok = update_article(a["id"], photo, rider_id)
            status = "✓" if ok else "✗"
            print(f"  {status} {a['title'][:60]}")
            if ok:
                updated += 1
        else:
            print(f"  — Ingen rytter fundet: {a['title'][:60]}")

    print(f"\nOpdateret: {updated}/{len(articles)}")


if __name__ == "__main__":
    run()
