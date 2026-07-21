"""
stage_profile_generator.py
Genererer klassementet.dk's egen FULDE etape-hoejdeprofil direkte fra raa
GPX-hoejdedata i sitets eget design (LEG-001: PCS-profilbilleder maa ikke
bruges — dette er den lovlige erstatning).

Design (matcher frontendens stage-side):
  - baggrund slate-950 (#020617), smelter sammen med ClimbProfile-kortet
  - terraensilhuet med emerald (#10b981) topkant + emerald->transparent fyld
  - kategoriserede stigninger (stage_climbs.category) som badges (HC/1/2/3/4)
    med navn og laengde/gradient/topphoejde; toppen snappes til lokalt
    GPX-hoejdemaksimum saa markoeren sidder praecist trods GPX-skalaafvigelse
  - mellemsprint (stages.sprints) som emerald SPRINT-markoer
  - km-akse i officielle km, hoejdelinjer, START/MAAL med hoejde

Genbruger byggeklodserne fra climb_profile_generator.py (GPX-kilde,
resampling, interpolation). GPX'ens kumulative distance matcher sjaeldent den
officielle etapedistance (~4-5% afvigelse) — terraenet tegnes i GPX-km, mens
akse-labels og markoerer regnes om via km_scale.

Skriver KUN til stages.elevation_image_url/-source naar der ikke allerede
findes et egengenereret billede, medmindre --overwrite angives. Gamle
PCS-URL'er (elevation_image_source IS NULL) blokerer ikke generering.

Koer (test — lokal PNG + upload til test/-sti, ingen DB-skrivning):
    python agents/stage_profile_generator.py --race tour-de-france-2026 --stage 20

Koer (produktion — skriver stages.elevation_image_url + elevation_image_source):
    python agents/stage_profile_generator.py --race tour-de-france-2026 --stage 20 --write-db
"""

import os
import io
import sys
import argparse
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image, ImageChops, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from climb_profile_generator import (  # noqa: E402
    download_stage_gpx,
    cumulative_distances_km,
    resample_elevation_profile,
    _interp_at,
)
# Bemaerk: climb_profile_generator.py wrapper allerede sys.stdout til UTF-8 ved
# import — wrapper det ikke igen her (dobbelt-wrapping lukker strommen).
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SB_AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
SB_HEADERS = {**SB_AUTH, "Content-Type": "application/json", "Prefer": "return=minimal"}
BUCKET = "stage-profiles"

REPO_ROOT = Path(__file__).resolve().parent.parent


# ── Design-konstanter (spejler frontendens Tailwind-farver) ──────────────────

# PIL tegner uden antialiasing — der renderes derfor i SS x oploesning og
# nedskaleres med Lanczos til OUT-stoerrelsen for glatte kanter.
SS = 2
OUT_WIDTH, OUT_HEIGHT = 3000, 1000
WIDTH, HEIGHT = OUT_WIDTH * SS, OUT_HEIGHT * SS
BG_COLOR = (2, 6, 23)            # slate-950 #020617 (sidens baggrund)
EMERALD = (16, 185, 129)         # emerald-500 #10b981 (brandfarve)
WHITE = (248, 250, 252)          # slate-50
SLATE_300 = (203, 213, 225)
SLATE_400 = (148, 163, 184)
SLATE_500 = (100, 116, 139)
SLATE_600 = (71, 85, 105)
SLATE_800 = (30, 41, 59)

# Kategori-badges — samme farvefamilie som frontendens gradientColor()-skala
CAT_COLORS = {
    "HC": (239, 68, 68),    # red-500
    "1": (249, 115, 22),    # orange-500
    "2": (234, 179, 8),     # yellow-500
    "3": (132, 204, 22),    # lime-500
    "4": (16, 185, 129),    # emerald-500
}
CAT_DARK_TEXT = {"2", "3"}  # gul/lime kraever moerk tekst for kontrast

PAD_LEFT, PAD_RIGHT, PAD_TOP, PAD_BOTTOM = 120 * SS, 70 * SS, 400 * SS, 110 * SS

