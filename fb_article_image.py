"""
fb_article_image.py
Genererer 1200x630 Facebook-billeder med Klassementet-branding og artiklens
overskrift i Bebas Neue, og poster dem på Facebook-siden som foto-opslag med
linket i første kommentar.

Bruges af ai_news_processor.py (automatisk publicering) og api.py (godkend).

Gennemgået 2026-11-08: pipelinen havde ikke postet et eneste opslag siden
juli. Nøglen var udløbet uden at nogen så det, skrifttypen blev hentet fra en
adresse, der var død (404), så billedet faldt tilbage på systemfonte, og en
lang overskrift blev klippet af uden varsel. Nu:
  - fontene ligger i repoet (fonts/, SIL OFL) — mangler de, fejler vi højt
    i stedet for at tegne med en nødfont,
  - overskriften skaleres, til den passer, og klippes aldrig stille,
  - en sides nøgle af typen USER byttes til sidens egen nøgle (/me/accounts),
  - hver fejl fra Facebook logges med Facebooks egen besked,
  - token_status() bruges af morgenbeskeden, så en udløbet nøgle ses samme dag.
"""

import os
from io import BytesIO
from pathlib import Path

import requests

try:
    from PIL import Image, ImageDraw, ImageFont
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

# ── Farver (klassementet.dk palette) ─────────────────────────────────────────
BG      = (10,  17,  34)
BG2     = (17,  27,  50)
EMERALD = (16, 185, 129)
EMERALD_DIM = (12, 74, 62)
WHITE   = (248, 250, 252)
GRAY    = (148, 163, 184)

W, H = 1200, 630
MARGIN = 72
GRAPH_URL = "https://graph.facebook.com/v23.0"
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
    "cykelcross":  "CYKELCROSS",
    "generelt":    "NYHEDER",
    "general":     "NYHEDER",
    "race_report": "LØBSRAPPORT",
}

CATEGORY_EMOJI = {
    "resultater": "🏆", "startliste": "📋", "startlist": "📋",
    "transfer": "🔄", "profil": "👤", "interview": "🎙️",
    "analyse": "📊", "analysis": "📊", "cykelcross": "🚵",
    "generelt": "🚴", "general": "🚴", "race_report": "🏁",
}

# ── Fonte (fonts/ i repoet: Bebas Neue og Geist, begge SIL OFL) ───────────────

_FONT_DIR = Path(__file__).parent / "fonts"
_BEBAS = _FONT_DIR / "BebasNeue-Regular.ttf"
_GEIST = _FONT_DIR / "Geist-Variable.ttf"


def _bebas(size: int):
    return ImageFont.truetype(str(_BEBAS), size)


def _geist(size: int, vaegt: str = "Medium"):
    f = ImageFont.truetype(str(_GEIST), size)
    try:
        f.set_variation_by_name(vaegt)
    except Exception:
        pass
    return f


def _wrap(text: str, font, max_w: int, draw: "ImageDraw.ImageDraw") -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for word in words:
        test = f"{cur} {word}".strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _tilpas_titel(title: str, draw, max_w: int, max_h: int):
    """Største skriftstørrelse, hvor hele overskriften er på højst 4 linjer
    inden for max_h. Passer den ikke selv ved mindste størrelse, afsluttes
    sidste linje med '…' — den klippes aldrig stille."""
    title = title.upper()
    for size in range(124, 55, -4):
        font = _bebas(size)
        lines = _wrap(title, font, max_w, draw)
        linjehoejde = int(size * 0.98)
        if len(lines) <= 4 and len(lines) * linjehoejde <= max_h \
                and all(draw.textlength(l, font=font) <= max_w for l in lines):
            return font, lines, linjehoejde
    font = _bebas(56)
    lines = _wrap(title, font, max_w, draw)[:4]
    while draw.textlength(lines[-1] + " …", font=font) > max_w and " " in lines[-1]:
        lines[-1] = lines[-1].rsplit(" ", 1)[0]
    lines[-1] += " …"
    return font, lines, int(56 * 0.98)


def _profil(draw) -> None:
    """En stigningsprofil i bunden — sidens kendetegn — tegnet som fyldt
    flade med en emerald kant."""
    pkt = [(0, 586), (70, 578), (140, 566), (190, 572), (250, 548), (310, 556),
           (370, 530), (430, 538), (480, 512), (540, 522), (600, 494), (650, 505),
           (700, 482), (760, 497), (820, 470), (870, 488), (930, 468), (990, 486),
           (1050, 474), (1110, 492), (1160, 486), (1200, 494)]
    draw.polygon(pkt + [(W, H), (0, H)], fill=EMERALD_DIM)
    draw.line(pkt, fill=EMERALD, width=4, joint="curve")


