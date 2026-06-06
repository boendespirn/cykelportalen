"""
intro_content.py
Genererer 3 fastgjorte opslag (1080x1080) til Instagram og TikTok-profilen.
Disse viser hvad klassementet.dk tilbyder og fastgøres øverst på profilerne.

Kør: python intro_content.py
Outputfiler: intro_1_hvad.png, intro_2_lob.png, intro_3_features.png
"""

from pathlib import Path
from io import BytesIO

try:
    from PIL import Image, ImageDraw, ImageFont
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

from fb_article_image import _font, _wrap
from brand_logo import make_logo

W, H = 1080, 1080

BG      = (10,  17,  34)
BG2     = (15,  23,  42)
EMERALD = (16, 185, 129)
WHITE   = (248, 250, 252)
GRAY    = (100, 116, 139)
DARK    = (18,  28,  52)
SLATE   = (30,  41,  59)


def _base_canvas() -> tuple["Image.Image", "ImageDraw.ImageDraw"]:
    """Opretter grundlæggende branded canvas med gradient + bjerg."""
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Gradient
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

    # Emerald top/bund-bar
    draw.rectangle([(0, 0),   (W, 8)], fill=EMERALD)
    draw.rectangle([(0, H-8), (W, H)], fill=EMERALD)

    return img, draw


def _paste_logo(img: "Image.Image", x: int = 36, y: int = 28, size: int = 100) -> int:
    """Indsæt K+cykelist-logo, returnér slutposition i x."""
    logo = make_logo(size).convert("RGBA")
    img.paste(logo, (x, y), logo)
    return x + size + 20


def _header(draw: "ImageDraw.ImageDraw", logo_end_x: int) -> None:
    hdr = _font(22)
    draw.text((logo_end_x, 52), "KLASSEMENTET.DK", font=hdr, fill=EMERALD)
    draw.rectangle([(36, 144), (W - 36, 148)], fill=EMERALD)


# ── Post 1: Hvad er klassementet.dk? ─────────────────────────────────────────

