# -*- coding: utf-8 -*-
"""
instagram_post_carousel.py
Poster en lokal karrusel-mappe til Instagram via Meta Graph API.

Kørsel:
  python instagram_post_carousel.py assets/instagram/2026-06-07-dagens-nyheder/
  python instagram_post_carousel.py assets/instagram/... --dry-run
"""

import io
import json
import os
import sys
import time
import argparse
import requests
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

TOKEN      = os.getenv("META_PAGE_ACCESS_TOKEN", "")
IG_USER_ID = os.getenv("META_INSTAGRAM_USER_ID", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
GRAPH      = "https://graph.facebook.com/v19.0"
BUCKET     = "news-images"
SITE_URL   = "https://klassementet.dk"


# ── Supabase upload ────────────────────────────────────────────────────────────

def upload_image(file_path: Path, key: str) -> str | None:
    """Uploader en lokal billedfil til Supabase Storage. Returnerer public URL."""
    h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    # Sikr at bucket eksisterer
    requests.post(
        f"{SUPABASE_URL}/storage/v1/bucket",
        json={"id": BUCKET, "name": BUCKET, "public": True},
        headers={**h, "Content-Type": "application/json"}, timeout=10,
    )
    data = file_path.read_bytes()
    res  = requests.post(
        f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{key}",
        data=data,
        headers={**h, "Content-Type": "image/jpeg", "x-upsert": "true"},
        timeout=30,
    )
    if not res.ok:
        print(f"  Upload fejl ({res.status_code}): {res.text[:100]}")
        return None
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{key}"


# ── Instagram Graph API ────────────────────────────────────────────────────────

def create_media_item(image_url: str, dry_run: bool) -> str | None:
    """Opretter et enkelt karrusel-element. Returnerer container_id."""
    if dry_run:
        print(f"    [DRY] POST /{IG_USER_ID}/media is_carousel_item=true url={image_url[:60]}")
        return "dry_run_id"
    res = requests.post(
        f"{GRAPH}/{IG_USER_ID}/media",
        data={
            "image_url":        image_url,
            "is_carousel_item": "true",
            "access_token":     TOKEN,
        },
        timeout=20,
    )
    if res.ok:
        return res.json().get("id")
    print(f"  Media item fejl ({res.status_code}): {res.text[:150]}")
    return None


def create_carousel(children: list[str], caption: str, dry_run: bool) -> str | None:
    """Opretter carousel-container. Returnerer creation_id."""
    if dry_run:
        print(f"    [DRY] POST /{IG_USER_ID}/media CAROUSEL children={children[:2]}...")
        return "dry_run_carousel"
    res = requests.post(
        f"{GRAPH}/{IG_USER_ID}/media",
        data={
            "media_type":   "CAROUSEL",
            "children":     ",".join(children),
            "caption":      caption,
            "access_token": TOKEN,
        },
        timeout=20,
    )
    if res.ok:
        return res.json().get("id")
    print(f"  Carousel container fejl ({res.status_code}): {res.text[:150]}")
    return None


def publish_carousel(creation_id: str, dry_run: bool) -> str | None:
    """Publicerer carousel. Returnerer Instagram media id."""
    if dry_run:
        print(f"    [DRY] POST /{IG_USER_ID}/media_publish creation_id={creation_id}")
        return "dry_run_post"
    res = requests.post(
        f"{GRAPH}/{IG_USER_ID}/media_publish",
        data={"creation_id": creation_id, "access_token": TOKEN},
        timeout=20,
    )
    if res.ok:
        return res.json().get("id")
    print(f"  Publish fejl ({res.status_code}): {res.text[:150]}")
    return None


def post_comment(post_id: str, link: str, dry_run: bool) -> None:
    """Poster link som forste kommentar."""
    if dry_run:
        print(f"    [DRY] POST /{post_id}/comments message={link}")
        return
    requests.post(
        f"{GRAPH}/{post_id}/comments",
        data={"message": link, "access_token": TOKEN},
        timeout=15,
    )


# ── Main ───────────────────────────────────────────────────────────────────────

def post_carousel(folder: Path, dry_run: bool = False) -> bool:
    print(f"Poster karrusel fra: {folder.name}")

    if not TOKEN or not IG_USER_ID:
        print("FEJL: META_PAGE_ACCESS_TOKEN eller META_INSTAGRAM_USER_ID mangler i .env")
        return False

    # Laes meta.json
    meta_path = folder / "meta.json"
    if not meta_path.exists():
        print("FEJL: meta.json ikke fundet i mappen")
        return False
    meta    = json.loads(meta_path.read_text(encoding="utf-8"))
    caption = meta.get("caption", "")
    link    = meta.get("link", SITE_URL)

    # Find alle slide-billeder (sorteret)
    slides = sorted(folder.glob("slide_*.jpg"))
    if not slides:
        print("FEJL: Ingen slide_*.jpg filer fundet")
        return False

    print(f"Fandt {len(slides)} slides")

    # 1. Upload hvert slide + opret media item
    container_ids = []
    for i, slide_path in enumerate(slides, 1):
        print(f"  [{i}/{len(slides)}] Uploader {slide_path.name}...")
        key = f"ig_carousel_{folder.name}_{i:02d}.jpg"
        if dry_run:
            url = f"https://example.com/{key}"
        else:
            url = upload_image(slide_path, key)
            if not url:
                return False

        cid = create_media_item(url, dry_run)
        if not cid:
            return False
        container_ids.append(cid)
        time.sleep(1)

    # 2. Opret carousel container
    print("  Opretter carousel container...")
    carousel_id = create_carousel(container_ids, caption, dry_run)
    if not carousel_id:
        return False

    # 3. Vent + publicer
    print("  Venter 4 sek paa Instagram...")
    if not dry_run:
        time.sleep(4)

    print("  Publicerer...")
    post_id = publish_carousel(carousel_id, dry_run)
    if not post_id:
        return False

    # 4. Post link i kommentar
    print("  Poster link i kommentar...")
    post_comment(post_id, link, dry_run)

    print(f"\nKlar! Instagram post id: {post_id}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", help="Sti til karrusel-mappe (assets/instagram/...)")
    parser.add_argument("--dry-run", action="store_true", help="Vis uden at sende til Instagram")
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.exists():
        sys.exit(f"Mappe ikke fundet: {folder}")

    success = post_carousel(folder, args.dry_run)
    sys.exit(0 if success else 1)
