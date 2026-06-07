# -*- coding: utf-8 -*-
"""
instagram_pinned.py
Genererer 3 fastgjorte Instagram-opslag (1080x1080) med rigtige screenshots
fra klassementet.dk annoteret med pile og cirkler.

Post 1: Forsiden — Løbskalender + Nyheder
Post 2: Etapeprofil — Højdeprofil-interface
Post 3: Klassement — GC-standings / favoritliste

Kørsel:
  python instagram_pinned.py
  python instagram_pinned.py --preview
"""

import math
import os
import sys
import json
import argparse
import requests as _requests
from io import BytesIO
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:
    sys.exit("Pillow ikke installeret: pip install pillow")

from dotenv import load_dotenv
load_dotenv()

from fb_article_image import BG, BG2, EMERALD, WHITE, GRAY, DARK, _font, _wrap
from instagram_carousel_daily import _add_logo_header

W, H   = 1080, 1080
OUT    = Path(__file__).parent / "assets" / "instagram" / "pinned"
API    = os.getenv("RAILWAY_API_URL", "https://web-production-4e06a.up.railway.app")
SITE   = "https://klassementet.dk"

# Annotation colors
EMERALD_SOLID = EMERALD
ARROW_W = 5
CIRCLE_W = 5


# ── PIL annotation helpers ────────────────────────────────────────────────────

def draw_circle(draw, x, y, w, h, padding=18, color=EMERALD_SOLID, width=CIRCLE_W):
    """Tegner en rundet cirkel/oval rundt om et element."""
    draw.rounded_rectangle(
        [(x - padding, y - padding), (x + w + padding, y + h + padding)],
        radius=18, outline=color, width=width,
    )


def draw_arrow(draw, x1, y1, x2, y2, color=EMERALD_SOLID, width=ARROW_W, head=20):
    """Tegner en pil fra (x1,y1) til (x2,y2)."""
    draw.line([(x1, y1), (x2, y2)], fill=color, width=width)
    angle = math.atan2(y2 - y1, x2 - x1)
    ax1 = x2 - head * math.cos(angle - math.pi / 6)
    ay1 = y2 - head * math.sin(angle - math.pi / 6)
    ax2 = x2 - head * math.cos(angle + math.pi / 6)
    ay2 = y2 - head * math.sin(angle + math.pi / 6)
    draw.polygon([(x2, y2), (int(ax1), int(ay1)), (int(ax2), int(ay2))], fill=color)


def draw_callout(draw, text, cx, cy, font, text_color=WHITE, bg=DARK, border=EMERALD_SOLID):
    """Tegner en callout-boks centreret på (cx, cy)."""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = 14
    rx0, ry0 = cx - tw // 2 - pad, cy - th // 2 - pad
    rx1, ry1 = cx + tw // 2 + pad, cy + th // 2 + pad
    draw.rounded_rectangle([(rx0, ry0), (rx1, ry1)], radius=10,
                            fill=bg, outline=border, width=3)
    draw.text((cx, cy), text, font=font, fill=text_color, anchor="mm")
    return (rx0, ry0, rx1, ry1)


def dark_overlay(img, y0, y1, alpha=210):
    """Lægger et mørkt overlay på billedet fra y0 til y1."""
    overlay = Image.new("RGBA", (W, y1 - y0), (10, 17, 34, alpha))
    img.paste(Image.new("RGB", (W, y1 - y0), BG),
              (0, y0), mask=overlay.split()[3])


