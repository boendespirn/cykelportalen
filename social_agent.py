"""
social_agent.py
Auto-poster nye nyheder til Facebook og Instagram via Meta Graph API (gratis).

Forudsætninger:
  1. Opret Facebook Page + Meta Developer App
  2. Tilføj til .env:
       META_PAGE_ACCESS_TOKEN=...
       META_PAGE_ID=...
       META_INSTAGRAM_USER_ID=...  (valgfri)
  3. Kør image_generator.py --all FØR dette script (billeder kræves til Instagram)

Kør: python social_agent.py
     python social_agent.py --dry-run   (vis hvad der ville blive posted)
     python social_agent.py --limit 3   (max 3 poster)
"""

import os
import sys
import io
import re
import time
import argparse
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

META_TOKEN   = os.getenv("META_PAGE_ACCESS_TOKEN")
PAGE_ID      = os.getenv("META_PAGE_ID")
IG_USER_ID   = os.getenv("META_INSTAGRAM_USER_ID")  # valgfri

AUTH_HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
DB_HEADERS   = {**AUTH_HEADERS, "Content-Type": "application/json", "Prefer": "return=minimal"}

SITE_URL   = "https://klassementet.dk"
GRAPH_URL  = "https://graph.facebook.com/v19.0"
DELAY      = 2.0


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_unposted(limit: int) -> list[dict]:
    """Henter publicerede artikler der ikke er postet til sociale medier endnu."""
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/news_articles"
        f"?social_posted=eq.false&is_advertorial=eq.false&status=eq.published"
        f"&select=id,slug,title,excerpt,category,image_url,published_at,races(name,slug)"
        f"&order=published_at.desc&limit={limit}",
        headers=AUTH_HEADERS,
    )
    return res.json() if res.ok else []


def mark_posted(article_id: str) -> None:
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/news_articles?id=eq.{article_id}",
        json={"social_posted": True},
        headers=DB_HEADERS,
    )


# ── Caption builder ───────────────────────────────────────────────────────────

CATEGORY_EMOJI = {
    "resultater": "🏆",
    "startliste": "📋",
    "transfer":   "🔄",
    "profil":     "👤",
    "analyse":    "📊",
    "generelt":   "🚴",
}

HASHTAGS = (
    "#klassementet #cykling #cycling #UCI #WorldTour "
    "#cykelsport #ProCycling #GirodItalia #TourDeFrance"
)


def build_caption(article: dict, platform: str) -> str:
    emoji = CATEGORY_EMOJI.get(article.get("category", ""), "🚴")
    race  = article.get("races")
    title = article["title"]
    exc   = article.get("excerpt", "")
    url   = f"{SITE_URL}/nyheder/{article['slug']}"

    if platform == "facebook":
        lines = [f"{emoji} {title}", ""]
        if exc:
            lines.append(exc)
        if race:
            lines.append(f"\n📌 {race['name']}")
        lines.append(f"\n🔗 Link i kommentar ↓")
        return "\n".join(lines)

    elif platform == "instagram":
        lines = [f"{emoji} {title}", ""]
        if exc:
            lines.append(exc[:150] + ("…" if len(exc) > 150 else ""))
        lines.append("")
        lines.append(f"Læs mere på klassementet.dk")
        lines.append("")
        lines.append(HASHTAGS)
        return "\n".join(lines)

    return title


# ── Meta Graph API ────────────────────────────────────────────────────────────

def post_facebook(article: dict, dry_run: bool) -> bool:
    """Poster til Facebook Page med link-preview."""
    caption = build_caption(article, "facebook")
    article_url = f"{SITE_URL}/nyheder/{article['slug']}"

    if dry_run:
        print(f"  [FB DRY-RUN] {caption[:80]}...")
        return True

    payload = {
        "message":      caption,
        "link":         article_url,
        "access_token": META_TOKEN,
    }
    res = requests.post(f"{GRAPH_URL}/{PAGE_ID}/feed", data=payload)
    if res.ok:
        post_id = res.json().get("id", "?")
        print(f"  [FB] Postet: {post_id}")
        # Tilføj artikel-link som første kommentar
        if post_id and post_id != "?":
            requests.post(
                f"{GRAPH_URL}/{post_id}/comments",
                data={"message": article_url, "access_token": META_TOKEN},
                timeout=15,
            )
        return True
    else:
        print(f"  [FB FEJL] {res.status_code}: {res.text[:200]}")
        return False


