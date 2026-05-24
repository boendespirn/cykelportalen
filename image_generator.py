"""
image_generator.py
Genererer thumbnail-billeder til nyheder med Python Pillow (gratis, ingen API).

Layout (1200x630):
  - Mørk baggrund (#0f172a, slate-950)
  - Emerald gradient-stribe øverst og nede
  - Venstre halvdel: rytterfoto (hvis tilgængeligt) med mørkt overlay
  - Højre halvdel / fuld: overskrift + excerpt + logo
  - Bundlinje: Klassementet · klassementet.dk

Krav: pip install Pillow requests

Kør:
  python image_generator.py --article <slug>
  python image_generator.py --all           (genererer billeder til alle artikler uden billede)
"""

import os
import sys
import io
import re
import argparse
import requests
from pathlib import Path
from io import BytesIO
from datetime import datetime
from dotenv import load_dotenv

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("FEJL: Pillow ikke installeret. Kør: pip install Pillow")
    sys.exit(1)

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

AUTH_HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
DB_HEADERS   = {**AUTH_HEADERS, "Content-Type": "application/json", "Prefer": "return=minimal"}

# ── Canvas-mål ────────────────────────────────────────────────────────────────
W, H = 1200, 630

# Farver (slate-950 palette)
BG_COLOR      = (15, 23, 42)       # slate-950
ACCENT_COLOR  = (16, 185, 129)     # emerald-500
TEXT_PRIMARY  = (248, 250, 252)    # slate-50
TEXT_SECONDARY = (148, 163, 184)   # slate-400
TEXT_DIM      = (71, 85, 105)      # slate-600
OVERLAY_COLOR = (0, 0, 0, 180)     # semi-transparent black

SITE_NAME = "KLASSEMENTET.DK"

# ── Font helpers ──────────────────────────────────────────────────────────────