def gradient_overlay(img, y0, y1, alpha_top=0, alpha_bottom=220):
    """Gradient overlay fra gennemsigtig til mørk."""
    grad = Image.new("RGBA", (W, y1 - y0), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(y1 - y0):
        t = y / (y1 - y0)
        a = int(alpha_top + (alpha_bottom - alpha_top) * t)
        gd.line([(0, y), (W, y)], fill=(10, 17, 34, a))
    img.paste(Image.new("RGB", (W, y1 - y0), BG), (0, y0), mask=grad.split()[3])


# ── Playwright screenshot + scale ─────────────────────────────────────────────

SCALE = W / 1280  # screenshot er 1280px bred → skaler til 1080

def take_screenshot(url, scroll_y=0, viewport_h=900, wait_ms=2500) -> Image.Image | None:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = p.chromium.launch().new_page(viewport={"width": 1280, "height": viewport_h})
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": viewport_h})
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(wait_ms)
            if scroll_y:
                page.evaluate(f"window.scrollTo(0, {scroll_y})")
                page.wait_for_timeout(600)
            sc = page.screenshot(type="png")
            browser.close()
        img = Image.open(BytesIO(sc)).convert("RGB")
        # Skaler til 1080 bred
        new_h = int(img.height * SCALE)
        return img.resize((W, new_h), Image.LANCZOS)
    except Exception as e:
        print(f"  [Screenshot] Fejl: {e}")
        return None


def get_element_bbox(url, selector, scroll_y=0, viewport_h=900, wait_ms=2500):
    """Returnerer (x, y, w, h) i SKALEREDE koordinater (1080px bred)."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": viewport_h})
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(wait_ms)
            if scroll_y:
                page.evaluate(f"window.scrollTo(0, {scroll_y})")
                page.wait_for_timeout(600)
            loc = page.locator(selector).first
            bb = loc.bounding_box(timeout=3000)
            browser.close()
        if bb:
            return (
                int(bb["x"] * SCALE),
                int(bb["y"] * SCALE),
                int(bb["width"] * SCALE),
                int(bb["height"] * SCALE),
            )
    except Exception:
        pass
    return None


def get_multiple_bboxes(url, selector, scroll_y=0, viewport_h=900, wait_ms=2500, max_n=3):
    """Returnerer liste af (x, y, w, h) for de første max_n elementer."""
    results = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": viewport_h})
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(wait_ms)
            if scroll_y:
                page.evaluate(f"window.scrollTo(0, {scroll_y})")
                page.wait_for_timeout(600)
            for i in range(max_n):
                try:
                    bb = page.locator(selector).nth(i).bounding_box(timeout=2000)
                    if bb:
                        results.append((
                            int(bb["x"] * SCALE),
                            int(bb["y"] * SCALE),
                            int(bb["width"] * SCALE),
                            int(bb["height"] * SCALE),
                        ))
                except Exception:
                    break
            browser.close()
    except Exception as e:
        print(f"  [BBox] Fejl: {e}")
    return results


def fetch_race_slugs():
    """Hent løb-slugs fra API (ongoing + upcoming)."""
    slugs = []
    for endpoint in ["ongoing-races", "upcoming-races"]:
        try:
            r = _requests.get(f"{API}/{endpoint}", timeout=8)
            if r.ok:
                for race in r.json():
                    if race.get("slug"):
                        slugs.append(race["slug"])
        except Exception:
            pass
    return slugs


# ── Compose helpers ────────────────────────────────────────────────────────────

def compose_screenshot_post(sc_img: Image.Image | None, crop_y: int, crop_h: int,
                             title: str, subtitle: str) -> tuple["Image.Image", "ImageDraw.ImageDraw"]:
    """
    Sammensætter base-canvas med screenshot:
      - 0..88: mørk header (logo)
      - 88..88+crop_h: screenshot crop
      - 88+crop_h..H: mørk footer (titel + undertitel)
    Returnerer (img, draw) klar til annotation.
    """
    canvas = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(canvas)

    if sc_img:
        # Crop den del af skærmbilledet vi vil vise
        cropped = sc_img.crop((0, crop_y, W, crop_y + crop_h))
        canvas.paste(cropped, (0, 88))
        # Gradient øverst og nederst
        gradient_overlay(canvas, 88, 88 + min(60, crop_h), alpha_top=180, alpha_bottom=0)
        gradient_overlay(canvas, 88 + crop_h - 80, 88 + crop_h, alpha_top=0, alpha_bottom=220)
    else:
        # Fallback: mørk firkant med tekst
        draw.rectangle([(0, 88), (W, 88 + crop_h)], fill=(14, 21, 40))
        draw.text((W // 2, 88 + crop_h // 2), "klassementet.dk",
                  font=_font(40, bebas=True), fill=EMERALD, anchor="mm")

    # Header
    dark_overlay(canvas, 0, 92, alpha=230)
    draw.rectangle([(0, 0), (W, 6)], fill=EMERALD)
    draw = ImageDraw.Draw(canvas)
    _add_logo_header(draw, canvas)

    # Footer
    footer_y = 88 + crop_h
    footer_h = H - footer_y
    dark_overlay(canvas, footer_y, H, alpha=240)
    draw.rectangle([(0, footer_y), (W, footer_y + 3)], fill=EMERALD)
    draw.rectangle([(0, H - 6), (W, H)], fill=EMERALD)
    draw = ImageDraw.Draw(canvas)

    title_f = _font(46, bebas=True)
    sub_f   = _font(22)
    # Centrer i footer-arealet
    ty = footer_y + footer_h // 2 - 28
    draw.text((W // 2, ty),      title,    font=title_f, fill=WHITE,   anchor="mm")
    draw.text((W // 2, ty + 52), subtitle, font=sub_f,   fill=EMERALD, anchor="mm")

    return canvas, draw


# ── Post 1: Forsiden — Løbskalender + Nyheder ─────────────────────────────────

def post_01_homepage() -> Image.Image:
    print("  Post 1: Screenshot af forsiden...")
    url = SITE

    # Tag screenshot + find elementer i ét Playwright-kald
    sc_img = None
    race_bb = None
    news_bb = None

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2800)
            sc_bytes = page.screenshot(type="png")

            # Find løb-sektion (første section med race-cards)
            try:
                bb = page.locator("section").first.bounding_box(timeout=2000)
                if bb:
                    race_bb = (int(bb["x"]*SCALE), int(bb["y"]*SCALE),
                               int(bb["width"]*SCALE), int(bb["height"]*SCALE))
            except Exception:
                pass

            # Find nyhedssektionen (links til nyheder)
            try:
                # Nyheder-sektion er typisk den anden store section
                sections = page.locator("section").all()
                for sec in sections[1:]:
                    bb = sec.bounding_box(timeout=1000)
                    if bb and bb["y"] > 300 and bb["height"] > 100:
                        news_bb = (int(bb["x"]*SCALE), int(bb["y"]*SCALE),
                                   int(bb["width"]*SCALE), int(bb["height"]*SCALE))
                        break
            except Exception:
                pass

            browser.close()

        sc_img = Image.open(BytesIO(sc_bytes)).convert("RGB")
        new_h = int(sc_img.height * SCALE)
        sc_img = sc_img.resize((W, new_h), Image.LANCZOS)
        print(f"    Screenshot: {W}x{new_h}px")
    except Exception as e:
        print(f"    Playwright fejl: {e}")

    # Layout: crop ca. 700px fra top af siden
    crop_y = 60
    crop_h = 820
    canvas, draw = compose_screenshot_post(
        sc_img, crop_y, crop_h,
        "LØBSKALENDER & NYHEDER",
        "Alt hvad der sker i cykelverdenen — klassementet.dk",
    )

    if sc_img:
        cf = _font(22, bebas=True)
        # Annoteringer koordinater er relativt til cropppen
        # (screen_y - crop_y + 88) → canvas_y

        def sc_to_canvas(sx, sy):
            return sx, sy - crop_y + 88

        # Cirkel rundt om løbskalender-sektionen
        if race_bb:
            rx, ry, rw, rh = race_bb
            cy_canvas = ry - crop_y + 88
            if 88 < cy_canvas < 88 + crop_h - 60:
                draw_circle(draw, rx, cy_canvas, min(rw, W - 20), min(rh, 200),
                            padding=12, width=4)
                callout_x = rx + min(rw, W - 20) // 2
                callout_y = max(cy_canvas - 38, 110)
                draw_callout(draw, "KOMMENDE LOB", callout_x, callout_y, cf)
                draw_arrow(draw, callout_x, callout_y + 22,
                           callout_x, cy_canvas - 14, head=14)
        else:
            # Fallback: annotter øverste halvdel
            draw_circle(draw, 30, 108, W - 60, 220, padding=8, width=4)
            draw_callout(draw, "KOMMENDE LOB", W // 2, 98, cf)

        # Cirkel rundt om nyheds-sektionen
        if news_bb:
            nx, ny, nw, nh = news_bb
            cy_canvas = ny - crop_y + 88
            if 88 < cy_canvas < 88 + crop_h - 60:
                draw_circle(draw, nx, cy_canvas, min(nw, W - 20), min(nh, 280),
                            padding=12, width=4)
                callout_x = nx + min(nw, W - 20) // 2
                callout_y = max(cy_canvas - 42, 150)
                draw_callout(draw, "SENESTE NYHEDER", callout_x, callout_y, cf)
                draw_arrow(draw, callout_x, callout_y + 22,
                           callout_x, cy_canvas - 14, head=14)
        else:
            # Fallback
            draw_circle(draw, 30, 88 + crop_h // 2, W - 60, 240, padding=8, width=4)
            draw_callout(draw, "SENESTE NYHEDER", W // 2, 88 + crop_h // 2 - 12, cf)

    return canvas


# ── Post 2: Etapeprofil ────────────────────────────────────────────────────────

def post_02_stage_profile() -> Image.Image:
    print("  Post 2: Screenshot af etapeprofil...")

    # Find et løb med etaper
    slugs = fetch_race_slugs()
    stage_url = None
    for slug in slugs:
        try:
            r = _requests.get(f"{API}/races/{slug}/stages", timeout=8)
            if r.ok:
                stages = r.json()
                for s in stages:
                    if s.get("elevation_image_url") or s.get("stage_type") in ("mountain", "hilly"):
                        n = s.get("stage_number", 1)
                        stage_url = f"{SITE}/{slug}/stage/{n}"
                        print(f"    Bruger: {stage_url}")
                        break
            if stage_url:
                break
        except Exception:
            pass

    if not stage_url and slugs:
        stage_url = f"{SITE}/{slugs[0]}/stage/1"
        print(f"    Fallback URL: {stage_url}")

    sc_img = None
    profile_bb = None
    climb_bb = None

    if stage_url:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.goto(stage_url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(3000)
                sc_bytes = page.screenshot(type="png", full_page=True)

                # Find højdeprofil-billede
                try:
                    # Elevation image er typisk et img-tag med elevation i src
                    selectors = [
                        "img[src*='elevation']",
                        "img[src*='profile']",
                        "img[alt*='profil']",
                        "img[alt*='etape']",
                        ".elevation-profile img",
                        "section img",
                    ]
                    for sel in selectors:
                        bb = page.locator(sel).first.bounding_box(timeout=1500)
                        if bb and bb["height"] > 60:
                            profile_bb = (int(bb["x"]*SCALE), int(bb["y"]*SCALE),
                                         int(bb["width"]*SCALE), int(bb["height"]*SCALE))
                            break
                except Exception:
                    pass

                # Find klatreprofil (ClimbProfile)
                try:
                    bb = page.locator("canvas, svg").first.bounding_box(timeout=1500)
                    if bb and bb["height"] > 40:
                        climb_bb = (int(bb["x"]*SCALE), int(bb["y"]*SCALE),
                                    int(bb["width"]*SCALE), int(bb["height"]*SCALE))
                except Exception:
                    pass

                browser.close()

            sc_img = Image.open(BytesIO(sc_bytes)).convert("RGB")
            new_h = int(sc_img.height * SCALE)
            sc_img = sc_img.resize((W, new_h), Image.LANCZOS)
            print(f"    Screenshot: {W}x{new_h}px")
        except Exception as e:
            print(f"    Playwright fejl: {e}")

    # Find den del af siden med profilet — scroll ned til det er synligt
    # Crop til at vise etape-info + profil
    crop_y = 80
    crop_h = 820

    # Hvis profile_bb er langt nede, juster crop
    if profile_bb and profile_bb[1] > 400:
        center = profile_bb[1] + profile_bb[3] // 2
        crop_y = max(60, center - 420)

    canvas, draw = compose_screenshot_post(
        sc_img, crop_y, crop_h,
        "ETAPEPROFIL & HØJDEKORT",
        "Rute, højdemeter og klatreprofiler for hver etape",
    )

    if sc_img:
        cf = _font(22, bebas=True)

        if profile_bb:
            px, py, pw, ph = profile_bb
            cy_canvas = py - crop_y + 88
            if 88 < cy_canvas < 88 + crop_h - 40:
                draw_circle(draw, px, cy_canvas, pw, ph, padding=14, width=5)
                # Pil fra højre side af cirklen med callout
                callout_x = min(px + pw + 140, W - 90)
                callout_y = cy_canvas + ph // 2
                cx_bbox = draw_callout(draw, "HOEJDEPROFIL", callout_x, callout_y, cf)
                # Pil fra callout-kassen venstre kant til cirklens højre kant
                arrow_start_x = cx_bbox[0] - 4
                draw_arrow(draw, arrow_start_x, callout_y,
                           px + pw + 14, cy_canvas + ph // 2, head=14)

        if climb_bb and climb_bb != profile_bb:
            cx2, cy2, cw2, ch2 = climb_bb
            cy_canvas2 = cy2 - crop_y + 88
            if 88 < cy_canvas2 < 88 + crop_h - 40:
                draw_circle(draw, cx2, cy_canvas2, cw2, ch2, padding=12, width=4)
                callout_x2 = cx2 + cw2 // 2
                callout_y2 = cy_canvas2 - 44
                if callout_y2 > 100:
                    draw_callout(draw, "KLATREPROFIL", callout_x2, callout_y2, cf)
                    draw_arrow(draw, callout_x2, callout_y2 + 24,
                               callout_x2, cy_canvas2 - 14, head=14)

        # Fallback annotation hvis ingen elementer fundet
        if not profile_bb and not climb_bb:
            mid_y = 88 + crop_h // 2
            draw_circle(draw, 40, mid_y - 80, W - 80, 160, padding=10, width=4)
            draw_callout(draw, "HOEJDEPROFIL", W // 2, mid_y - 90, cf)

    return canvas


# ── Post 3: Klassement / Favoritter ───────────────────────────────────────────

def post_03_standings() -> Image.Image:
    print("  Post 3: Screenshot af klassement...")

    # Find et løb med GC-data
    slugs = fetch_race_slugs()
    race_url = None
    for slug in slugs:
        try:
            r = _requests.get(f"{API}/races/{slug}/standings/gc", timeout=8)
            if r.ok and len(r.json()) > 0:
                race_url = f"{SITE}/{slug}"
                print(f"    Bruger: {race_url}")
                break
        except Exception:
            pass

    if not race_url and slugs:
        race_url = f"{SITE}/{slugs[0]}"
        print(f"    Fallback URL: {race_url}")
    elif not race_url:
        race_url = SITE
        print(f"    Fallback URL: {race_url}")

    sc_img = None
    standings_bb = None
    jersey_bb = None

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(race_url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)

            # Find klassement-sektionen (RaceFavorites er section.rounded-2xl)
            try:
                sel = "section.rounded-2xl, section.mb-8.rounded-2xl"
                bb = page.locator(sel).first.bounding_box(timeout=2000)
                if bb:
                    standings_bb = (int(bb["x"]*SCALE), int(bb["y"]*SCALE),
                                   int(bb["width"]*SCALE), int(bb["height"]*SCALE))
            except Exception:
                pass

            # Find jersey-tab baren
            try:
                bb = page.locator("div.flex.border-b").first.bounding_box(timeout=1500)
                if bb:
                    jersey_bb = (int(bb["x"]*SCALE), int(bb["y"]*SCALE),
                                 int(bb["width"]*SCALE), int(bb["height"]*SCALE))
            except Exception:
                pass

            sc_bytes = page.screenshot(type="png", full_page=True)
            browser.close()

        sc_img = Image.open(BytesIO(sc_bytes)).convert("RGB")
        new_h = int(sc_img.height * SCALE)
        sc_img = sc_img.resize((W, new_h), Image.LANCZOS)
        print(f"    Screenshot: {W}x{new_h}px")
    except Exception as e:
        print(f"    Playwright fejl: {e}")

    # Juster crop til at vise klassement-komponenten
    crop_y = 80
    crop_h = 820
    if standings_bb and standings_bb[1] > 200:
        center = standings_bb[1] + standings_bb[3] // 2
        crop_y = max(60, center - 380)

    canvas, draw = compose_screenshot_post(
        sc_img, crop_y, crop_h,
        "KLASSEMENT & FAVORITTER",
        "Følg GC, point og bjergklassementet live",
    )

    if sc_img:
        cf = _font(22, bebas=True)

        if standings_bb:
            sx, sy, sw, sh = standings_bb
            cy_canvas = sy - crop_y + 88
            if 88 < cy_canvas < 88 + crop_h - 40:
                # Stor cirkel rundt om hele klassement-boksen
                draw_circle(draw, sx, cy_canvas, sw, min(sh, 400),
                            padding=16, width=5)
                callout_x = sx + sw // 2
                callout_y = cy_canvas - 46
                if callout_y > 100:
                    draw_callout(draw, "LIVE KLASSEMENT", callout_x, callout_y, cf)
                    draw_arrow(draw, callout_x, callout_y + 24,
                               callout_x, cy_canvas - 18, head=14)

        if jersey_bb:
            jx, jy, jw, jh = jersey_bb
            cy_canvas_j = jy - crop_y + 88
            if 88 < cy_canvas_j < 88 + crop_h - 40:
                # Cirkel rundt om jersey-tabs
                draw_circle(draw, jx, cy_canvas_j, jw, jh, padding=8, width=4)
                # Callout til højre
                callout_x2 = min(jx + jw + 140, W - 100)
                callout_y2 = cy_canvas_j + jh // 2
                cx_bbox = draw_callout(draw, "GC · POINT · BJERGE · UNGDOM",
                                       callout_x2, callout_y2, cf)
                draw_arrow(draw, cx_bbox[0] - 4, callout_y2,
                           jx + jw + 14, cy_canvas_j + jh // 2, head=14)

        if not standings_bb:
            mid_y = 88 + crop_h // 2
            draw_circle(draw, 40, mid_y - 100, W - 80, 200, padding=10, width=4)
            draw_callout(draw, "LIVE KLASSEMENT", W // 2, mid_y - 110, cf)

    return canvas


# ── Gem ────────────────────────────────────────────────────────────────────────

def save_all(preview: bool = False) -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    posts = [
        ("post_01_kalender.jpg",   post_01_homepage,  "Forsiden — Løbskalender + Nyheder"),
        ("post_02_etapeprofil.jpg", post_02_stage_profile, "Etapeprofil"),
        ("post_03_klassement.jpg", post_03_standings,  "Klassement / Favoritter"),
    ]

    for filename, generator, label in posts:
        print(f"\n[{label}]")
        img = generator()
        path = OUT / filename
        img.save(path, format="JPEG", quality=92, optimize=True)
        print(f"  Gemt: {path}")
        if preview:
            img.show()

    print(f"\nFaerdig. Upload til Instagram og fastnaal:")
    print(f"  {OUT}")
    print("\nUpload-raekkefolge (aeldste vises oeverst → upload 03 foerst):")
    print("  1. post_03_klassement.jpg  — upload foerst")
    print("  2. post_02_etapeprofil.jpg")
    print("  3. post_01_kalender.jpg    — fastnaal oeverst")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true", help="Vis billeder efter generering")
    args = parser.parse_args()
    save_all(args.preview)
