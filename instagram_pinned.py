# -*- coding: utf-8 -*-
"""
instagram_pinned.py
Genererer 3 fastgjorte Instagram-opslag (1080x1080) til Klassementet-profilen.

Post 1: "Hvad er Klassementet?" — hvad du kan se pa siden
Post 2: "Følg dit yndlingsløb" — screenshot af lob-siden
Post 3: "Lokale favoritter" — dansk cykelkærlighed

Kørsel:
  python instagram_pinned.py
  python instagram_pinned.py --preview
"""

import io
import math
import os
import sys
import argparse
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("Pillow ikke installeret: pip install pillow")

from dotenv import load_dotenv
load_dotenv()

from fb_article_image import BG, BG2, EMERALD, WHITE, GRAY, DARK, _font, _wrap
from instagram_carousel_daily import _base_canvas, _add_logo_header, slide_branding

W, H   = 1080, 1080
OUT    = Path(__file__).parent / "assets" / "instagram" / "pinned"


# ── Post 1: Hvad er Klassementet? ─────────────────────────────────────────────

def pinned_01_hvad() -> "Image.Image":
    img, draw = _base_canvas()
    draw.rectangle([(0, 0),   (W, 8)], fill=EMERALD)
    draw.rectangle([(0, H-8), (W, H)], fill=EMERALD)
    _add_logo_header(draw, img)
    draw.rectangle([(44, 136), (W - 44, 140)], fill=EMERALD)

    # Stor overskrift
    h1 = _font(72, bebas=True)
    draw.text((W // 2, 190), "ALT OM PROFESSIONEL", font=h1, fill=WHITE, anchor="mm")
    draw.text((W // 2, 258), "CYKLING", font=h1, fill=EMERALD, anchor="mm")
    h2 = _font(36, bebas=True)
    draw.text((W // 2, 308), "— ET STED", font=h2, fill=GRAY, anchor="mm")

    # Separator
    draw.rectangle([(W // 2 - 60, 338), (W // 2 + 60, 342)], fill=EMERALD)

    # 4 bullet-features
    features = [
        ("Loebskalender",  "Alle UCI WorldTour lob — kommende og afsluttede"),
        ("Etapeprofiler",  "Ruter, hoejder og detaljer for hver etape"),
        ("Ryttere & hold", "Profiler, statistikker og holdopstillinger"),
        ("Nyheder",        "Analyser og nyheder om dansk og international cykling"),
    ]
    TX  = 80
    TY  = 368
    for title, desc in features:
        # Emerald dot
        draw.ellipse([(TX, TY + 10), (TX + 16, TY + 26)], fill=EMERALD)
        ft = _font(32, bebas=True)
        draw.text((TX + 30, TY), title, font=ft, fill=WHITE)
        fd = _font(20)
        draw.text((TX + 30, TY + 38), desc, font=fd, fill=GRAY)
        TY += 98

    # CTA footer
    draw.rectangle([(0, H - 130), (W, H - 8)], fill=DARK)
    draw.rectangle([(0, H - 130), (W, H - 126)], fill=EMERALD)
    cta_f = _font(36, bebas=True)
    draw.text((W // 2, H - 88), "klassementet.dk", font=cta_f, fill=EMERALD, anchor="mm")
    sub_f = _font(22)
    draw.text((W // 2, H - 44), "Dansk cykelmedie — Gratis og uannonsceret", font=sub_f, fill=GRAY, anchor="mm")
    return img


# ── Post 2: Følg dit yndlingsløb ──────────────────────────────────────────────

def pinned_02_follow() -> "Image.Image":
    img, draw = _base_canvas()
    draw.rectangle([(0, 0),   (W, 8)], fill=EMERALD)
    draw.rectangle([(0, H-8), (W, H)], fill=EMERALD)
    _add_logo_header(draw, img)
    draw.rectangle([(44, 136), (W - 44, 140)], fill=EMERALD)

    # Overskrift
    h1 = _font(82, bebas=True)
    draw.text((W // 2, 192), "FOLG DIT", font=h1, fill=WHITE, anchor="mm")
    draw.text((W // 2, 274), "YNDLINGSLOB", font=h1, fill=EMERALD, anchor="mm")

    # Browser mockup (ingen Playwright, rent grafisk)
    BX, BY = 44, 316
    BW, BH = W - 88, 520
    # Browser-ramme
    draw.rounded_rectangle([(BX, BY), (BX + BW, BY + BH)],
                            radius=14, fill=(12, 18, 38), outline=EMERALD, width=2)
    # URL-bar
    draw.rounded_rectangle([(BX + 12, BY + 14), (BX + BW - 12, BY + 52)],
                            radius=8, fill=(20, 30, 55))
    url_f = _font(18)
    draw.text(((BX + BW // 2), BY + 34),
              "klassementet.dk/tour-de-france-2026", font=url_f, fill=GRAY, anchor="mm")

    # Indhold-mock-blokke (simulerer siden)
    CX = BX + 24
    CY = BY + 70

    title_f = _font(28, bebas=True)
    draw.text((CX, CY), "TOUR DE FRANCE 2026", font=title_f, fill=EMERALD)
    CY += 40

    block_f = _font(18)
    draw.text((CX, CY), "1. juli — 26. juli  |  21 etaper  |  Frankrig", font=block_f, fill=GRAY)
    CY += 36

    # Nav tabs
    tabs = ["Oversigt", "Etaper", "Startliste", "Klassement", "Nyheder"]
    TX2 = CX
    for tab in tabs:
        tw = draw.textbbox((0, 0), tab, font=block_f)[2] + 20
        col = EMERALD if tab == "Etaper" else (30, 42, 70)
        draw.rounded_rectangle([(TX2, CY), (TX2 + tw, CY + 30)], radius=6, fill=col)
        tc = (10, 17, 34) if tab == "Etaper" else GRAY
        draw.text((TX2 + tw // 2, CY + 15), tab, font=_font(15), fill=tc, anchor="mm")
        TX2 += tw + 8
    CY += 48

    # Etape-rækker mock
    for i in range(1, 6):
        row_col = (16, 24, 50) if i % 2 == 0 else (13, 20, 42)
        draw.rectangle([(CX, CY), (BX + BW - 24, CY + 38)], fill=row_col)
        draw.text((CX + 8, CY + 10), f"Etape {i}", font=_font(18), fill=WHITE)
        draw.text((BX + BW - 32, CY + 10), "km", font=_font(16), fill=GRAY, anchor="rm")
        CY += 40

    # Feature-labels under mockup
    features = ["Etaper", "Startliste", "Klassement", "Nyheder"]
    TX3 = 44
    FY  = BY + BH + 24
    spacing = (W - 88) // len(features)
    feat_f = _font(22, bebas=True)
    for feat in features:
        draw.text((TX3 + spacing // 2, FY), feat, font=feat_f, fill=WHITE, anchor="mm")
        TX3 += spacing

    draw.rectangle([(44, H - 60), (W - 44, H - 56)], fill=DARK)
    draw.text((W // 2, H - 34), "Link i bio  |  klassementet.dk", font=_font(22), fill=EMERALD, anchor="mm")
    return img


# ── Post 3: Lokale favoritter ──────────────────────────────────────────────────

def pinned_03_local() -> "Image.Image":
    img, draw = _base_canvas()
    draw.rectangle([(0, 0),   (W, 8)], fill=EMERALD)
    draw.rectangle([(0, H-8), (W, H)], fill=EMERALD)
    _add_logo_header(draw, img)
    draw.rectangle([(44, 136), (W - 44, 140)], fill=EMERALD)

    # Overskrift
    h1 = _font(90, bebas=True)
    draw.text((W // 2, 196), "LOKALE", font=h1, fill=WHITE, anchor="mm")
    draw.text((W // 2, 284), "FAVORITTER", font=h1, fill=EMERALD, anchor="mm")

    # Beskrivelse
    desc_lines = [
        "Folg de danske ryttere du holder med",
        "— og se hvem der gar bedst i hvert lob",
    ]
    for i, line in enumerate(desc_lines):
        draw.text((W // 2, 342 + i * 36), line, font=_font(28), fill=GRAY, anchor="mm")

    # Rytter-korte mock (3 stk)
    cards = [
        ("Jonas Vingegaard",   "Visma | Lease a Bike", "GC Specialist"),
        ("Kasper Asgreen",     "Lidl-Trek",            "Klassiker"),
        ("Paul Seixas",        "Uno-X Mobility",       "Upcoming Talent"),
    ]
    CY = 430
    for name, team, role in cards:
        # Kort baggrund
        draw.rounded_rectangle([(60, CY), (W - 60, CY + 88)],
                                radius=10, fill=(16, 24, 50), outline=(30, 42, 70), width=1)
        # Avatar-cirkel
        draw.ellipse([(80, CY + 16), (80 + 56, CY + 72)], fill=(25, 36, 70), outline=EMERALD, width=2)
        initials = "".join(p[0] for p in name.split()[:2])
        draw.text((108, CY + 44), initials, font=_font(22, bebas=True), fill=EMERALD, anchor="mm")
        # Navn + hold
        draw.text((156, CY + 22), name,   font=_font(24, bebas=True), fill=WHITE)
        draw.text((156, CY + 52), team,   font=_font(18), fill=GRAY)
        # Role badge
        bw = draw.textbbox((0, 0), role, font=_font(16))[2] + 16
        draw.rounded_rectangle([(W - 80 - bw, CY + 28), (W - 80, CY + 60)],
                                radius=6, fill=EMERALD)
        draw.text((W - 80 - bw + bw // 2, CY + 44), role, font=_font(16), fill=(10, 17, 34), anchor="mm")
        CY += 106

    # CTA
    cta_f = _font(28, bebas=True)
    draw.text((W // 2, H - 90), "Find dine favoritter pa klassementet.dk", font=cta_f, fill=WHITE, anchor="mm")
    draw.text((W // 2, H - 46), "Link i bio", font=_font(22), fill=EMERALD, anchor="mm")
    return img


# ── Gem til disk ───────────────────────────────────────────────────────────────

def save_all(preview: bool = False) -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    posts = [
        ("post_01_hvad.jpg",     pinned_01_hvad(),    "Hvad er Klassementet?"),
        ("post_02_follow.jpg",   pinned_02_follow(),  "Folg dit yndlingslob"),
        ("post_03_local.jpg",    pinned_03_local(),   "Lokale favoritter"),
    ]

    for filename, img, label in posts:
        path = OUT / filename
        img.save(path, format="JPEG", quality=92, optimize=True)
        print(f"  Gemt: {filename}  ({label})")
        if preview:
            img.show()

    print(f"\nFaerdig. Upload manuelt til Instagram og fastnaal de 3 opslag:")
    print(f"  {OUT}")
    print("\nUpload-raekkefolge (aeldste = post_01 → vises forst pa profilen):")
    print("  1. post_03_local.jpg   — Lokale favoritter")
    print("  2. post_02_follow.jpg  — Folg dit yndlingslob")
    print("  3. post_01_hvad.jpg    — Hvad er Klassementet? (pinned oeverst)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true", help="Vis billeder lokalt")
    args = parser.parse_args()
    save_all(args.preview)