def make_intro_1() -> "Image.Image":
    """Post 1 — brandintroduktion og hvad sitet er."""
    img, draw = _base_canvas()
    lx = _paste_logo(img)
    _header(draw, lx)

    TY = 176
    TX = 56

    # Overskrift
    title_f = _font(82, bebas=True)
    for line in _wrap("HVAD ER KLASSEMENTET?", title_f, W - TX*2, draw)[:3]:
        lh = draw.textbbox((0, 0), line, font=title_f)[3]
        draw.text((TX, TY), line, font=title_f, fill=WHITE)
        TY += int(lh * 0.90)

    TY += 24

    # Tagline
    tag_f = _font(26)
    draw.text((TX, TY), "Danmarks bedste cykelportal — gratis og altid opdateret.", font=tag_f, fill=GRAY)
    TY += 52

    # Separator
    draw.rectangle([(TX, TY), (TX + 80, TY + 4)], fill=EMERALD)
    TY += 28

    # Bullet points
    bullets = [
        ("🗓️", "Løbskalender for UCI WorldTour"),
        ("🚴", "Rytterprofiler og holdoversigt"),
        ("📊", "Etapedata, klassementer og højdeprofiler"),
        ("📰", "Nyheder og løbsrapporter"),
        ("🏆", "Resultater fra alle store løb"),
    ]
    bl_f = _font(30)
    for emoji, text in bullets:
        draw.text((TX, TY), emoji, font=bl_f, fill=WHITE)
        draw.text((TX + 52, TY), text, font=bl_f, fill=WHITE)
        TY += 50

    TY += 20
    cta_f = _font(28)
    draw.text((W // 2, TY), "klassementet.dk", font=cta_f, fill=EMERALD, anchor="mm")

    return img


# ── Post 2: Følg med i alle store løb ────────────────────────────────────────

def make_intro_2() -> "Image.Image":
    """Post 2 — de store løb vi dækker."""
    img, draw = _base_canvas()
    lx = _paste_logo(img)
    _header(draw, lx)

    TY = 176
    TX = 56

    title_f = _font(76, bebas=True)
    for line in _wrap("FØLG MED I ALLE STORE LØB", title_f, W - TX*2, draw)[:3]:
        lh = draw.textbbox((0, 0), line, font=title_f)[3]
        draw.text((TX, TY), line, font=title_f, fill=WHITE)
        TY += int(lh * 0.90)

    TY += 20
    draw.rectangle([(TX, TY), (TX + 80, TY + 4)], fill=EMERALD)
    TY += 28

    races = [
        ("🟡", "TOUR DE FRANCE",       "Juli"),
        ("🩷", "GIRO D'ITALIA",         "Maj"),
        ("🔴", "LA VUELTA",             "August"),
        ("🔵", "PARIS–ROUBAIX",         "April"),
        ("🟠", "IL LOMBARDIA",          "Oktober"),
        ("⚫", "MILANO–SAN REMO",       "Marts"),
        ("🟤", "LIÈGE–BASTOGNE–LIÈGE",  "April"),
    ]

    race_f  = _font(28)
    month_f = _font(22)

    for emoji, name, month in races:
        # Emerald pill baggrund
        pill_y = TY - 4
        draw.rounded_rectangle([(TX, pill_y), (W - TX, pill_y + 44)], radius=8, fill=SLATE)

        draw.text((TX + 14, TY), emoji,  font=race_f, fill=WHITE)
        draw.text((TX + 56, TY), name,   font=race_f, fill=WHITE)
        draw.text((W - TX - 14, TY + 4), month, font=month_f, fill=GRAY, anchor="rt")
        TY += 54

    TY += 10
    cta_f = _font(26)
    draw.text((W // 2, TY), "Følg med på klassementet.dk", font=cta_f, fill=EMERALD, anchor="mm")

    return img


# ── Post 3: Find alt på klassementet.dk ──────────────────────────────────────

def make_intro_3() -> "Image.Image":
    """Post 3 — features og hvad man finder på sitet."""
    img, draw = _base_canvas()
    lx = _paste_logo(img)
    _header(draw, lx)

    TY = 176
    TX = 56

    title_f = _font(82, bebas=True)
    for line in _wrap("ALT DU HAR BRUG FOR", title_f, W - TX*2, draw)[:3]:
        lh = draw.textbbox((0, 0), line, font=title_f)[3]
        draw.text((TX, TY), line, font=title_f, fill=WHITE)
        TY += int(lh * 0.90)

    TY += 22
    draw.rectangle([(TX, TY), (TX + 80, TY + 4)], fill=EMERALD)
    TY += 32

    features = [
        ("📋", "STARTLISTER",     "Se hvem kører hvornår"),
        ("🏔️", "HØJDEPROFILER",   "Interaktive etapeprofiler"),
        ("👤", "RYTTERPROFILER",  "Stats, resultater og karriere"),
        ("🏢", "HOLD",            "Holdsammensætninger 2026"),
        ("📈", "KLASSEMENTER",    "GC, point, bjerg, ungdom"),
        ("📰", "NYHEDER",         "Daglige artikler og analyser"),
    ]

    lbl_f  = _font(26, bebas=True)
    desc_f = _font(22)
    col_w  = (W - TX*2 - 30) // 2

    for i, (emoji, label, desc) in enumerate(features):
        col = i % 2
        row = i // 2
        fx  = TX + col * (col_w + 30)
        fy  = TY + row * 108

        draw.rounded_rectangle([(fx, fy), (fx + col_w, fy + 90)], radius=10, fill=SLATE)
        draw.text((fx + 14, fy + 12), emoji, font=lbl_f, fill=EMERALD)
        draw.text((fx + 50, fy + 12), label, font=lbl_f, fill=WHITE)
        draw.text((fx + 14, fy + 56), desc,  font=desc_f, fill=GRAY)

    TY += 3 * 108 + 20
    cta_f = _font(28)
    draw.text((W // 2, TY), "Besøg klassementet.dk", font=cta_f, fill=EMERALD, anchor="mm")

    return img


def save_all() -> None:
    print("Genererer pinned post-billeder...")
    for i, (fn, maker) in enumerate([
        ("intro_1_hvad.png",     make_intro_1),
        ("intro_2_lob.png",      make_intro_2),
        ("intro_3_features.png", make_intro_3),
    ], 1):
        img = maker()
        img.save(fn)
        print(f"  [{i}/3] Gemt: {fn}")
    print("\nSådan bruger du dem:")
    print("  1. Post hvert billede på Instagram (manuel upload)")
    print("  2. Gaa til opslaget -> 'Fastgoer til profil'")
    print("  3. Gør det samme på TikTok")


if __name__ == "__main__":
    if not PILLOW_AVAILABLE:
        print("Fejl: pip install pillow")
        exit(1)
    save_all()
