# -*- coding: utf-8 -*-
"""
instagram_carousel_daily.py
Genererer en "DAGENS NYHEDER" Instagram-karrusel (4-6 slides) og gemmer
billederne + meta.json i assets/instagram/YYYY-MM-DD-dagens-nyheder/

Kørsel:
  python instagram_carousel_daily.py            # brug dagens artikler
  python instagram_carousel_daily.py --preview  # generer + vis slides lokalt
  python instagram_carousel_daily.py --limit 4  # max 4 artikler
"""

import io
import json
import os
import sys
import argparse
import requests
from datetime import date, datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    from PIL import Image, ImageDraw
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

W, H   = 1080, 1080
ASSETS = Path(__file__).parent / "assets" / "instagram"
API    = os.getenv("RAILWAY_API_URL", "https://web-production-4e06a.up.railway.app")

HASHTAGS = (
    "#klassementet #cykling #cycling #UCI #WorldTour "
    "#cykelsport #ProCycling"
)

CATEGORY_COLORS = {
    "resultater":  (239,  68,  68),
    "analyse":     ( 59, 130, 246),
    "startliste":  (168,  85, 247),
    "transfer":    (249, 115,  22),
    "profil":      (234, 179,  8),
    "race_report": (236,  72, 153),
    "generelt":    EMERALD,
    "general":     EMERALD,
    "interview":   EMERALD,
}


# ── Baggrundsgenerering (delt) ─────────────────────────────────────────────────

def _base_canvas() -> tuple["Image.Image", "ImageDraw.ImageDraw"]:
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        c = tuple(int(BG[i] + (BG2[i] - BG[i]) * t) for i in range(3))
        draw.line([(0, y), (W, y)], fill=c)
    # Bjergsilhuet
    peaks = [
        (0, H), (0, H - 95), (110, H - 245), (210, H - 145), (330, H - 315),
        (440, H - 198), (545, H - 390), (635, H - 275), (725, H - 415),
        (830, H - 310), (920, H - 375), (1000, H - 258), (1080, H - 300),
        (1080, H),
    ]
    draw.polygon(peaks, fill=DARK)
    draw.rectangle([(0, 0),   (W, 8)], fill=EMERALD)
    draw.rectangle([(0, H-8), (W, H)], fill=EMERALD)
    return img, draw


def _add_logo_header(draw: "ImageDraw.ImageDraw", img: "Image.Image") -> int:
    """Tegner hjul-logo + KLASSEMENTET.DK. Returnerer x efter logo."""
    assets_dir = Path(__file__).parent / "assets"
    logo_path  = assets_dir / "logo_80.png"
    logo_end_x = 44
    if logo_path.exists():
        try:
            logo = Image.open(logo_path).convert("RGBA").resize((72, 72))
            img.paste(logo, (44, 32), logo)
            logo_end_x = 44 + 72 + 16
        except Exception:
            pass
    hdr = _font(20)
    draw.text((logo_end_x, 56), "KLASSEMENTET.DK", font=hdr, fill=EMERALD)
    return logo_end_x


# ── Slide 1: Header ────────────────────────────────────────────────────────────