# Label-baner over terraenet (tre raekker; labels glider vandret ved kollision).
# Baneafstanden (88) er stoerre end et majort labels samlede hoejde (badge-top
# til sub-bund ~83), saa baner aldrig overlapper hinanden lodret.
LANE_Y = {0: 150 * SS, 1: 238 * SS, 2: 326 * SS}
LANE_SUB_OFFSET = 38 * SS
LANE_GAP_PX = 24 * SS

_FONT_CANDIDATES_DISPLAY = [
    str(REPO_ROOT / "assets" / "fonts" / "BebasNeue-Regular.ttf"),
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def _font(size: int, display: bool = False):
    """Fontstoerrelser angives i OUT-pixels; skaleres automatisk med SS."""
    for p in (_FONT_CANDIDATES_DISPLAY if display else _FONT_CANDIDATES):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size * SS)
            except Exception:
                continue
    return ImageFont.load_default()


def fmt_da(x: float, dec: int = 1) -> str:
    """Dansk talformat: komma-decimal, punktum-tusinder."""
    s = f"{x:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_int_da(x: float) -> str:
    return f"{int(round(x)):,}".replace(",", ".")


# ── Geometri-hjaelpere ───────────────────────────────────────────────────────

def snap_to_local_max(
    resampled: list[tuple[float, float]], target_km: float, window_km: float = 3.0
) -> tuple[float, float]:
    """Finder (km, elev) for det hoejeste punkt inden for ±window_km af target.
    Bruges til at saette top-markoerer praecist trods km_scale-afvigelse."""
    window = [(km, e) for km, e in resampled if abs(km - target_km) <= window_km]
    if not window:
        return target_km, _interp_at(resampled, target_km)
    return max(window, key=lambda p: p[1])


def _dashed_vline(draw: ImageDraw.ImageDraw, x: float, y0: float, y1: float,
                  fill, width: int = 2 * SS, dash: int = 12 * SS, gap: int = 9 * SS) -> None:
    y = min(y0, y1)
    y_end = max(y0, y1)
    while y < y_end:
        draw.line([(x, y), (x, min(y + dash, y_end))], fill=fill, width=width)
        y += dash + gap


# ── Rendering ─────────────────────────────────────────────────────────────────