def generate_fb_image(title: str, category: str, excerpt: str | None = None) -> "Image.Image":
    """Opslagets billede. `excerpt` står i opslagsteksten og bruges ikke på
    billedet — to tekster på et lille feedbillede gør begge ulæselige."""
    if not (_BEBAS.exists() and _GEIST.exists()):
        raise FileNotFoundError(f"Fontene mangler i {_FONT_DIR} — tegner ikke med en nødfont")

    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        draw.line([(0, y), (W, y)], fill=tuple(int(BG[i] + (BG2[i] - BG[i]) * t) for i in range(3)))
    _profil(draw)

    # Top: ordmærke til venstre, kategori til højre
    draw.text((MARGIN, 56), "KLASSEMENTET", font=_bebas(44), fill=EMERALD)
    label = CATEGORY_LABELS.get(category, (category or "nyheder").upper())
    lf = _geist(20, "SemiBold")
    lw = draw.textlength(label, font=lf)
    x1, y1 = W - MARGIN, 58
    draw.rounded_rectangle([(x1 - lw - 36, y1), (x1, y1 + 40)], radius=20, outline=EMERALD, width=2)
    draw.text((x1 - lw / 2 - 18, y1 + 20), label, font=lf, fill=EMERALD, anchor="mm")

    # Overskriften, centreret lodret i feltet mellem top og profil
    top, bund = 130, 455
    font, lines, lh = _tilpas_titel(title, draw, W - 2 * MARGIN, bund - top)
    y = top + (bund - top - len(lines) * lh) // 2
    for line in lines:
        draw.text((MARGIN, y), line, font=font, fill=WHITE)
        y += lh

    draw.text((W - MARGIN, H - 34), "klassementet.dk", font=_geist(22, "Medium"),
              fill=WHITE, anchor="rm")
    return img


# ── Upload til Supabase Storage ───────────────────────────────────────────────

def _upload(img: "Image.Image", slug: str, sb_url: str, sb_key: str) -> str | None:
    sb_url = sb_url.rstrip("/")
    h = {"apikey": sb_key, "Authorization": f"Bearer {sb_key}"}
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=92, optimize=True)
    res = requests.post(
        f"{sb_url}/storage/v1/object/{BUCKET}/fb_{slug}.jpg",
        data=buf.getvalue(),
        headers={**h, "Content-Type": "image/jpeg", "x-upsert": "true"},
        timeout=20,
    )
    if not res.ok:
        print(f"[FB] Upload fejlede: {res.status_code} {res.text[:200]}")
        return None
    return f"{sb_url}/storage/v1/object/public/{BUCKET}/fb_{slug}.jpg"


# ── Nøglen ────────────────────────────────────────────────────────────────────

def _fejltekst(res: requests.Response) -> str:
    try:
        e = res.json().get("error", {})
        return f"{e.get('code')}/{e.get('error_subcode')}: {e.get('message')}"
    except ValueError:
        return f"HTTP {res.status_code}"


def token_status(token: str, page_id: str) -> tuple[bool, str]:
    """(kan poste, forklaring) — til morgenbeskeden."""
    if not token or not page_id:
        return False, "META_PAGE_ACCESS_TOKEN eller META_PAGE_ID mangler"
    try:
        res = requests.get(f"{GRAPH_URL}/debug_token",
                           params={"input_token": token, "access_token": token}, timeout=15)
    except requests.RequestException as e:
        return False, f"Facebook svarede ikke ({e.__class__.__name__})"
    if not res.ok:
        return False, _fejltekst(res)
    d = res.json().get("data", {})
    if not d.get("is_valid"):
        return False, f"nøglen er ugyldig ({d.get('error', {}).get('message', 'udløbet')})"
    udloeb = d.get("expires_at") or 0
    if udloeb:
        import time
        dage = (udloeb - time.time()) / 86400
        if dage < 14:
            return True, f"nøglen udløber om {dage:.0f} dage — forny den"
    return True, f"ok ({d.get('type')}, {'udløber aldrig' if not udloeb else 'udløber senere'})"


