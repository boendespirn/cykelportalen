# -*- coding: utf-8 -*-
"""
instagram_carousel_bignews.py
Genererer en "stor nyhed" Instagram-karrusel (4 slides) for en enkelt artikel.

Kørsel:
  python instagram_carousel_bignews.py <artikel-slug>
  python instagram_carousel_bignews.py pogacar-vuelta-2026 --preview
"""

import io
import json
import math
import os
import re
import sys
import argparse
import requests
from datetime import date
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    from PIL import Image, ImageDraw, ImageFilter
    PILLOW_AVAILABLE = True
except ImportError:
    sys.exit("Pillow ikke installeret: pip install pillow")

from dotenv import load_dotenv
load_dotenv()

from fb_article_image import (
    BG, BG2, EMERALD, WHITE, GRAY, DARK,
    CATEGORY_LABELS, CATEGORY_EMOJI,
    _font, _wrap,
)
from instagram_carousel_daily import _base_canvas, _add_logo_header, slide_branding

W, H   = 1080, 1080
ASSETS = Path(__file__).parent / "assets" / "instagram"
API    = os.getenv("RAILWAY_API_URL", "https://web-production-4e06a.up.railway.app")
HASHTAGS = "#klassementet #cykling #cycling #UCI #WorldTour #cykelsport #ProCycling"


# ── Hent artikel ──────────────────────────────────────────────────────────────

def fetch_article(slug: str) -> dict | None:
    try:
        res = requests.get(f"{API}/news/{slug}", timeout=15)
        if res.ok:
            data = res.json()
            return None if data.get("error") else data
    except Exception as e:
        print(f"API fejl: {e}")
    return None


def _extract_quote(content: str) -> str:
    """Udtræk forste citat eller forste meningsfulde saetning."""
    # Prøv at finde citationstegn
    m = re.search(r'["""](.{30,200})["""]', content)
    if m:
        return m.group(1).strip()
    # Tag første afsnit der er langt nok
    for para in content.split("\n"):
        clean = re.sub(r"[#*_`]", "", para).strip()
        if len(clean) > 60:
            return clean[:220] + ("..." if len(clean) > 220 else "")
    return ""


# ── Slide 1: Hero ─────────────────────────────────────────────────────────────

def slide_hero(article: dict) -> "Image.Image":
    img, draw = _base_canvas()

    # Hvis der er et billede, læg det som baggrund med overlay
    image_url = article.get("image_url")
    if image_url:
        try:
            r = requests.get(image_url, timeout=10)
            if r.ok:
                from io import BytesIO
                bg_img = Image.open(BytesIO(r.content)).convert("RGB")
                bg_img = bg_img.resize((W, H), Image.LANCZOS)
                # Mørk gradient overlay
                overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ov_draw = ImageDraw.Draw(overlay)
                for y in range(H):
                    alpha = int(140 + (y / H) * 90)  # mørkere i bunden
                    ov_draw.line([(0, y), (W, y)], fill=(10, 17, 34, alpha))
                img = bg_img.copy()
                img.paste(overlay, mask=overlay)
                draw = ImageDraw.Draw(img)
        except Exception:
            pass

    # Emerald bars
    draw.rectangle([(0, 0),   (W, 8)], fill=EMERALD)
    draw.rectangle([(0, H-8), (W, H)], fill=EMERALD)
    _add_logo_header(draw, img)

    # Kategori
    category  = article.get("category", "generelt")
    cat_label = CATEGORY_LABELS.get(category, category.upper())
    emoji     = CATEGORY_EMOJI.get(category, "")
    cat_f     = _font(24)
    draw.text((56, 152), f"{emoji}  {cat_label}", font=cat_f, fill=EMERALD)

    # Race-navn hvis tilknyttet
    races = article.get("races")
    if races:
        race_f = _font(22)
        draw.text((56, 190), races.get("name", ""), font=race_f, fill=GRAY)

    # Stor overskrift nedad fra midten
    title   = article.get("title", "")
    title_f = _font(102, bebas=True)
    lines   = _wrap(title, title_f, W - 112, draw)
    TY      = 420
    for line in lines[:4]:
        lh = draw.textbbox((0, 0), line, font=title_f)[3]
        draw.text((56, TY), line, font=title_f, fill=WHITE)
        TY += int(lh * 0.90)

    # "Swipe for at laese mere →"
    swipe_f = _font(22)
    draw.text((W - 56, H - 48), "Swipe for at laese mere", font=swipe_f, fill=GRAY, anchor="rm")
    return img