def render_stage_profile(
    stage_meta: dict,
    resampled: list[tuple[float, float]],
    climbs: list[dict],
    sprints: list[dict],
    km_scale: float,
) -> Image.Image:
    """
    stage_meta: {stage_number, start_location, finish_location, distance_km,
                 elevation_gain_m}
    resampled:  [(gpx_km, elev_m)] for hele etapen (jaevnt fordelt)
    climbs:     kun kategoriserede: {name, category, length_km, avg_gradient,
                summit_km_official}
    sprints:    [{"km": officiel_km, "name": str}]
    """
    img = Image.new("RGBA", (WIDTH, HEIGHT), (*BG_COLOR, 255))
    draw = ImageDraw.Draw(img)

    inner_w = WIDTH - PAD_LEFT - PAD_RIGHT
    inner_h = HEIGHT - PAD_TOP - PAD_BOTTOM
    baseline_y = HEIGHT - PAD_BOTTOM

    elevs = [e for _, e in resampled]
    min_elev, max_elev = min(elevs), max(elevs)
    elev_range = max(max_elev - min_elev, 1.0)
    min_elev_padded = max(0.0, min_elev - elev_range * 0.05)
    max_elev_padded = max_elev + elev_range * 0.10
    total_km = resampled[-1][0]

    def to_x(gpx_km: float) -> float:
        return PAD_LEFT + (gpx_km / total_km) * inner_w

    def to_y(elev: float) -> float:
        return PAD_TOP + inner_h - ((elev - min_elev_padded) / (max_elev_padded - min_elev_padded)) * inner_h

    # 1) Hoejde-gitterlinjer + labels (bag terraenet) — adaptivt trin, saa
    #    ogsaa flade etaper (range < 250 m) faar hoejdelinjer
    step_elev = next(s for s in (50, 100, 250, 500, 1000, 2000) if elev_range / s <= 5)
    level = (int(min_elev_padded) // step_elev + 1) * step_elev
    while level < max_elev_padded:
        y = to_y(level)
        draw.line([(PAD_LEFT, y), (WIDTH - PAD_RIGHT, y)], fill=SLATE_800, width=SS)
        draw.text((PAD_LEFT - 14 * SS, y), f"{fmt_int_da(level)} m", font=_font(24),
                  fill=SLATE_500, anchor="rm")
        level += step_elev

    # 2) Terraen: emerald->transparent gradientfyld masket af silhuetten
    surface_pts = [(to_x(km), to_y(e)) for km, e in resampled]
    terrain_poly = [(surface_pts[0][0], baseline_y)] + surface_pts + [(surface_pts[-1][0], baseline_y)]

    mask = Image.new("L", (WIDTH, HEIGHT), 0)
    ImageDraw.Draw(mask).polygon(terrain_poly, fill=255)

    grad_col = Image.new("L", (1, HEIGHT), 0)
    top_alpha, bottom_alpha = 130, 16
    col = []
    for y in range(HEIGHT):
        if y < PAD_TOP:
            col.append(top_alpha)
        else:
            frac = (y - PAD_TOP) / max(inner_h, 1)
            col.append(int(top_alpha + (bottom_alpha - top_alpha) * frac))
    grad_col.putdata(col)
    grad = grad_col.resize((WIDTH, HEIGHT))

    fill_layer = Image.merge("RGBA", (
        Image.new("L", (WIDTH, HEIGHT), EMERALD[0]),
        Image.new("L", (WIDTH, HEIGHT), EMERALD[1]),
        Image.new("L", (WIDTH, HEIGHT), EMERALD[2]),
        ImageChops.multiply(grad, mask),
    ))
    img = Image.alpha_composite(img, fill_layer)

    # 3) Emerald topkant med bloed glow (ejer-kravet)
    stroke_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    stroke_draw = ImageDraw.Draw(stroke_layer)
    stroke_draw.line(surface_pts, fill=(*EMERALD, 45), width=24 * SS, joint="curve")
    stroke_draw.line(surface_pts, fill=(*EMERALD, 255), width=8 * SS, joint="curve")
    img = Image.alpha_composite(img, stroke_layer)
    draw = ImageDraw.Draw(img)

    # 4) Baseline + km-akse (officielle km)
    distance_official = float(stage_meta["distance_km"])
    draw.line([(PAD_LEFT, baseline_y), (WIDTH - PAD_RIGHT, baseline_y)], fill=SLATE_600, width=2 * SS)
    step_km = next(s for s in (10, 20, 25, 50, 100) if distance_official / s <= 14)
    k = 0
    while k <= distance_official + 0.5:
        gpx_km = min(k * km_scale, total_km)
        x = to_x(gpx_km)
        draw.line([(x, baseline_y), (x, baseline_y + 10 * SS)], fill=SLATE_600, width=2 * SS)
        draw.text((x, baseline_y + 20 * SS), str(k), font=_font(24), fill=SLATE_500, anchor="ma")
        k += step_km
    draw.text((WIDTH - PAD_RIGHT, baseline_y + 20 * SS), "km", font=_font(24),
              fill=SLATE_500, anchor="la")

    # 5) Markoerer: ALLE stigninger + mellemsprint. Kategoriserede stigninger og
    #    sprint faar fremhaevet badge-stil; ukategoriserede (del-stigninger) faar
    #    en diskret, mindre navnemarkoer, saa navnene matcher stigningsfanerne.
    #    En maalstigning uden kategori vises ved MAAL-flaget i stedet (se pkt. 6).
    finish_climb = None
    markers = []
    for c in climbs:
        near_finish = c["summit_km_official"] >= distance_official - 2.5
        if not c["category"] and near_finish:
            finish_climb = c
            continue
        if c["category"]:
            summit = snap_to_local_max(resampled, c["summit_km_official"] * km_scale)
        else:
            # Del-stigninger topper ofte paa en fortsat opkoersel — lokalmaks-snap
            # ville skubbe markoeren videre op ad bjerget; brug ren interpolation.
            gpx_km = min(c["summit_km_official"] * km_scale, total_km)
            summit = (gpx_km, _interp_at(resampled, gpx_km))
        major = bool(c["category"])
        markers.append({
            "x": to_x(summit[0]),
            "terrain_y": to_y(summit[1]),
            "major": major,
            "badge": c["category"],
            "badge_color": CAT_COLORS.get(c["category"], SLATE_600),
            "name": c["name"].upper(),
            # Ukategoriserede er mellempunkter paa en opkoersel — topphoejden er
            # mindre meningsfuld, saa de faar kun laengde/gradient (kompakt).
            "sub": (f"{fmt_da(c['length_km'])} km · {fmt_da(c['avg_gradient'])}% · {fmt_int_da(summit[1])} m"
                    if major else f"{fmt_da(c['length_km'])} km · {fmt_da(c['avg_gradient'])}%"),
        })
    for s in sprints:
        gpx_km = float(s["km"]) * km_scale
        markers.append({
            "x": to_x(gpx_km),
            "terrain_y": to_y(_interp_at(resampled, gpx_km)),
            "major": True,
            "badge": "SPRINT",
            "badge_color": EMERALD,
            "name": str(s.get("name", "")).upper(),
            "sub": f"km {fmt_da(float(s['km']))}",
        })
    markers.sort(key=lambda m: m["x"])

    badge_font = _font(30, display=True)
    name_font_major = _font(38, display=True)
    name_font_minor = _font(27, display=True)
    sub_font_major = _font(24)
    sub_font_minor = _font(20)

    # Baneplacering: greedy med vandret glidning — hver bane husker sin hoejre
    # kant, og et label skubbes hoejrepaa (vaek fra sin markoerlinje) frem for at
    # overlappe naboen. Bane 0 starter efter headerens underlinje, som ligger i
    # samme hoejde i venstre hjoerne.
    header_sub = "  ·  ".join(
        [f"{fmt_da(distance_official)} km"]
        + ([f"{fmt_int_da(stage_meta['elevation_gain_m'])} højdemeter"]
           if stage_meta.get("elevation_gain_m") else [])
    )
    lane_end = {
        0: PAD_LEFT + draw.textlength(header_sub, font=_font(30)) + LANE_GAP_PX,
        1: -1e9,
        2: -1e9,
    }
    for m in markers:
        if m["major"]:
            badge_w = draw.textlength(m["badge"], font=badge_font) + 24 * SS
            top_w = badge_w + 14 * SS + draw.textlength(m["name"], font=name_font_major)
            sub_w = draw.textlength(m["sub"], font=sub_font_major)
            block_w = max(top_w, sub_w)
            name_w = 0.0
        else:
            # Minor: alt paa EN linje ("NAVN  5,8 km · 8,2%") — halv hoejde,
            # mindre visuel stoej og faerre kollisioner.
            badge_w = 0
            name_w = draw.textlength(m["name"], font=name_font_minor)
            sub_w = draw.textlength(m["sub"], font=sub_font_minor)
            block_w = name_w + 12 * SS + sub_w
        m["name_w"] = name_w
        desired_left = min(max(m["x"] - block_w / 2, PAD_LEFT), WIDTH - PAD_RIGHT - block_w)
        best = None
        for lane in (0, 1, 2):
            left = max(desired_left, lane_end[lane] + LANE_GAP_PX)
            disp = left - desired_left
            if best is None or disp < best[2]:
                best = (lane, left, disp)
        lane, left, _ = best
        left = min(left, WIDTH - PAD_RIGHT - block_w)
        lane_end[lane] = left + block_w
        m.update({"lane": lane, "left": left, "badge_w": badge_w, "block_w": block_w})

    # Stiplede linjer foerst, labels ovenpaa med baggrundsfarvet stroke — saa
    # forbliver tekst laesbar, selv hvor en nabolinje krydser et label.
    for m in markers:
        y_line_top = LANE_Y[m["lane"]] + (LANE_SUB_OFFSET + 26 * SS if m["major"] else 20 * SS)
        _dashed_vline(draw, m["x"], y_line_top, m["terrain_y"] - 8 * SS, fill=SLATE_600)
    for m in markers:
        y_badge = LANE_Y[m["lane"]]
        y_sub = y_badge + LANE_SUB_OFFSET
        cx = m["left"] + m["block_w"] / 2
        if m["major"]:
            badge_h = 42 * SS
            dark_badge_text = m["badge"] in CAT_DARK_TEXT
            draw.rounded_rectangle(
                [m["left"], y_badge - badge_h / 2, m["left"] + m["badge_w"], y_badge + badge_h / 2],
                radius=10 * SS, fill=m["badge_color"],
            )
            draw.text((m["left"] + m["badge_w"] / 2, y_badge + 2 * SS), m["badge"], font=badge_font,
                      fill=BG_COLOR if dark_badge_text else WHITE, anchor="mm")
            draw.text((m["left"] + m["badge_w"] + 14 * SS, y_badge + 2 * SS), m["name"],
                      font=name_font_major, fill=WHITE, anchor="lm",
                      stroke_width=3 * SS, stroke_fill=BG_COLOR)
            draw.text((cx, y_sub), m["sub"], font=sub_font_major, fill=SLATE_400, anchor="ma",
                      stroke_width=3 * SS, stroke_fill=BG_COLOR)
        else:
            draw.text((m["left"], y_badge + 2 * SS), m["name"],
                      font=name_font_minor, fill=SLATE_300, anchor="lm",
                      stroke_width=3 * SS, stroke_fill=BG_COLOR)
            draw.text((m["left"] + m["name_w"] + 12 * SS, y_badge + 3 * SS), m["sub"],
                      font=sub_font_minor, fill=SLATE_500, anchor="lm",
                      stroke_width=3 * SS, stroke_fill=BG_COLOR)

    # 6) START / MAAL med hoejde fra GPX
    start_elev = resampled[0][1]
    finish_elev = resampled[-1][1]
    sx, sy = surface_pts[0]
    fx, fy = surface_pts[-1]

    draw.ellipse([sx - 9 * SS, sy - 9 * SS, sx + 9 * SS, sy + 9 * SS],
                 fill=EMERALD, outline=(*BG_COLOR, 255), width=3 * SS)
    draw.text((sx + 16 * SS, sy - 58 * SS), "START", font=_font(34, display=True), fill=WHITE, anchor="la")
    draw.text((sx + 16 * SS, sy - 20 * SS), f"{fmt_int_da(start_elev)} m", font=_font(24),
              fill=SLATE_400, anchor="la")

    # Maalflag: lille ternet flag paa stang
    pole_top = fy - 64 * SS
    draw.line([(fx, fy), (fx, pole_top)], fill=WHITE, width=3 * SS)
    sq = 9 * SS
    for row in range(2):
        for col_i in range(4):
            color = WHITE if (row + col_i) % 2 == 0 else BG_COLOR
            x0 = fx + 3 * SS + col_i * sq
            y0 = pole_top + row * sq
            draw.rectangle([x0, y0, x0 + sq, y0 + sq], fill=color, outline=SLATE_600)
    if finish_climb:
        # Ukategoriseret maalstigning: vis navnet ved MAAL-flaget, saa man ved
        # hvilken stigning etapen slutter paa (matcher stigningsfanen).
        draw.text((fx - 16 * SS, fy - 132 * SS), "MÅL", font=_font(34, display=True),
                  fill=WHITE, anchor="ra")
        draw.text((fx - 16 * SS, fy - 92 * SS), finish_climb["name"].upper(),
                  font=_font(27, display=True), fill=SLATE_300, anchor="ra",
                  stroke_width=3 * SS, stroke_fill=BG_COLOR)
        draw.text((fx - 16 * SS, fy - 56 * SS),
                  f"{fmt_da(finish_climb['length_km'])} km · {fmt_da(finish_climb['avg_gradient'])}%",
                  font=_font(20), fill=SLATE_500, anchor="ra")
        draw.text((fx - 16 * SS, fy - 20 * SS), f"{fmt_int_da(finish_elev)} m", font=_font(24),
                  fill=SLATE_400, anchor="ra")
    else:
        draw.text((fx - 16 * SS, fy - 58 * SS), "MÅL", font=_font(34, display=True), fill=WHITE, anchor="ra")
        draw.text((fx - 16 * SS, fy - 20 * SS), f"{fmt_int_da(finish_elev)} m", font=_font(24),
                  fill=SLATE_400, anchor="ra")

    # 7) Header + branding
    n = stage_meta["stage_number"]
    start_loc = (stage_meta.get("start_location") or "").upper()
    finish_loc = (stage_meta.get("finish_location") or "").upper()
    title = f"ETAPE {n}"
    if start_loc and finish_loc:
        title += f"  |  {start_loc} - {finish_loc}"
    draw.text((PAD_LEFT, 44 * SS), title, font=_font(66, display=True), fill=WHITE, anchor="la")
    draw.text((PAD_LEFT, 122 * SS), header_sub, font=_font(30), fill=SLATE_400, anchor="la")

    draw.text((WIDTH - PAD_RIGHT, HEIGHT - 26 * SS), "KLASSEMENTET.DK",
              font=_font(34, display=True), fill=EMERALD, anchor="rd")

    return img.convert("RGB").resize((OUT_WIDTH, OUT_HEIGHT), Image.LANCZOS)


# ── Supabase ──────────────────────────────────────────────────────────────────

def get_race_id(race_slug: str) -> str | None:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?slug=eq.{race_slug}&select=id&limit=1",
        headers=SB_AUTH,
    )
    data = res.json()
    return data[0]["id"] if res.ok and data else None


