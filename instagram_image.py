"""
instagram_image.py
Genererer 1080x1080 Instagram-billeder med Klassementet-branding.
K+cykelist-logoet er integreret i designet.
Poster automatisk til Instagram via Meta Graph API.
"""

import os
import time
import requests
from io import BytesIO
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

from fb_article_image import (
    BG, BG2, EMERALD, WHITE, GRAY, DARK,
    CATEGORY_LABELS, CATEGORY_EMOJI,
    _get_bebas, _font, _wrap, GRAPH_URL, SITE_URL, BUCKET,
)

W, H = 1080, 1080


def _get_logo(size: int = 90) -> "Image.Image | None":
    """Indlæs K+cykelist-logoet fra assets/ eller generer det."""
    assets_dir = Path(__file__).parent / "assets"
    logo_path = assets_dir / "logo_80.png" if size <= 80 else assets_dir / "logo_200.png"

    if logo_path.exists():
        try:
            return Image.open(logo_path).convert("RGBA").resize((size, size), Image.LANCZOS)
        except Exception:
            pass

    try:
        from brand_logo import make_logo
        return make_logo(size).convert("RGBA")
    except Exception:
        return None


def generate_ig_image(title: str, category: str, excerpt: str | None = None) -> "Image.Image":
    """Genererer 1080x1080 Instagram-post billede."""
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Baggrundsgradient
    for y in range(H):
        t = y / H
        c = tuple(int(BG[i] + (BG2[i] - BG[i]) * t) for i in range(3))
        draw.line([(0, y), (W, y)], fill=c)

    # Bjergsilhuet (nedre del)
    peaks = [
        (0, H), (0, H - 95), (110, H - 245), (210, H - 145), (330, H - 315),
        (440, H - 198), (545, H - 390), (635, H - 275), (725, H - 415),
        (830, H - 310), (920, H - 375), (1000, H - 258), (1080, H - 300),
        (1080, H),
    ]
    draw.polygon(peaks, fill=DARK)

    # Emerald top/bund-bar
    draw.rectangle([(0, 0),    (W, 8)],    fill=EMERALD)
    draw.rectangle([(0, H-8),  (W, H)],    fill=EMERALD)

    # K+cykelist-logo øverst til venstre
    logo = _get_logo(96)
    if logo:
        img.paste(logo, (36, 28), logo)
        logo_end_x = 36 + 96 + 18
    else:
        logo_end_x = 36

    # KLASSEMENTET.DK header
    hdr_font = _font(22)
    draw.text((logo_end_x, 52), "KLASSEMENTET.DK", font=hdr_font, fill=EMERALD)

    # Horizontal separator under header
    draw.rectangle([(36, 140), (W - 36, 144)], fill=EMERALD)

    # Kategori-label
    TY = 164
    TX = 56
    TW = W - TX - 56

    draw.ellipse([(TX, TY + 8), (TX + 12, TY + 20)], fill=EMERALD)
    cat_label = CATEGORY_LABELS.get(category, category.upper())
    cat_font  = _font(20)
    draw.text((TX + 22, TY + 4), cat_label, font=cat_font, fill=GRAY)
    TY += 48

    # Artikel-titel i Bebas Neue
    title_font  = _font(98, bebas=True)
    title_lines = _wrap(title, title_font, TW, draw)
    for line in title_lines[:5]:
        lh = draw.textbbox((0, 0), line, font=title_font)[3]
        draw.text((TX, TY), line, font=title_font, fill=WHITE)
        TY += int(lh * 0.90)

    # Excerpt
    if excerpt and TY < H - 180:
        TY += 22
        exc_font  = _font(27)
        exc_lines = _wrap(excerpt[:200], exc_font, TW, draw)
        for line in exc_lines[:3]:
            draw.text((TX, TY), line, font=exc_font, fill=GRAY)
            TY += 36

    # URL og CTA
    cta_font = _font(24)
    draw.text(
        (W // 2, H - 34),
        "Læs mere på klassementet.dk →",
        font=cta_font, fill=GRAY, anchor="mm",
    )

    return img


def _upload_ig(img: "Image.Image", slug: str, sb_url: str, sb_key: str) -> str | None:
    """Upload IG-billede til Supabase Storage, returnerer public URL."""
    h = {"apikey": sb_key, "Authorization": f"Bearer {sb_key}"}
    requests.post(
        f"{sb_url}/storage/v1/bucket",
        json={"id": BUCKET, "name": BUCKET, "public": True},
        headers={**h, "Content-Type": "application/json"},
        timeout=10,
    )
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90, optimize=True)
    res = requests.post(
        f"{sb_url}/storage/v1/object/{BUCKET}/ig_{slug}.jpg",
        data=buf.getvalue(),
        headers={**h, "Content-Type": "image/jpeg", "x-upsert": "true"},
        timeout=20,
    )
    if not res.ok:
        return None
    return f"{sb_url}/storage/v1/object/public/{BUCKET}/ig_{slug}.jpg"