def _side_noegle(token: str, page_id: str) -> str:
    """Sidens egen nøgle. Er den gemte nøgle en brugernøgle (kendt fælde ved
    fornyelse via facebook_auth.py), hentes sidens nøgle fra /me/accounts."""
    try:
        d = requests.get(f"{GRAPH_URL}/debug_token",
                         params={"input_token": token, "access_token": token}, timeout=15).json()
        if d.get("data", {}).get("type") != "USER":
            return token
        sider = requests.get(f"{GRAPH_URL}/me/accounts",
                             params={"access_token": token}, timeout=15).json().get("data", [])
        side = next((s for s in sider if s.get("id") == page_id), None)
        if side and side.get("access_token"):
            print("[FB] Den gemte nøgle er en brugernøgle — bruger sidens egen nøgle")
            return side["access_token"]
    except (requests.RequestException, ValueError):
        pass
    return token


# ── Facebook photo post ───────────────────────────────────────────────────────

def _fb_post(article_id: str, slug: str, title: str, category: str,
             excerpt: str | None, image_url: str,
             token: str, page_id: str, sb_url: str, sb_key: str) -> bool:
    emoji   = CATEGORY_EMOJI.get(category, "🚴")
    art_url = f"{SITE_URL}/nyheder/{slug}"

    # Opslaget: titel + excerpt + "link i kommentar" — INGEN URL i selve opslaget
    parts = [f"{emoji} {title}"]
    if excerpt:
        parts += ["", excerpt]
    parts += ["", "🔗 Link i kommentar ↓"]

    res = requests.post(
        f"{GRAPH_URL}/{page_id}/photos",
        data={"url": image_url, "caption": "\n".join(parts), "access_token": token},
        timeout=40,
    )
    if not res.ok:
        print(f"[FB] Opslaget blev afvist: {_fejltekst(res)}")
        return False

    post_data = res.json()
    post_id   = post_data.get("post_id") or post_data.get("id")

    h = {
        "apikey": sb_key, "Authorization": f"Bearer {sb_key}",
        "Content-Type": "application/json", "Prefer": "return=minimal",
    }
    requests.patch(
        f"{sb_url}/rest/v1/news_articles?id=eq.{article_id}",
        json={"social_posted": True, "fb_post_id": post_id},
        headers=h, timeout=10,
    )

    # Linket som første kommentar
    if post_id:
        k = requests.post(f"{GRAPH_URL}/{post_id}/comments",
                          data={"message": art_url, "access_token": token}, timeout=20)
        if not k.ok:
            print(f"[FB] Opslaget er postet, men link-kommentaren fejlede: {_fejltekst(k)}")
    return True


def _allerede_postet(article_id: str, sb_url: str, sb_key: str) -> bool:
    h = {"apikey": sb_key, "Authorization": f"Bearer {sb_key}"}
    try:
        rows = requests.get(f"{sb_url}/rest/v1/news_articles?id=eq.{article_id}&select=fb_post_id",
                            headers=h, timeout=10).json()
        return bool(rows and rows[0].get("fb_post_id"))
    except (requests.RequestException, ValueError):
        return False


# ── Indgang ───────────────────────────────────────────────────────────────────

def generate_and_post(
    article_id: str,
    slug: str,
    title: str,
    category: str,
    excerpt: str | None,
    sb_url: str,
    sb_key: str,
    meta_token: str,
    page_id: str,
) -> bool:
    """Genererer billedet og poster artiklen. Returnerer True, når opslaget
    er på siden. Poster aldrig samme artikel to gange."""
    if not meta_token or not page_id:
        print("[FB] META_PAGE_ACCESS_TOKEN/META_PAGE_ID mangler — ikke postet")
        return False
    if not PILLOW_AVAILABLE:
        print(f"[FB] Pillow ikke installeret — kan ikke generere billede til {slug}")
        return False
    if _allerede_postet(article_id, sb_url, sb_key):
        print(f"[FB] {slug} er allerede postet — springes over")
        return True
    try:
        image_url = _upload(generate_fb_image(title, category, excerpt), slug, sb_url, sb_key)
    except Exception as e:
        print(f"[FB] Billedgenerering fejl: {e}")
        return False
    if not image_url:
        return False

    ok = _fb_post(article_id, slug, title, category, excerpt, image_url,
                  _side_noegle(meta_token, page_id), page_id, sb_url, sb_key)
    print(f"[FB] {'✓' if ok else '✗'} {title[:65]}")
    return ok