def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Prøver Windows system fonts; falder tilbage til standard."""
    candidates = []
    if bold:
        candidates = [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
    else:
        candidates = [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibri.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def wrap_text(text: str, font, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """Brekker tekst i linjer der passer inden for max_width."""
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


# ── Billedgenerering ──────────────────────────────────────────────────────────

def fetch_image(url: str) -> Image.Image | None:
    """Henter billede fra URL, returnerer PIL Image."""
    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Klassementet/1.0"})
        if resp.ok:
            return Image.open(BytesIO(resp.content)).convert("RGBA")
    except Exception:
        pass
    return None


def generate_thumbnail(
    title: str,
    excerpt: str | None,
    category: str,
    rider_photo_url: str | None = None,
    race_name: str | None = None,
) -> Image.Image:
    """Bygger et 1200×630 thumbnail."""

    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # ── Baggrundsbillede (rytterfoto) ──────────────────────────────────────
    has_photo = False
    if rider_photo_url:
        photo = fetch_image(rider_photo_url)
        if photo:
            # Resize og placer i venstre halvdel
            photo_w = W // 2
            aspect  = photo.height / photo.width
            photo_h = int(photo_w * aspect)
            photo   = photo.resize((photo_w, max(H, photo_h)), Image.LANCZOS)
            # Crop til venstre halvdel
            photo_crop = photo.crop((0, 0, photo_w, H))
            # Konvertér til RGB for kompatibilitet
            if photo_crop.mode == "RGBA":
                bg = Image.new("RGB", photo_crop.size, BG_COLOR)
                bg.paste(photo_crop, mask=photo_crop.split()[3])
                photo_crop = bg
            img.paste(photo_crop, (0, 0))
            has_photo = True

    # ── Gradienter og overlays ─────────────────────────────────────────────

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov_draw  = ImageDraw.Draw(overlay)

    if has_photo:
        # Mørkt overlay over hele billedet, stærkere i højre halvdel
        for x in range(W):
            alpha = int(120 + (x / W) * 100) if x < W // 2 else 200
            ov_draw.line([(x, 0), (x, H)], fill=(0, 0, 0, alpha))
    else:
        # Subtil pattern-baggrund med diagonale linjer
        for i in range(0, W + H, 40):
            ov_draw.line([(i, 0), (0, i)], fill=(255, 255, 255, 5), width=1)

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # ── Emerald accent-bar øverst ──────────────────────────────────────────
    draw.rectangle([(0, 0), (W, 5)], fill=ACCENT_COLOR)

    # ── Emerald accent-bar nederst ─────────────────────────────────────────
    draw.rectangle([(0, H - 5), (W, H)], fill=ACCENT_COLOR)

    # ── Text-område ────────────────────────────────────────────────────────
    text_x     = W // 2 + 40 if has_photo else 60
    text_w     = W - text_x - 50
    text_y_start = 60

    # Kategori-label (lille, emerald)
    cat_font = load_font(18, bold=False)
    cat_labels = {
        "resultater": "RESULTATER", "startliste": "STARTLISTE",
        "transfer": "TRANSFER", "profil": "PROFIL",
        "analyse": "ANALYSE", "generelt": "NYHEDER",
    }
    cat_text = cat_labels.get(category, category.upper())
    draw.text((text_x, text_y_start), cat_text, font=cat_font, fill=ACCENT_COLOR)
    text_y = text_y_start + 34

    # Løbsnavn (hvis tilgængeligt)
    if race_name:
        race_font = load_font(20, bold=False)
        draw.text((text_x, text_y), race_name, font=race_font, fill=TEXT_SECONDARY)
        text_y += 28

    text_y += 10

    # Overskrift (stor, fed)
    title_font = load_font(44, bold=True)
    title_lines = wrap_text(title, title_font, text_w, draw)
    max_title_lines = 4
    for line in title_lines[:max_title_lines]:
        draw.text((text_x, text_y), line, font=title_font, fill=TEXT_PRIMARY)
        text_y += 52

    text_y += 20

    # Excerpt (lille)
    if excerpt and text_y < H - 120:
        exc_font  = load_font(22, bold=False)
        exc_lines = wrap_text(excerpt, exc_font, text_w, draw)
        for line in exc_lines[:3]:
            draw.text((text_x, text_y), line, font=exc_font, fill=TEXT_SECONDARY)
            text_y += 28

    # ── Site-branding (bunden) ─────────────────────────────────────────────
    logo_font = load_font(20, bold=True)
    logo_text = SITE_NAME
    draw.text((text_x, H - 50), logo_text, font=logo_font, fill=ACCENT_COLOR)

    # Dato
    date_font = load_font(16, bold=False)
    date_str  = datetime.now().strftime("%-d. %B %Y") if sys.platform != "win32" else datetime.now().strftime("%d. %m. %Y")
    draw.text((text_x + 220, H - 47), date_str, font=date_font, fill=TEXT_DIM)

    return img


# ── Supabase Storage upload ───────────────────────────────────────────────────

BUCKET = "news-images"


def ensure_bucket() -> None:
    """Opret bucket hvis den ikke eksisterer (idempotent)."""
    res = requests.post(
        f"{SUPABASE_URL}/storage/v1/bucket",
        json={"id": BUCKET, "name": BUCKET, "public": True},
        headers={**AUTH_HEADERS, "Content-Type": "application/json"},
    )
    # 400 = already exists — det er OK


def upload_image(img: Image.Image, slug: str) -> str | None:
    """Gemmer PIL Image til Supabase Storage og returnerer public URL."""
    ensure_bucket()

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    buf.seek(0)

    path = f"{slug}.jpg"
    res  = requests.post(
        f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{path}",
        data=buf.read(),
        headers={
            **AUTH_HEADERS,
            "Content-Type": "image/jpeg",
            "x-upsert": "true",
        },
    )
    if not res.ok:
        print(f"  [Storage FEJL] {res.status_code}: {res.text[:100]}")
        return None

    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{path}"


def update_article_image(article_id: str, image_url: str) -> None:
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/news_articles?id=eq.{article_id}",
        json={"image_url": image_url},
        headers=DB_HEADERS,
    )


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_articles_without_image(limit: int = 20) -> list[dict]:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/news_articles"
        f"?image_url=is.null&is_advertorial=eq.false"
        f"&select=id,slug,title,excerpt,category,races(name,slug)"
        f"&order=published_at.desc&limit={limit}",
        headers=AUTH_HEADERS,
    )
    return res.json() if res.ok else []


def get_article_by_slug(slug: str) -> dict | None:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/news_articles"
        f"?slug=eq.{slug}&select=id,slug,title,excerpt,category,image_url,races(name,slug)&limit=1",
        headers=AUTH_HEADERS,
    )
    data = res.json()
    return data[0] if res.ok and data else None


def get_rider_photo_for_article(article: dict) -> str | None:
    """Prøver at finde et rytterfoto via artikelindhold — simpelt navnematch."""
    return None  # Kan udvides: søg i riders tabel efter navne nævnt i titlen


# ── Main ──────────────────────────────────────────────────────────────────────

def process_article(article: dict) -> bool:
    race = article.get("races")
    rider_photo = get_rider_photo_for_article(article)

    print(f"  Genererer: {article['title'][:60]}")
    img = generate_thumbnail(
        title=article["title"],
        excerpt=article.get("excerpt"),
        category=article.get("category", "generelt"),
        rider_photo_url=rider_photo,
        race_name=race["name"] if race else None,
    )
    url = upload_image(img, article["slug"])
    if url:
        update_article_image(article["id"], url)
        print(f"  -> {url}")
        return True
    return False


def run(slug: str | None, process_all: bool, limit: int) -> None:
    print(f"image_generator.py — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    if slug:
        article = get_article_by_slug(slug)
        if not article:
            print(f"Artikel ikke fundet: {slug}")
            return
        process_article(article)
    elif process_all:
        articles = get_articles_without_image(limit)
        print(f"Fandt {len(articles)} artikler uden billede\n")
        done = sum(1 for a in articles if process_article(a))
        print(f"\nFærdig: {done}/{len(articles)} genereret")
    else:
        print("Brug --article <slug> eller --all")
        print("Eksempel: python image_generator.py --all")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--article", help="Artikel-slug")
    parser.add_argument("--all",     action="store_true", help="Generer til alle artikler uden billede")
    parser.add_argument("--limit",   type=int, default=20, help="Max artikler (default: 20)")
    args = parser.parse_args()
    run(args.article, args.all, args.limit)