# ── Slide 2: Citat ────────────────────────────────────────────────────────────

def slide_quote(article: dict) -> "Image.Image":
    img, draw = _base_canvas()
    draw.rectangle([(0, 0),   (W, 8)], fill=EMERALD)
    draw.rectangle([(0, H-8), (W, H)], fill=EMERALD)
    _add_logo_header(draw, img)
    draw.rectangle([(44, 136), (W - 44, 140)], fill=EMERALD)

    content = article.get("content", article.get("excerpt", ""))
    quote   = _extract_quote(content)

    if not quote:
        quote = article.get("excerpt", article.get("title", ""))[:220]

    # Emerald accent-streg til venstre
    draw.rectangle([(56, 200), (68, H - 200)], fill=EMERALD)

    TX = 100
    TW = W - TX - 56

    # Stort citationstegn
    big_q = _font(120, bebas=True)
    draw.text((TX, 180), '"', font=big_q, fill=tuple(int(c * 0.25) for c in EMERALD))

    # Citat-tekst
    TY = 280
    qt_f = _font(52, bebas=True)
    for line in _wrap(quote, qt_f, TW, draw)[:6]:
        lh = draw.textbbox((0, 0), line, font=qt_f)[3]
        draw.text((TX, TY), line, font=qt_f, fill=WHITE)
        TY += int(lh * 0.95)

    # Kilde
    author = article.get("author", "Klassementet")
    src_f  = _font(22)
    draw.text((TX, H - 80), f"— {author}", font=src_f, fill=GRAY)
    return img


# ── Slide 3: Website preview ──────────────────────────────────────────────────

