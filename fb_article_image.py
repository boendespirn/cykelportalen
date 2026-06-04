"""
fb_article_image.py
Genererer 1200x630 Facebook-billeder med Klassementet-branding og artikelens
overskrift i Bebas Neue. Poster automatisk til Facebook Page som foto-opslag.

Bruges som background task fra api.py (approve + edit endpoints).
"""

import os
import requests
from io import BytesIO
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

# ── Farver (klassementet.dk palette) ─────────────────────────────────────────
BG      = (10,  17,  34)
BG2     = (15,  23,  42)
EMERALD = (16, 185, 129)
WHITE   = (248, 250, 252)
GRAY    = (100, 116, 139)
DARK    = (18,  28,  52)

W, H = 1200, 630
GRAPH_URL = "https://graph.facebook.com/v19.0"
SITE_URL  = "https://klassementet.dk"
BUCKET    = "news-images"

CATEGORY_LABELS = {
    "resultater":  "RESULTATER",
    "startliste":  "STARTLISTE",
    "startlist":   "STARTLISTE",
    "transfer":    "TRANSFER",
    "profil":      "PROFIL",
    "interview":   "INTERVIEW",
    "analyse":     "ANALYSE",
    "analysis":    "ANALYSE",
    "generelt":    "NYHEDER",
    "general":     "NYHEDER",
    "race_report": "LØBSRAPPORT",
}

CATEGORY_EMOJI = {
    "resultater": "🏆", "startliste": "📋", "startlist": "📋",
    "transfer": "🔄", "profil": "👤", "interview": "🎙️",
    "analyse": "📊", "analysis": "📊", "generelt": "🚴",
    "general": "🚴", "race_report": "🏁",
}

# ── Font ─────────────────────────────────────────────────────────────────────

_FONT_DIR   = Path(__file__).parent / "fonts"
_BEBAS_PATH = _FONT_DIR / "BebasNeue-Regular.ttf"
_BEBAS_URL  = (
    "https://raw.githubusercontent.com/dharmatype/Bebas-Neue"
    "/master/Fonts/BN%20Regular/BebasNeue-Regular.ttf"
)
_bebas_cache: str | None = None


