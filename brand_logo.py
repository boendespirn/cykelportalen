"""
brand_logo.py
K+cykelist-logo for Klassementet.dk.
K'et tegnes manuelt med Pillow-polygoner, så cyklisten sidder
præcis på K'ets øvre arm (som fungerer som bakkevejen).
"""

import math
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

BG      = (10,  17,  34)
EMERALD = (16, 185, 129)
K_COLOR = (22,  36,  68)
GRAY    = (100, 116, 139)

_FONT_DIR   = Path(__file__).parent / "fonts"
_BEBAS_PATH = _FONT_DIR / "BebasNeue-Regular.ttf"


def _get_small_font(size: int):
    if _BEBAS_PATH.exists():
        try:
            return ImageFont.truetype(str(_BEBAS_PATH), size)
        except Exception:
            pass
    for p in ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/impact.ttf"]:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ── Geometrihjælpere ──────────────────────────────────────────────────────────

def _thick_line_poly(x1, y1, x2, y2, width):
    """Returnerer 4 hjørnepunkter for en tyk linje som polygon."""
    dx, dy = x2 - x1, y2 - y1
    length = math.sqrt(dx*dx + dy*dy)
    if length < 1:
        return []
    px, py = -dy / length, dx / length  # perpendicular unit vector
    hw = width / 2
    return [
        (x1 + px*hw, y1 + py*hw),
        (x1 - px*hw, y1 - py*hw),
        (x2 - px*hw, y2 - py*hw),
        (x2 + px*hw, y2 + py*hw),
    ]


# ── K-tegning ─────────────────────────────────────────────────────────────────

def _draw_k(draw, cx, cy, size, color) -> tuple:
    """
    Tegner et bold, geometrisk K.
    Returnerer (arm_sx, arm_sy, arm_ex, arm_ey) — øvre arms centerlinje.
    """
    sw = size * 0.088    # streg-bredde
    h  = size * 0.56     # K-højde
    kx = cx - size * 0.18   # K's venstre kant

    top    = cy - h / 2
    bottom = cy + h / 2

    # 1. Lodret streg
    draw.rectangle([kx, top, kx + sw, bottom], fill=color)

    # 2. Øvre arm: (kx+sw, cy) → (kx + 0.56*size, top + sw*0.4)
    #    Vinkel ≈ 47° opad mod højre
    arm_sx = kx + sw
    arm_sy = cy
    arm_ex = kx + size * 0.38        # kortere arm (~44° vinkel)
    arm_ey = top                      # slutter ved K'ets top

    pts_upper = _thick_line_poly(arm_sx, arm_sy, arm_ex, arm_ey, sw)
    if pts_upper:
        draw.polygon(pts_upper, fill=color)

    # 3. Nedre arm: spejling af øvre
    pts_lower = _thick_line_poly(arm_sx, arm_sy, arm_ex, bottom, sw)
    if pts_lower:
        draw.polygon(pts_lower, fill=color)

    return arm_sx, arm_sy, arm_ex, arm_ey


# ── Cykelist ──────────────────────────────────────────────────────────────────

def _draw_cyclist(draw, road_x, road_y, scale, angle_deg, color):
    """
    Tændstikkemand på cykel, præcist på vejen.
    road_x, road_y: baghjulets vejkontaktpunkt.
    scale: overordnet størrelse.
    angle_deg: vejens hældning (grader op mod højre).
    """
    ang   = math.radians(angle_deg)
    cos_a = math.cos(ang)
    sin_a = math.sin(ang)

    def tf(x_road, y_above):
        # x_road=langs vejen, y_above=over vejen (positiv=opad fra overfladen)
        return (
             x_road * cos_a - y_above * sin_a + road_x,
            -x_road * sin_a - y_above * cos_a + road_y,
        )

    s  = scale
    rw = s * 0.17             # hjulradius
    wb = s * 0.56             # akselafstand langs vejen
    lw = max(2, int(s * 0.06))

    rear_c  = tf(0,  rw)
    front_c = tf(wb, rw)

    # Hjul
    for wx, wy in [rear_c, front_c]:
        draw.ellipse([wx-rw, wy-rw, wx+rw, wy+rw], outline=color, width=lw)

    # Ramme (3 linjer)
    saddle = tf(wb * 0.14, rw + s * 0.38)
    hbar   = tf(wb * 0.88, rw + s * 0.27)
    draw.line([rear_c, saddle ], fill=color, width=lw)
    draw.line([saddle, hbar   ], fill=color, width=lw)
    draw.line([hbar,   front_c], fill=color, width=lw)

    # Krop (tyk linje = ryg)
    shldr = tf(wb * 0.44, rw + s * 0.58)
    draw.line([saddle, shldr], fill=color, width=max(2, int(s * 0.085)))
    draw.line([shldr,  hbar ], fill=color, width=lw)

    # Hoved
    hr     = s * 0.095
    hx, hy = tf(wb * 0.36, rw + s * 0.74)
    draw.ellipse([hx-hr, hy-hr, hx+hr, hy+hr], fill=color)


# ── Logo ──────────────────────────────────────────────────────────────────────

def make_logo(size: int = 400) -> "Image.Image":
    if not PILLOW_AVAILABLE:
        raise RuntimeError("pip install pillow")

    img  = Image.new("RGB", (size, size), BG)
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2

    # Emerald ring
    ring_r = int(size * 0.456)
    ring_w = max(3, size // 85)
    draw.ellipse([cx-ring_r, cy-ring_r, cx+ring_r, cy+ring_r],
                 outline=EMERALD, width=ring_w)

    # Tegn K — hent armens start/slut
    arm_sx, arm_sy, arm_ex, arm_ey = _draw_k(draw, cx, cy, size, K_COLOR)

    # Beregn armens vinkel og placér cyklisten på armen
    adx = arm_ex - arm_sx
    ady = arm_ey - arm_sy                          # negativt i skærm (opad)
    arm_angle = math.degrees(math.atan2(-ady, adx))  # positiv = opad
    arm_len   = math.sqrt(adx**2 + ady**2)

    # Cyklistens størrelse: ~30% af armens længde
    cyclist_scale = arm_len * 0.30

    # Kontaktpunkt ved t=0.40 langs armen
    t      = 0.40
    road_x = arm_sx + t * adx
    road_y = arm_sy + t * ady

    _draw_cyclist(draw, road_x, road_y, cyclist_scale, arm_angle, EMERALD)

    # KLASSEMENTET.DK tekst i bunden — inde i cirklen med margin
    if size >= 150:
        font = _get_small_font(max(8, int(size * 0.040)))
        draw.text((cx, cy + ring_r - int(size * 0.095)),
                  "KLASSEMENTET.DK", font=font, fill=GRAY, anchor="mm")

    return img


def save_assets() -> None:
    assets_dir = Path(__file__).parent / "assets"
    assets_dir.mkdir(exist_ok=True)
    for sz, name in [(400, "logo_400"), (200, "logo_200"), (80, "logo_80")]:
        path = assets_dir / f"{name}.png"
        make_logo(sz).save(path)
        print(f"Gemt: {path}")


if __name__ == "__main__":
    save_assets()
    make_logo(400).save("logo_preview.png")
    print("Preview: logo_preview.png")
