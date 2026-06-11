"""
instagram_carousel.py
Genererer "Dagens Nyheder" Instagram-karrusel med alle artikler publiceret i dag.
Poster som carousel via Meta Graph API og gemmer slides lokalt til TikTok.
"""

import time
import requests
from io import BytesIO
from pathlib import Path
from datetime import date

try:
    from PIL import Image, ImageDraw
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

from fb_article_image import (
    BG, BG2, EMERALD, WHITE, GRAY, DARK,
    CATEGORY_LABELS, CATEGORY_EMOJI,
    _font, _wrap, GRAPH_URL, BUCKET,
)

W, H = 1080, 1080
OUTPUT_DIR = Path(__file__).parent / "output" / "instagram"


def _mountain_bg(draw: "ImageDraw.ImageDraw", img: "Image.Image") -> None:
    """Tegner gradient-baggrund + bjergsilhuet + top/bund-bar."""
    for y in range(H):
        t = y / H
        c = tuple(int(BG[i] + (BG2[i] - BG[i]) * t) for i in range(3))
        draw.line([(0, y), (W, y)], fill=c)
    peaks = [
        (0, H), (0, H - 95), (110, H - 245), (210, H - 145), (330, H - 315),
        (440, H - 198), (545, H - 390), (635, H - 275), (725, H - 415),
        (830, H - 310), (920, H - 375), (1000, H - 258), (1080, H - 300),
        (1080, H),
    ]
    draw.polygon(peaks, fill=DARK)
    draw.rectangle([(0, 0), (W, 8)], fill=EMERALD)
    draw.rectangle([(0, H - 8), (W, H)], fill=EMERALD)


def _paste_logo(img: "Image.Image", size: int = 96) -> int:
    """Indsætter logo øverst til venstre, returnerer x-position efter logo."""
    try:
        from instagram_image import _get_logo
        logo = _get_logo(size)
        if logo:
            img.paste(logo, (36, 28), logo)
            return 36 + size + 18
    except Exception:
        pass
    return 36