def _get_bebas() -> str | None:
    global _bebas_cache
    if _bebas_cache and Path(_bebas_cache).exists():
        return _bebas_cache
    if _BEBAS_PATH.exists():
        _bebas_cache = str(_BEBAS_PATH)
        return _bebas_cache
    try:
        resp = requests.get(_BEBAS_URL, timeout=12)
        if resp.ok and len(resp.content) > 5000:
            _FONT_DIR.mkdir(exist_ok=True)
            _BEBAS_PATH.write_bytes(resp.content)
            _bebas_cache = str(_BEBAS_PATH)
            return _bebas_cache
    except Exception:
        pass
    for p in [
        "C:/Windows/Fonts/impact.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        if Path(p).exists():
            return p
    return None


def _font(size: int, bebas: bool = False):
    if bebas:
        path = _get_bebas()
        if path:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    for p in [
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap(text: str, font, max_w: int, draw: ImageDraw.ImageDraw) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for word in words:
        test = f"{cur} {word}".strip()
        if draw.textbbox((0, 0), test, font=font)[2] <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


# ── Billedgenerering ──────────────────────────────────────────────────────────

def generate_fb_image(title: str, category: str, excerpt: str | None = None) -> "Image.Image":
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Baggrundsgradient
    for y in range(H):
        t = y / H
        c = tuple(int(BG[i] + (BG2[i] - BG[i]) * t) for i in range(3))
        draw.line([(0, y), (W, y)], fill=c)

    # Bjergsilhuet
    peaks = [
        (0, H), (0, H - 55), (90, H - 145), (170, H - 75), (265, H - 185),
        (355, H - 108), (445, H - 230), (510, H - 155), (595, H - 278),
        (660, H - 205), (735, H - 256), (815, H - 172), (885, H - 238),
        (955, H - 163), (1035, H - 205), (1110, H - 128), (1200, H - 162), (1200, H),
    ]
    draw.polygon(peaks, fill=DARK)

    # Emerald top/bund-bar
    draw.rectangle([(0, 0), (W, 6)], fill=EMERALD)
    draw.rectangle([(0, H - 6), (W, H)], fill=EMERALD)

    # Vandmærke: stort "K" til venstre
    k_font = _font(440, bebas=True)
    draw.text((50, H // 2 + 15), "K", font=k_font, fill=(20, 35, 65), anchor="lm")

    # Vertikal emerald-separator
    SEP_X = 370
    draw.rectangle([(SEP_X, 48), (SEP_X + 4, H - 48)], fill=EMERALD)

    # Tekstområde til højre for separator
    TX = SEP_X + 44
    TW = W - TX - 48
    TY = 62

    # KLASSEMENTET.DK
    hdr = _font(21)
    draw.text((TX, TY), "KLASSEMENTET.DK", font=hdr, fill=EMERALD)
    TY += 34

    # Kategori-dot + label
    draw.ellipse([(TX, TY + 7), (TX + 11, TY + 18)], fill=EMERALD)
    cat_label = CATEGORY_LABELS.get(category, category.upper())
    cat_f = _font(17)
    draw.text((TX + 18, TY + 4), cat_label, font=cat_f, fill=GRAY)
    TY += 42

    # Overskrift i Bebas Neue
    title_f   = _font(92, bebas=True)
    title_lines = _wrap(title, title_f, TW, draw)
    for line in title_lines[:4]:
        lh = draw.textbbox((0, 0), line, font=title_f)[3]
        draw.text((TX, TY), line, font=title_f, fill=WHITE)
        TY += int(lh * 0.92)

    # Excerpt
    if excerpt and TY < H - 105:
        TY += 14
        exc_f = _font(23)
        for line in _wrap(excerpt[:220], exc_f, TW, draw)[:2]:
            draw.text((TX, TY), line, font=exc_f, fill=GRAY)
            TY += 30

    # URL nederst til højre
    url_f = _font(19)
    draw.text((W - 38, H - 26), "klassementet.dk →", font=url_f, fill=GRAY, anchor="rm")

    return img


# ── Upload til Supabase Storage ───────────────────────────────────────────────

def _upload(img: "Image.Image", slug: str, sb_url: str, sb_key: str) -> str | None:
    h = {"apikey": sb_key, "Authorization": f"Bearer {sb_key}"}
    requests.post(
        f"{sb_url}/storage/v1/bucket",
        json={"id": BUCKET, "name": BUCKET, "public": True},
        headers={**h, "Content-Type": "application/json"},
        timeout=10,
    )
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=88, optimize=True)
    res = requests.post(
        f"{sb_url}/storage/v1/object/{BUCKET}/fb_{slug}.jpg",
        data=buf.getvalue(),
        headers={**h, "Content-Type": "image/jpeg", "x-upsert": "true"},
        timeout=20,
    )
    if not res.ok:
        return None
    return f"{sb_url}/storage/v1/object/public/{BUCKET}/fb_{slug}.jpg"


# ── Facebook photo post ───────────────────────────────────────────────────────

def _fb_post(article_id: str, slug: str, title: str, category: str,
             excerpt: str | None, image_url: str,
             token: str, page_id: str, sb_url: str, sb_key: str) -> bool:
    emoji   = CATEGORY_EMOJI.get(category, "🚴")
    art_url = f"{SITE_URL}/nyheder/{slug}"
    parts   = [f"{emoji} {title}"]
    if excerpt:
        parts += ["", excerpt]
    parts += ["", f"🔗 {art_url}"]

    res = requests.post(
        f"{GRAPH_URL}/{page_id}/photos",
        data={"url": image_url, "caption": "\n".join(parts), "access_token": token},
        timeout=20,
    )
    if res.ok:
        h = {
            "apikey": sb_key, "Authorization": f"Bearer {sb_key}",
            "Content-Type": "application/json", "Prefer": "return=minimal",
        }
        requests.patch(
            f"{sb_url}/rest/v1/news_articles?id=eq.{article_id}",
            json={"social_posted": True},
            headers=h,
            timeout=10,
        )
    return res.ok


# ── Background-task entry point ───────────────────────────────────────────────

def generate_and_post(
    article_id: str,
    slug: str,
    title: str,
    category: str,
    excerpt: str | None,
    existing_image_url: str | None,
    sb_url: str,
    sb_key: str,
    meta_token: str,
    page_id: str,
) -> None:
    """Kaldes som FastAPI BackgroundTask efter en artikel publiceres."""
    if not meta_token or not page_id:
        return

    if existing_image_url:
        image_url = existing_image_url
    else:
        if not PILLOW_AVAILABLE:
            print(f"[FB] Pillow ikke installeret — kan ikke generere billede til {slug}")
            return
        try:
            img       = generate_fb_image(title, category, excerpt)
            image_url = _upload(img, slug, sb_url, sb_key)
        except Exception as e:
            print(f"[FB] Billedgenerering fejl: {e}")
            return

    if not image_url:
        print(f"[FB] Ingen image_url til {slug}")
        return

    # Gem image_url på artiklen hvis den manglede
    if not existing_image_url:
        h = {
            "apikey": sb_key, "Authorization": f"Bearer {sb_key}",
            "Content-Type": "application/json", "Prefer": "return=minimal",
        }
        requests.patch(
            f"{sb_url}/rest/v1/news_articles?id=eq.{article_id}",
            json={"image_url": image_url},
            headers=h,
            timeout=10,
        )

    ok = _fb_post(article_id, slug, title, category, excerpt,
                  image_url, meta_token, page_id, sb_url, sb_key)
    print(f"[FB] {'✓' if ok else '✗'} {title[:65]}")