def get_stage(race_id: str, stage_number: int) -> dict | None:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages"
        f"?race_id=eq.{race_id}&stage_number=eq.{stage_number}"
        f"&select=id,stage_number,distance_km,elevation_gain_m,elevation_image_url,"
        f"elevation_image_source,sprints,start_location,finish_location&limit=1",
        headers=SB_AUTH,
    )
    data = res.json()
    return data[0] if res.ok and data else None


def get_stage_numbers_for_race(race_id: str) -> list[int]:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages?race_id=eq.{race_id}"
        f"&select=stage_number&order=stage_number.asc",
        headers=SB_AUTH,
    )
    return [s["stage_number"] for s in res.json()] if res.ok else []


def get_climbs_for_stage(stage_id: str) -> list[dict]:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stage_climbs"
        f"?stage_id=eq.{stage_id}"
        f"&select=name,km_from_start,length_km,avg_gradient,category"
        f"&order=km_from_start.asc",
        headers=SB_AUTH,
    )
    return res.json() if res.ok else []


def upload_image(path: str, data: bytes) -> str | None:
    res = requests.post(
        f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{path}",
        data=data,
        headers={**SB_AUTH, "Content-Type": "image/png", "x-upsert": "true"},
    )
    if not res.ok:
        print(f"Upload fejl {res.status_code}: {res.text[:150]}")
        return None
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{path}"