def slide_header(article_count: int, today: date) -> "Image.Image":
    img, draw = _base_canvas()
    _add_logo_header(draw, img)

    # Separator linje
    draw.rectangle([(44, 136), (W - 44, 140)], fill=EMERALD)

    # "DAGENS" lille label
    lbl = _font(28)
    draw.text((W // 2, 220), "DAGENS", font=lbl, fill=GRAY, anchor="mm")

    # "NYHEDER" stort
    big = _font(148, bebas=True)
    draw.text((W // 2, 390), "NYHEDER", font=big, fill=WHITE, anchor="mm")

    # Dato
    months = ["jan", "feb", "mar", "apr", "maj", "jun",
              "jul", "aug", "sep", "okt", "nov", "dec"]
    dato_str = f"{today.day}. {months[today.month - 1]} {today.year}"
    dat = _font(26)
    draw.text((W // 2, 510), dato_str, font=dat, fill=GRAY, anchor="mm")

    # Antal
    count_f = _font(22)
    draw.text((W // 2, H - 52),
              f"{article_count} historier i dag  |  klassementet.dk",
              font=count_f, fill=GRAY, anchor="mm")
    return img


# ── Slides 2-N: Artikel ────────────────────────────────────────────────────────

def slide_article(article: dict, index: int, total: int) -> "Image.Image":
    img, draw = _base_canvas()

    # Slide-tæller øverst til højre
    num_f = _font(22)
    draw.text((W - 44, 52), f"{index}/{total}", font=num_f, fill=GRAY, anchor="rm")

    # Logo header
    _add_logo_header(draw, img)
    draw.rectangle([(44, 136), (W - 44, 140)], fill=EMERALD)

    category = article.get("category", "generelt")
    cat_color = CATEGORY_COLORS.get(category, EMERALD)
    cat_label = CATEGORY_LABELS.get(category, category.upper())
    emoji     = CATEGORY_EMOJI.get(category, "")

    TY = 168
    TX = 56
    TW = W - TX - 56

    # Kategori-dot + label
    draw.ellipse([(TX, TY + 8), (TX + 14, TY + 22)], fill=cat_color)
    cat_f = _font(22)
    draw.text((TX + 24, TY + 4), f"{emoji}  {cat_label}", font=cat_f, fill=GRAY)
    TY += 52

    # Overskrift
    title = article.get("title", "")
    title_f = _font(82, bebas=True)
    for line in _wrap(title, title_f, TW, draw)[:5]:
        lh = draw.textbbox((0, 0), line, font=title_f)[3]
        draw.text((TX, TY), line, font=title_f, fill=WHITE)
        TY += int(lh * 0.90)

    # Excerpt
    excerpt = article.get("excerpt") or ""
    if excerpt and TY < H - 200:
        TY += 20
        exc_f = _font(26)
        for line in _wrap(excerpt[:180], exc_f, TW, draw)[:3]:
            draw.text((TX, TY), line, font=exc_f, fill=GRAY)
            TY += 36

    # Footer
    draw.rectangle([(TX, H - 74), (W - TX, H - 70)], fill=DARK)
    url_f = _font(20)
    draw.text((W - 56, H - 48), "klassementet.dk", font=url_f, fill=GRAY, anchor="rm")
    return img


# ── Slide sidst: Branding ──────────────────────────────────────────────────────

def slide_branding() -> "Image.Image":
    img, draw = _base_canvas()

    # Stor hjul manuelt (SVG-lignende med PIL)
    cx, cy, r = W // 2, 380, 160
    draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)],
                 outline=EMERALD, width=14)
    draw.ellipse([(cx - r*2//3, cy - r*2//3), (cx + r*2//3, cy + r*2//3)],
                 outline=tuple(int(c * 0.35) for c in EMERALD), width=4)
    import math
    for i in range(12):
        angle = math.radians(i * 30)
        x2 = cx + int(r * math.cos(angle))
        y2 = cy + int(r * math.sin(angle))
        draw.line([(cx, cy), (x2, y2)], fill=EMERALD, width=3)
    draw.ellipse([(cx - 16, cy - 16), (cx + 16, cy + 16)], fill=EMERALD)

    # Wordmark
    wm = _font(88, bebas=True)
    # K i emerald + LASSEMENTET i hvid
    k_w = draw.textbbox((0, 0), "K", font=wm)[2]
    total_w = draw.textbbox((0, 0), "KLASSEMENTET", font=wm)[2]
    start_x = (W - total_w) // 2
    draw.text((start_x, 585), "K", font=wm, fill=EMERALD)
    draw.text((start_x + k_w, 585), "LASSEMENTET", font=wm, fill=WHITE)

    # Tagline
    tl = _font(26)
    draw.text((W // 2, 710), "Dansk cykelmedie", font=tl, fill=GRAY, anchor="mm")

    url_f = _font(22)
    draw.text((W // 2, H - 52), "Laes mere paa klassementet.dk", font=url_f, fill=GRAY, anchor="mm")
    return img


# ── Fetch artikler ─────────────────────────────────────────────────────────────

def fetch_articles(limit: int) -> list[dict]:
    try:
        res = requests.get(f"{API}/news", params={"limit": limit}, timeout=15)
        if res.ok:
            return res.json()
    except Exception as e:
        print(f"API fejl: {e}")
    return []


# ── Gem + meta.json ────────────────────────────────────────────────────────────

def save_carousel(slides: list["Image.Image"], articles: list[dict], folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for i, slide in enumerate(slides, 1):
        path = folder / f"slide_{i:02d}.jpg"
        slide.save(path, format="JPEG", quality=92, optimize=True)
        print(f"  Gemt: {path.name}")

    today = date.today()
    months = ["januar", "februar", "marts", "april", "maj", "juni",
              "juli", "august", "september", "oktober", "november", "december"]
    dato_str = f"{today.day}. {months[today.month - 1]} {today.year}"

    caption_lines = [f"DAGENS NYHEDER — {dato_str}", ""]
    for i, art in enumerate(articles, 1):
        emoji = CATEGORY_EMOJI.get(art.get("category", ""), "")
        caption_lines.append(f"{i}. {emoji} {art.get('title', '')}")
    caption_lines += ["", "Link i kommentar", "", HASHTAGS]

    meta = {
        "caption":     "\n".join(caption_lines),
        "hashtags":    HASHTAGS,
        "article_ids": [art.get("id") for art in articles],
        "date":        today.isoformat(),
        "link":        "https://klassementet.dk/nyheder",
    }
    (folder / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  Gemt: meta.json")


# ── Main ───────────────────────────────────────────────────────────────────────

def run(limit: int = 4, preview: bool = False) -> Path:
    today   = date.today()
    articles = fetch_articles(limit)

    if not articles:
        print("Ingen artikler fundet — bruger dummy-data til preview")
        articles = [
            {"id": "1", "title": "Vingegaard vinder Tour de France-etape",
             "excerpt": "Jonas Vingegaard satte et imponerende tempo.", "category": "resultater"},
            {"id": "2", "title": "Paul Seixas udtaget til dansk hold",
             "excerpt": "Den unge dansker er klar til sin storscene.", "category": "startliste"},
            {"id": "3", "title": "Analyse: Hvem vinder Vuelta?",
             "excerpt": "Tre ryttere skiller sig ud som klare favoritter.", "category": "analyse"},
        ]

    articles = articles[:limit]
    total    = len(articles)

    print(f"Genererer {total + 2} slides...")
    slides = [slide_header(total, today)]
    for i, art in enumerate(articles, 1):
        slides.append(slide_article(art, i, total))
    slides.append(slide_branding())

    folder_name = f"{today.isoformat()}-dagens-nyheder"
    folder      = ASSETS / folder_name
    save_carousel(slides, articles, folder)

    print(f"\nKlar: {folder}")
    print(f"Post med: python instagram_post_carousel.py {folder}")

    if preview:
        for slide in slides:
            slide.show()

    return folder


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit",   type=int,  default=4, help="Max artikler (default: 4)")
    parser.add_argument("--preview", action="store_true",  help="Vis slides lokalt")
    args = parser.parse_args()
    run(args.limit, args.preview)