def post_instagram(article: dict, dry_run: bool) -> bool:
    """Poster til Instagram med billede (kræver image_url)."""
    if not IG_USER_ID:
        print("  [IG] META_INSTAGRAM_USER_ID ikke sat — springer over")
        return False

    image_url = article.get("image_url")
    if not image_url:
        print("  [IG] Ingen image_url — brug image_generator.py --all")
        return False

    caption = build_caption(article, "instagram")

    if dry_run:
        print(f"  [IG DRY-RUN] Billede: {image_url[:60]}...")
        print(f"  Caption: {caption[:80]}...")
        return True

    # Trin 1: Opret media container
    res = requests.post(
        f"{GRAPH_URL}/{IG_USER_ID}/media",
        data={
            "image_url":    image_url,
            "caption":      caption,
            "access_token": META_TOKEN,
        },
    )
    if not res.ok:
        print(f"  [IG FEJL media] {res.status_code}: {res.text[:200]}")
        return False

    container_id = res.json().get("id")
    if not container_id:
        print("  [IG FEJL] Ingen container_id i svar")
        return False

    # Vent på Instagram-behandling
    time.sleep(3)

    # Trin 2: Publicér
    res2 = requests.post(
        f"{GRAPH_URL}/{IG_USER_ID}/media_publish",
        data={
            "creation_id":  container_id,
            "access_token": META_TOKEN,
        },
    )
    if res2.ok:
        media_id = res2.json().get("id", "?")
        print(f"  [IG] Postet: {media_id}")
        return True
    else:
        print(f"  [IG FEJL publish] {res2.status_code}: {res2.text[:200]}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def check_credentials() -> tuple[bool, bool]:
    """Returnerer (facebook_ok, instagram_ok)."""
    fb_ok = bool(META_TOKEN and PAGE_ID)
    ig_ok = bool(META_TOKEN and IG_USER_ID)
    return fb_ok, ig_ok


def run(limit: int, dry_run: bool) -> None:
    print(f"social_agent.py — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    fb_ok, ig_ok = check_credentials()

    if not fb_ok and not dry_run:
        print("\nFEJL: META_PAGE_ACCESS_TOKEN og/eller META_PAGE_ID mangler i .env")
        print("Følg opsætningsguiden:")
        print("  1. Opret Facebook Page")
        print("  2. Opret Meta Developer App på developers.facebook.com")
        print("  3. Generer Page Access Token (langtids) via Graph API Explorer")
        print("  4. Tilføj META_PAGE_ACCESS_TOKEN og META_PAGE_ID til .env")
        print("\nKør med --dry-run for at teste uden API-nøgler")
        return

    if dry_run:
        print("[DRY-RUN tilstand — ingen poster sendes]\n")

    articles = get_unposted(limit)
    print(f"Fandt {len(articles)} ikke-postede artikler\n")

    posted_fb = posted_ig = failed = 0

    for i, art in enumerate(articles, 1):
        print(f"[{i}/{len(articles)}] {art['title'][:65]}")

        fb_success = False
        ig_success = False

        # Facebook
        if fb_ok or dry_run:
            fb_success = post_facebook(art, dry_run)
            if fb_success:
                posted_fb += 1
            time.sleep(DELAY)

        # Instagram
        if ig_ok or dry_run:
            ig_success = post_instagram(art, dry_run)
            if ig_success:
                posted_ig += 1
            time.sleep(DELAY)

        # Markér som postet hvis mindst ét platform lykkedes
        if (fb_success or ig_success) and not dry_run:
            mark_posted(art["id"])
        elif not fb_success and not ig_success:
            failed += 1

        print()

    print(f"Færdig: {posted_fb} FB-poster, {posted_ig} IG-poster, {failed} fejl")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Vis uden at sende")
    parser.add_argument("--limit",   type=int, default=5, help="Max artikler per kørsel (default: 5)")
    args = parser.parse_args()
    run(args.limit, args.dry_run)