def update_stage_image(stage_id: str, url: str) -> bool:
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/stages?id=eq.{stage_id}",
        json={"elevation_image_url": url, "elevation_image_source": "generated"},
        headers=SB_HEADERS,
    )
    return res.ok


# ── Hovedpipeline ─────────────────────────────────────────────────────────────

def process_stage(race_slug: str, stage_number: int, write_db: bool, overwrite: bool,
                  out_path: str | None = None) -> None:
    race_id = get_race_id(race_slug)
    if not race_id:
        print(f"Løb ikke fundet: {race_slug}")
        return

    stage = get_stage(race_id, stage_number)
    if not stage or not stage.get("distance_km"):
        print(f"Etape {stage_number} ikke fundet eller mangler distance_km")
        return

    # Kun et allerede-egengenereret billede blokerer — gamle PCS-URL'er
    # (elevation_image_source IS NULL) skal kunne erstattes frit.
    if write_db and stage.get("elevation_image_source") == "generated" and not overwrite:
        print(f"Etape {stage_number} har allerede et egengenereret billede — springer over (brug --overwrite)")
        return

    print(f"stage_profile_generator.py — {race_slug} etape {stage_number}")
    print("Henter GPX...")
    points = download_stage_gpx(race_slug, stage_number)
    if not points:
        print("Kunne ikke hente/parse GPX-fil for denne etape — ingen kilde tilgængelig")
        return

    cum_dist = cumulative_distances_km(points)
    gpx_total = cum_dist[-1]
    distance_km_official = float(stage["distance_km"])
    km_scale = gpx_total / distance_km_official
    print(f"GPX: {len(points)} punkter, {gpx_total:.1f} km (officiel distance: {distance_km_official} km, "
          f"skalafaktor {km_scale:.3f})")
    # Vagt mod forkerte/foraeldede GPX-rutevarianter: normal afvigelse er op til
    # ~5% (kurve-udjaevning; relativt stoerre paa korte etaper, derfor 3 km-gulv).
    # Stoerre afvigelse tyder paa en anden rute — publicér ikke (korrekthed foer alt).
    if abs(gpx_total - distance_km_official) > max(0.06 * distance_km_official, 3.0):
        print(f"✗ GPX-distancen afviger {abs(gpx_total - distance_km_official):.1f} km fra officiel "
              f"({distance_km_official} km) — ruten kan ikke verificeres, springer over")
        return

    resampled = resample_elevation_profile(points, n=1200)

    # Alle stigninger med i billedet: kategoriserede som fremhaevede badges,
    # ukategoriserede (del-stigninger m.m.) som diskrete navnemarkoerer, saa
    # navnene matcher stigningsfanerne paa etapesiden.
    climbs = []
    for c in get_climbs_for_stage(stage["id"]):
        if c.get("km_from_start") is None or not c.get("length_km"):
            continue
        climbs.append({
            "name": c["name"],
            "category": c.get("category"),
            "length_km": float(c["length_km"]),
            "avg_gradient": float(c.get("avg_gradient") or 0.0),
            "summit_km_official": float(c["km_from_start"]) + float(c["length_km"]),
        })
    n_cat = sum(1 for c in climbs if c["category"])
    print(f"Stigninger: {len(climbs)} ({n_cat} kategoriserede)")

    sprints = stage.get("sprints") or []
    print(f"Mellemsprints: {len(sprints)}")

    stage_meta = {
        "stage_number": stage["stage_number"],
        "start_location": stage.get("start_location"),
        "finish_location": stage.get("finish_location"),
        "distance_km": distance_km_official,
        "elevation_gain_m": stage.get("elevation_gain_m"),
    }

    img = render_stage_profile(stage_meta, resampled, climbs, sprints, km_scale)
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    local_path = Path(out_path) if out_path else REPO_ROOT / "output" / f"stage-profile-{race_slug}-{stage_number}.png"
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(buf.getvalue())
    print(f"Lokal PNG: {local_path}")

    path = f"stage-full/{stage['id']}.png" if write_db else f"test/stage-{stage['id']}.png"
    url = upload_image(path, buf.getvalue())
    if not url:
        print("Upload fejlede")
        return

    if write_db:
        if update_stage_image(stage["id"], url):
            print(f"✓ Opdateret i DB (source=generated): {url}")
        else:
            print("✗ DB-opdatering fejlede")
    else:
        print(f"✓ Genereret (test, ingen DB-skrivning): {url}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--race", required=True, help="Løb-slug, fx tour-de-france-2026")
    parser.add_argument("--stage", type=int, help="Etapenummer")
    parser.add_argument("--all", action="store_true", help="Alle løbets etaper (pipeline-brug)")
    parser.add_argument("--write-db", action="store_true",
                        help="Upload til stage-full/ og patch stages.elevation_image_url+source (default: kun test/-upload)")
    parser.add_argument("--overwrite", action="store_true",
                        help="Ved --write-db: overskriv etaper der allerede har et egengenereret billede")
    parser.add_argument("--out", help="Lokal sti til PNG (default: output/stage-profile-<race>-<n>.png)")
    args = parser.parse_args()

    if args.all:
        rid = get_race_id(args.race)
        if not rid:
            print(f"Løb ikke fundet: {args.race}")
            sys.exit(1)
        for n in get_stage_numbers_for_race(rid):
            try:
                process_stage(args.race, n, args.write_db, args.overwrite, None)
            except Exception as e:
                print(f"Etape {n}: FEJL {type(e).__name__}: {e}")
    elif args.stage is not None:
        process_stage(args.race, args.stage, args.write_db, args.overwrite, args.out)
    else:
        parser.error("angiv --stage N eller --all")