def slide_website(article: dict) -> "Image.Image":
    """Tager et Playwright-screenshot af klassementet.dk og laver en slide."""
    img, draw = _base_canvas()
    draw.rectangle([(0, 0),   (W, 8)], fill=EMERALD)
    draw.rectangle([(0, H-8), (W, H)], fill=EMERALD)

    races     = article.get("races")
    race_slug = races.get("slug") if races else None
    race_name = races.get("name") if races else "klassementet.dk"
    target_url = f"https://klassementet.dk/{race_slug}" if race_slug else "https://klassementet.dk"

    # Forsøg Playwright screenshot
    screenshot_added = False
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page    = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(2000)
            sc_bytes = page.screenshot(type="jpeg", quality=85)
            browser.close()

        from io import BytesIO
        sc_img = Image.open(BytesIO(sc_bytes)).convert("RGB")
        # Crop og resize til 1080x600 (øvre 2/3 af slide)
        sc_img = sc_img.crop((0, 0, 1280, 750))
        sc_img = sc_img.resize((W, int(W * 750 / 1280)), Image.LANCZOS)
        sc_h   = sc_img.height
        # Læg screenshot ind med afrundede hjørner (approx)
        sc_y   = 80
        img.paste(sc_img, (0, sc_y))

        # Overlay gradient i bunden af screenshot
        grad = Image.new("RGBA", (W, 120), (0, 0, 0, 0))
        gd   = ImageDraw.Draw(grad)
        for y in range(120):
            gd.line([(0, y), (W, y)], fill=(10, 17, 34, int(y * 2.0)))
        img.paste(Image.new("RGB", (W, 120), BG),
                  (0, sc_y + sc_h - 120),
                  mask=grad.split()[3])
        draw = ImageDraw.Draw(img)
        screenshot_added = True
    except Exception as e:
        print(f"  [Screenshot] Playwright ikke tilgaengelig: {e}")

    if not screenshot_added:
        # Fallback: URL-bar mockup
        draw.rectangle([(44, 110), (W - 44, 160)], fill=DARK)
        url_f = _font(22)
        draw.text((W // 2, 135), f"klassementet.dk/{race_slug or ''}", font=url_f, fill=GRAY, anchor="mm")
        # Visuel "browser" ramme
        draw.rectangle([(44, 160), (W - 44, 700)], fill=(15, 22, 40))
        draw.rectangle([(44, 160), (W - 44, 700)], outline=EMERALD, width=2)
        mid_f = _font(36, bebas=True)
        draw.text((W // 2, 420), race_name, font=mid_f, fill=WHITE, anchor="mm")

    # Overlay CTA
    CTA_Y = H - 240
    draw.rectangle([(0, CTA_Y), (W, H - 8)], fill=BG)
    draw.rectangle([(0, CTA_Y), (W, CTA_Y + 4)], fill=EMERALD)

    cta_big  = _font(52, bebas=True)
    cta_line = f"SE ALT OM {race_name.upper()}"
    draw.text((W // 2, CTA_Y + 52), cta_line, font=cta_big, fill=WHITE, anchor="mm")

    cta_sub = _font(26)
    draw.text((W // 2, CTA_Y + 120), "Startliste  |  Etaper  |  Ryttere  |  Klassement",
              font=cta_sub, fill=GRAY, anchor="mm")

    url_f2 = _font(24)
    draw.text((W // 2, CTA_Y + 168), "klassementet.dk  ->", font=url_f2, fill=EMERALD, anchor="mm")
    return img


# ── Gem + meta.json ────────────────────────────────────────────────────────────

def save_bignews(slides: list["Image.Image"], article: dict, folder: Path) -> None:
    names = ["slide_01_hero.jpg", "slide_02_quote.jpg",
             "slide_03_website.jpg", "slide_04_branding.jpg"]
    folder.mkdir(parents=True, exist_ok=True)
    for slide, name in zip(slides, names):
        path = folder / name
        slide.save(path, format="JPEG", quality=92, optimize=True)
        print(f"  Gemt: {path.name}")

    races    = article.get("races")
    race_url = f"https://klassementet.dk/{races['slug']}" if races else "https://klassementet.dk"
    art_url  = f"https://klassementet.dk/nyheder/{article['slug']}"
    emoji    = CATEGORY_EMOJI.get(article.get("category", ""), "")
    caption  = (
        f"{emoji} {article['title']}\n\n"
        + (f"{article['excerpt'][:160]}\n\n" if article.get("excerpt") else "")
        + f"Link i kommentar\n\n{HASHTAGS}"
    )
    meta = {
        "caption":    caption,
        "link":       art_url,
        "race_url":   race_url,
        "article_id": article.get("id"),
        "slug":       article.get("slug"),
    }
    (folder / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  Gemt: meta.json")


# ── Main ───────────────────────────────────────────────────────────────────────

def run(slug: str, preview: bool = False) -> Path:
    print(f"Henter artikel: {slug}")
    article = fetch_article(slug)

    if not article:
        print("Artikel ikke fundet — bruger dummy til preview")
        article = {
            "id": "demo", "slug": slug,
            "title": "Paul Seixas udtaget til Tour de France 2026",
            "excerpt": "Den unge dansker er udtaget som den yngste dansker nogensinde til Touren.",
            "content": '"Jeg er stadig i chok over at vaere udtaget. Det er en drøm der går i opfyldelse," siger Paul Seixas.',
            "category": "startliste", "author": "Klassementet",
            "image_url": None, "races": {"name": "Tour de France 2026", "slug": "tour-de-france-2026"},
        }

    print("Genererer 4 slides...")
    slides = [
        slide_hero(article),
        slide_quote(article),
        slide_website(article),
        slide_branding(),
    ]

    today  = date.today()
    folder = ASSETS / f"{today.isoformat()}-{slug}"
    save_bignews(slides, article, folder)

    print(f"\nKlar: {folder}")
    print(f"Post med: python instagram_post_carousel.py {folder}")

    if preview:
        for slide in slides:
            slide.show()

    return folder


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("slug",    help="Artikel-slug (fx pogacar-vuelta-2026)")
    parser.add_argument("--preview", action="store_true", help="Vis slides lokalt")
    args = parser.parse_args()
    run(args.slug, args.preview)