def generate_carousel_slide(title: str, category: str, slide_num: int, total: int) -> "Image.Image":
    """Genererer 1080x1080 artikel-slide til karrusel."""
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    _mountain_bg(draw, img)

    logo_end_x = _paste_logo(img)

    # KLASSEMENTET.DK header
    draw.text((logo_end_x, 52), "KLASSEMENTET.DK", font=_font(22), fill=EMERALD)

    # Slide-tæller badge (N/total) øverst til højre
    badge_text = f"{slide_num}/{total}"
    badge_font = _font(20)
    bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw, bh = bbox[2] - bbox[0] + 24, bbox[3] - bbox[1] + 12
    bx, by = W - 36 - bw, 36
    draw.rounded_rectangle([(bx, by), (bx + bw, by + bh)], radius=8, fill=DARK, outline=EMERALD)
    draw.text((bx + 12, by + 6), badge_text, font=badge_font, fill=EMERALD)

    # Separator
    draw.rectangle([(36, 140), (W - 36, 144)], fill=EMERALD)

    # Kategori
    TX, TW = 56, W - 112
    TY = 164
    draw.ellipse([(TX, TY + 8), (TX + 12, TY + 20)], fill=EMERALD)
    draw.text((TX + 22, TY + 4), CATEGORY_LABELS.get(category, category.upper()), font=_font(20), fill=GRAY)
    TY += 48

    # Overskrift
    title_font = _font(98, bebas=True)
    for line in _wrap(title, title_font, TW, draw)[:5]:
        lh = draw.textbbox((0, 0), line, font=title_font)[3]
        draw.text((TX, TY), line, font=title_font, fill=WHITE)
        TY += int(lh * 0.90)

    # Bund-CTA
    draw.text((W // 2, H - 34), "Læs mere på klassementet.dk →", font=_font(24), fill=GRAY, anchor="mm")

    return img


def generate_cta_slide(article_count: int, date_label: str) -> "Image.Image":
    """Genererer afsluttende CTA-slide med dato og klassementet.dk."""
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    _mountain_bg(draw, img)

    # Logo centreret
    try:
        from instagram_image import _get_logo
        logo = _get_logo(120)
        if logo:
            img.paste(logo, ((W - 120) // 2, 190), logo)
    except Exception:
        pass

    draw.text((W // 2, 410), "DAGENS NYHEDER", font=_font(88, bebas=True), fill=WHITE, anchor="mm")
    draw.text((W // 2, 488), date_label, font=_font(28), fill=EMERALD, anchor="mm")
    draw.rectangle([(120, 528), (W - 120, 532)], fill=EMERALD)
    draw.text((W // 2, 620), "KLASSEMENTET.DK", font=_font(56, bebas=True), fill=EMERALD, anchor="mm")
    draw.text(
        (W // 2, 692),
        f"Alle {article_count} artikler klar til læsning →",
        font=_font(26), fill=GRAY, anchor="mm",
    )

    return img


def save_slides_locally(slides: list, date_str: str) -> Path:
    """Gemmer slides til output/instagram/YYYY-MM-DD/, returnerer mappen."""
    folder = OUTPUT_DIR / date_str
    folder.mkdir(parents=True, exist_ok=True)
    for i, img in enumerate(slides, 1):
        img.save(folder / f"slide_{i:02d}.jpg", format="JPEG", quality=92, optimize=True)
    return folder


def _upload_slide(img, filename: str, sb_url: str, sb_key: str) -> str | None:
    """Upload slide til Supabase Storage, returnerer public URL."""
    sb_url = sb_url.rstrip("/")
    h = {"apikey": sb_key, "Authorization": f"Bearer {sb_key}"}
    requests.post(
        f"{sb_url}/storage/v1/bucket",
        json={"id": BUCKET, "name": BUCKET, "public": True},
        headers={**h, "Content-Type": "application/json"},
        timeout=10,
    )
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=92, optimize=True)
    res = requests.post(
        f"{sb_url}/storage/v1/object/{BUCKET}/{filename}",
        data=buf.getvalue(),
        headers={**h, "Content-Type": "image/jpeg", "x-upsert": "true"},
        timeout=20,
    )
    if not res.ok:
        print(f"[Carousel] Upload fejl {res.status_code}: {res.text[:200]}")
        return None
    return f"{sb_url}/storage/v1/object/public/{BUCKET}/{filename}"


def _post_carousel_api(image_urls: list[str], caption: str, meta_token: str, ig_user_id: str) -> str | None:
    """
    Poster karrusel via Meta Graph API (3-trins flow).
    Returnerer media_id ved succes, None ved fejl.
    """
    # Trin 1: opret item-containers
    item_ids = []
    for url in image_urls:
        res = requests.post(
            f"{GRAPH_URL}/{ig_user_id}/media",
            data={"image_url": url, "is_carousel_item": "true", "access_token": meta_token},
            timeout=20,
        )
        if not res.ok:
            print(f"[Carousel] Item-container fejl: {res.text[:200]}")
            return None
        item_id = res.json().get("id")
        if not item_id:
            return None
        item_ids.append(item_id)
        time.sleep(1)

    # Trin 2: opret carousel-container
    res2 = requests.post(
        f"{GRAPH_URL}/{ig_user_id}/media",
        data={
            "media_type": "CAROUSEL",
            "children": ",".join(item_ids),
            "caption": caption,
            "access_token": meta_token,
        },
        timeout=20,
    )
    if not res2.ok:
        print(f"[Carousel] Container fejl: {res2.text[:200]}")
        return None
    carousel_id = res2.json().get("id")
    if not carousel_id:
        return None

    time.sleep(5)  # Instagram behandler carousel-containers langsommere end enkeltbilleder

    # Trin 3: publicér
    res3 = requests.post(
        f"{GRAPH_URL}/{ig_user_id}/media_publish",
        data={"creation_id": carousel_id, "access_token": meta_token},
        timeout=20,
    )
    if not res3.ok:
        print(f"[Carousel] Publish fejl: {res3.text[:200]}")
        return None

    media_id = res3.json().get("id")
    print(f"[Carousel] ✓ Postet karrusel: {media_id}")
    return media_id


def post_dagens_nyheder(
    articles: list[dict],
    sb_url: str,
    sb_key: str,
    meta_token: str,
    ig_user_id: str,
) -> dict:
    """
    Orkestrator: genererer slides, gemmer lokalt, uploader og poster karrusel.
    Returnerer {"ok": bool, "slides": int, "ig_post_id": str|None, "saved_path": str, "error": str|None}
    """
    if not articles:
        return {"ok": False, "slides": 0, "ig_post_id": None, "saved_path": "", "error": "Ingen artikler publiceret i dag"}

    if not PILLOW_AVAILABLE:
        return {"ok": False, "slides": 0, "ig_post_id": None, "saved_path": "", "error": "Pillow ikke installeret på serveren"}

    today = date.today().isoformat()

    # Instagram max 10 items: brug op til 9 artikel-slides + 1 CTA
    article_batch = articles[:9]
    total_slides = len(article_batch) + 1

    # Generer slides
    slides = []
    for i, art in enumerate(article_batch, 1):
        slides.append(generate_carousel_slide(art["title"], art.get("category", "generelt"), i, total_slides))
    slides.append(generate_cta_slide(len(articles), today))

    # Gem lokalt
    saved_folder = save_slides_locally(slides, today)
    saved_path = str(saved_folder)
    print(f"[Carousel] Gemt {len(slides)} slides til {saved_path}")

    if not meta_token or not ig_user_id:
        return {"ok": False, "slides": len(slides), "ig_post_id": None, "saved_path": saved_path, "error": "META_PAGE_ACCESS_TOKEN eller META_INSTAGRAM_USER_ID mangler i Railway"}

    # Upload alle slides
    image_urls = []
    for i, slide in enumerate(slides, 1):
        filename = f"carousel_{today}_slide_{i:02d}.jpg"
        url = _upload_slide(slide, filename, sb_url, sb_key)
        if not url:
            return {"ok": False, "slides": len(slides), "ig_post_id": None, "saved_path": saved_path, "error": f"Upload fejl på slide {i}"}
        image_urls.append(url)

    # Byg caption
    caption_lines = [f"📰 DAGENS NYHEDER — {today}", ""]
    for art in article_batch:
        emoji = CATEGORY_EMOJI.get(art.get("category", "generelt"), "🚴")
        caption_lines.append(f"{emoji} {art['title']}")
    caption_lines += [
        "",
        "Swipe for at se alle overskrifter 👉",
        "Læs de fulde artikler på klassementet.dk",
        "",
        "#klassementet #cykling #cycling #UCI #WorldTour #cykelsport #ProCycling",
    ]
    caption = "\n".join(caption_lines)

    # Edge case: kun 1 slide → post som enkelt billede (carousel kræver min. 2)
    if len(image_urls) == 1:
        res = requests.post(
            f"{GRAPH_URL}/{ig_user_id}/media",
            data={"image_url": image_urls[0], "caption": caption, "access_token": meta_token},
            timeout=20,
        )
        if not res.ok:
            return {"ok": False, "slides": 1, "ig_post_id": None, "saved_path": saved_path, "error": f"Single-post fejl: {res.text[:200]}"}
        container_id = res.json().get("id")
        time.sleep(4)
        res2 = requests.post(
            f"{GRAPH_URL}/{ig_user_id}/media_publish",
            data={"creation_id": container_id, "access_token": meta_token},
            timeout=20,
        )
        post_id = res2.json().get("id") if res2.ok else None
        return {
            "ok": bool(post_id), "slides": 1, "ig_post_id": post_id,
            "saved_path": saved_path,
            "error": None if post_id else "Single-post publish fejl",
        }

    # Post som karrusel (2-10 slides)
    post_id = _post_carousel_api(image_urls, caption, meta_token, ig_user_id)
    return {
        "ok": bool(post_id),
        "slides": len(slides),
        "ig_post_id": post_id,
        "saved_path": saved_path,
        "error": None if post_id else "Karrusel-posting fejl — se Railway logs",
    }


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    test_articles = [
        {"title": "Vingegaard vinder Alpe d'Huez i strålende stil", "category": "resultater"},
        {"title": "Pogačar angriber fra 80 km og ingen kan følge med", "category": "race_report"},
        {"title": "Van der Poel bekræfter start i Tour de France", "category": "transfer"},
    ]

    today = date.today().isoformat()
    slides = []
    total = len(test_articles) + 1
    for i, art in enumerate(test_articles, 1):
        slides.append(generate_carousel_slide(art["title"], art["category"], i, total))
    slides.append(generate_cta_slide(len(test_articles), today))

    folder = save_slides_locally(slides, f"test-{today}")
    print(f"Preview gemt i: {folder}")
    for f in sorted(folder.iterdir()):
        print(f"  {f.name}")