def _post_instagram(
    article_id: str,
    slug: str,
    title: str,
    category: str,
    excerpt: str | None,
    image_url: str,
    meta_token: str,
    ig_user_id: str,
    sb_url: str,
    sb_key: str,
) -> bool:
    """2-trins Instagram-posting via Meta Graph API."""
    emoji    = CATEGORY_EMOJI.get(category, "🚴")
    art_url  = f"{SITE_URL}/nyheder/{slug}"
    hashtags = (
        "#klassementet #cykling #cycling #UCI #WorldTour "
        "#cykelsport #ProCycling"
    )
    caption_parts = [f"{emoji} {title}", ""]
    if excerpt:
        caption_parts.append(excerpt[:150] + ("…" if len(excerpt) > 150 else ""))
    caption_parts += ["", f"Læs mere på klassementet.dk", "", hashtags]
    caption = "\n".join(caption_parts)

    # Trin 1: opret media container
    res1 = requests.post(
        f"{GRAPH_URL}/{ig_user_id}/media",
        data={"image_url": image_url, "caption": caption, "access_token": meta_token},
        timeout=20,
    )
    if not res1.ok:
        print(f"[IG] Media container fejl {res1.status_code}: {res1.text[:200]}")
        return False

    container_id = res1.json().get("id")
    if not container_id:
        return False

    time.sleep(4)  # vent på Instagram-behandling

    # Trin 2: publicér
    res2 = requests.post(
        f"{GRAPH_URL}/{ig_user_id}/media_publish",
        data={"creation_id": container_id, "access_token": meta_token},
        timeout=20,
    )
    if res2.ok:
        h = {
            "apikey": sb_key, "Authorization": f"Bearer {sb_key}",
            "Content-Type": "application/json", "Prefer": "return=minimal",
        }
        requests.patch(
            f"{sb_url}/rest/v1/news_articles?id=eq.{article_id}",
            json={"instagram_posted": True},
            headers=h, timeout=10,
        )
        print(f"[IG] ✓ Postet: {res2.json().get('id', '?')}")
        return True

    print(f"[IG] Publish fejl {res2.status_code}: {res2.text[:200]}")
    return False


def generate_and_post_ig(
    article_id: str,
    slug: str,
    title: str,
    category: str,
    excerpt: str | None,
    existing_image_url: str | None,
    sb_url: str,
    sb_key: str,
    meta_token: str,
    ig_user_id: str,
) -> None:
    """Baggrunds-task: generer IG-billede og post til Instagram."""
    if not meta_token or not ig_user_id:
        return

    if existing_image_url and "ig_" in existing_image_url:
        image_url = existing_image_url
    else:
        if not PILLOW_AVAILABLE:
            print(f"[IG] Pillow ikke installeret — kan ikke generere billede til {slug}")
            return
        try:
            img       = generate_ig_image(title, category, excerpt)
            image_url = _upload_ig(img, slug, sb_url, sb_key)
        except Exception as e:
            print(f"[IG] Billedgenerering fejl: {e}")
            return

    if not image_url:
        print(f"[IG] Ingen image_url til {slug}")
        return

    ok = _post_instagram(
        article_id, slug, title, category, excerpt,
        image_url, meta_token, ig_user_id, sb_url, sb_key,
    )
    print(f"[IG] {'✓' if ok else '✗'} {title[:65]}")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    img = generate_ig_image(
        "Vingegaard vinder Alpe d'Huez-etapen i strålende stil",
        "resultater",
        "Jonas Vingegaard satte et imponerende tempo på de sidste kilometer og distancerede alle rivaler.",
    )
    img.save("ig_preview.png")
    print("Preview: ig_preview.png")
