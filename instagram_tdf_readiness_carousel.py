# -*- coding: utf-8 -*-
"""
instagram_tdf_readiness_carousel.py
Genererer en "vi har alt til Tour de France"-karrusel (5 slides):
hero + 3 kapacitets-slides (stigningsprofiler, startliste/holdkort,
daglige resultater/nyheder) + branding-closer.

Kørsel:
  python instagram_tdf_readiness_carousel.py --preview
  python instagram_tdf_readiness_carousel.py
  python instagram_post_carousel.py assets/instagram/<mappe>/
"""

import io
import json
import sys
import argparse
from datetime import date
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("Pillow ikke installeret: pip install pillow")

from dotenv import load_dotenv
load_dotenv()

from fb_article_image import BG, EMERALD, WHITE, GRAY, DARK, _font, _wrap
from instagram_carousel_daily import _base_canvas, _add_logo_header, slide_branding

W, H   = 1080, 1080
ASSETS = Path(__file__).parent / "assets" / "instagram"
RACE_SLUG  = "tour-de-france-2026"
RACE_LABEL = "Tour de France 2026"
HASHTAGS = "#klassementet #tourdefrance #TDF2026 #cykling #cycling #UCI #WorldTour #cykelsport"


def slide_hero() -> "Image.Image":
    img, draw = _base_canvas()
    _add_logo_header(draw, img)
    draw.rectangle([(44, 136), (W - 44, 140)], fill=EMERALD)

    lbl = _font(28)
    draw.text((W // 2, 210), "TOUR DE FRANCE 2026", font=lbl, fill=GRAY, anchor="mm")

    big_f = _font(108, bebas=True)
    lines = ["ALT DU SKAL", "BRUGE TIL", "TOUREN"]
    TY = 300
    for line in lines:
        draw.text((W // 2, TY), line, font=big_f, fill=WHITE, anchor="mm")
        TY += 118

    sub_f = _font(30)
    draw.text((W // 2, H - 140), "Er du klar? Vi er.", font=sub_f, fill=EMERALD, anchor="mm")
    swipe_f = _font(22)
    draw.text((W // 2, H - 48), "Swipe for at se hvad vi har →", font=swipe_f, fill=GRAY, anchor="mm")
    return img


def _feature_slide(kicker: str, title_lines: list[str], subtitle: str) -> "Image.Image":
    img, draw = _base_canvas()
    _add_logo_header(draw, img)
    draw.rectangle([(44, 136), (W - 44, 140)], fill=EMERALD)

    kicker_f = _font(26)
    draw.text((56, 260), kicker.upper(), font=kicker_f, fill=EMERALD)

    title_f = _font(92, bebas=True)
    TY = 330
    for line in title_lines:
        lh = draw.textbbox((0, 0), line, font=title_f)[3]
        draw.text((56, TY), line, font=title_f, fill=WHITE)
        TY += int(lh * 0.95)

    sub_f = _font(30)
    for i, line in enumerate(_wrap(subtitle, sub_f, W - 112, draw)[:3]):
        draw.text((56, TY + 40 + i * 42), line, font=sub_f, fill=GRAY)

    return img


def slide_climb_profiles() -> "Image.Image":
    return _feature_slide(
        "Stignings-data",
        ["VI HAR ALLE", "STIGNINGS-", "PROFILER"],
        "Km-for-km hældningsprofil, kategori og placering for hver eneste stigning i Touren.",
    )


def slide_startlist() -> "Image.Image":
    return _feature_slide(
        "Ryttere & hold",
        ["VI HAR HELE", "STARTLISTEN"],
        "Alle holdkort, alle ryttere, alle favoritter — samlet ét sted.",
    )


def slide_daily_updates() -> "Image.Image":
    return _feature_slide(
        "Under touren",
        ["DAGLIGE", "RESULTATER", "& NYHEDER"],
        "Vi følger med hver eneste etape — hele vejen til Paris.",
    )


def save_carousel(slides: list["Image.Image"], folder: Path) -> None:
    names = [
        "slide_01_hero.jpg", "slide_02_climbs.jpg",
        "slide_03_startlist.jpg", "slide_04_daily.jpg",
        "slide_05_branding.jpg",
    ]
    folder.mkdir(parents=True, exist_ok=True)
    for slide, name in zip(slides, names):
        path = folder / name
        slide.save(path, format="JPEG", quality=92, optimize=True)
        print(f"  Gemt: {path.name}")

    caption = (
        f"🏔️ {RACE_LABEL} — ER DU KLAR?\n\n"
        "Vi har samlet alt det vigtigste ét sted: stigningsprofiler for hver etape, "
        "hele startlisten med alle holdkort, og daglige resultater og nyheder hele vejen "
        "gennem Touren.\n\n"
        "Link i kommentar\n\n"
        f"{HASHTAGS}"
    )
    meta = {
        "caption": caption,
        "link": f"https://klassementet.dk/{RACE_SLUG}",
        "race_slug": RACE_SLUG,
    }
    (folder / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("  Gemt: meta.json")


def run(preview: bool = False) -> Path:
    print("Genererer 5 slides...")
    slides = [
        slide_hero(),
        slide_climb_profiles(),
        slide_startlist(),
        slide_daily_updates(),
        slide_branding(),
    ]

    today  = date.today()
    folder = ASSETS / f"{today.isoformat()}-tdf-readiness"
    save_carousel(slides, folder)

    print(f"\nKlar: {folder}")
    print(f"Post med: python instagram_post_carousel.py {folder}")

    if preview:
        for slide in slides:
            slide.show()

    return folder


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true", help="Vis slides lokalt")
    args = parser.parse_args()
    run(args.preview)
