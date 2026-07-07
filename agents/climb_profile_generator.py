"""
climb_profile_generator.py
Genererer klassementet.dk's egne stigningsprofil-billeder direkte fra raa
GPX-hoejdedata, som fallback naar ClimbFinder ikke har et verificeret match.

Stil: terraensilhuet delt i 20 sektioner, farvet efter haeldning
(hvid 0% -> roed 10% -> moerkeroed ~13% -> sort 15%+), i to varianter
("full" med akser/labels, "minimal" uden).

Kilde til GPX: cyclingstage.com (samme kilde som gpx_agent.py, men parset
med hoejde bevaret og uden downsampling).

Kør (test — genererer begge stilarter, uploader kun til test/-sti, ingen DB-skrivning):
     python agents/climb_profile_generator.py --race tour-de-france-2026 --stage 2

Kør (produktion, én etape — skriver profile_image_url for stigninger uden billede):
     python agents/climb_profile_generator.py --race tour-de-france-2026 --stage 2 \
         --style full --write-db

Kør (produktion, alle etaper i løbet):
     python agents/climb_profile_generator.py --race tour-de-france-2026 --all \
         --style full --write-db
"""

import os
import re
import io
import sys
import math
import bisect
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SB_AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
SB_HEADERS = {**SB_AUTH, "Content-Type": "application/json", "Prefer": "return=minimal"}
BUCKET = "stage-profiles"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

CYCLINGSTAGE_GPX_PAGES: dict[str, str] = {
    "giro-d-italia-2026":         "https://www.cyclingstage.com/giro-2026-gpx",
    "tour-de-france-2026":        "https://www.cyclingstage.com/tour-de-france-2026-gpx",
    "criterium-du-dauphine-2026": "https://www.cyclingstage.com/criterium-du-dauphine-2026-gpx",
    "tour-de-suisse-2026":        "https://www.cyclingstage.com/tour-de-suisse-2026-gpx",
}


# ── GPX henter/parser ──────────────────────────────────────────────────────────

def parse_gpx_with_elevation(xml_content: str) -> list[tuple[float, float, float]]:
    """
    Parser GPX XML og returnerer [(lat, lon, ele_m), ...] i fuld opløsning
    (ingen downsampling — modsat gpx_agent.py, som kun gemmer lat/lon).
    Punkter uden <ele> arver forrige punkts højde (GPS-udfald er sjældne,
    men skal ikke vælte hele parsingen).
    """
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        raise ValueError(f"GPX XML-fejl: {e}")

    points_el = []
    for ns_uri in ("http://www.topografix.com/GPX/1/1", "http://www.topografix.com/GPX/1/0"):
        ns = {"g": ns_uri}
        points_el = root.findall(".//g:trkpt", ns)
        if points_el:
            break

    if not points_el:
        points_el = [el for el in root.iter() if el.tag.endswith("trkpt")]

    if not points_el:
        raise ValueError("Ingen trkpt-punkter fundet i GPX")

    points: list[tuple[float, float, float]] = []
    last_ele = 0.0
    for el in points_el:
        lat = float(el.get("lat"))
        lon = float(el.get("lon"))
        ele_el = next((child for child in el if child.tag.endswith("ele")), None)
        if ele_el is not None and ele_el.text:
            last_ele = float(ele_el.text)
        points.append((lat, lon, last_ele))

    return points


def get_gpx_url_for_stage(race_slug: str, stage_number: int) -> str | None:
    """Finder GPX-download-URL'en for en specifik etape på cyclingstage.com."""
    gpx_page_url = CYCLINGSTAGE_GPX_PAGES.get(race_slug)
    if not gpx_page_url:
        return None
    res = requests.get(gpx_page_url, headers={"User-Agent": UA}, timeout=15)
    if not res.ok:
        return None
    soup = BeautifulSoup(res.text, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # cyclingstage.com bruger flere filnavns-mønstre for GPX-links: "stage-N-route.gpx"
        # (giro), "stage-N.gpx" uden suffix (nogle tour-de-france-etaper, se
        # STG-006/STG-007/STG-002), og siden juli 2026 "stage-N-parcours.gpx" for hele
        # tour-de-france-2026 (bekræftet: cyclingstage.com skiftede navnekonvention —
        # uden "-parcours" i regex fik get_gpx_url_for_stage() til at returnere None for
        # ALLE TdF 2026-etaper, hvilket sprang veloviewer_agent.py's GPX-udtræk helt over,
        # se STG-019).
        m = re.fullmatch(r".*stage-(\d+)(?:-route|-parcours)?\.gpx", href)
        if not m:
            continue
        if int(m.group(1)) == stage_number:
            return href if href.startswith("http") else "https://cdn.cyclingstage.com" + href
    return None


def download_stage_gpx(race_slug: str, stage_number: int) -> list[tuple[float, float, float]] | None:
    """Henter og parser den rå GPX-fil for en etape. None hvis ikke fundet/fejl."""
    gpx_url = get_gpx_url_for_stage(race_slug, stage_number)
    if not gpx_url:
        return None
    res = requests.get(gpx_url, headers={"User-Agent": UA}, timeout=20)
    if not res.ok:
        return None
    try:
        return parse_gpx_with_elevation(res.text)
    except ValueError as e:
        print(f"    [GPX parse-fejl: {e}]")
        return None


# ── Geometri ────────────────────────────────────────────────────────────────

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def cumulative_distances_km(points: list[tuple[float, float, float]]) -> list[float]:
    """Kumulativ distance i km langs punktrækken, samme længde som points. cum[0] = 0.0."""
    cum = [0.0]
    for i in range(1, len(points)):
        d = haversine_km(points[i - 1][0], points[i - 1][1], points[i][0], points[i][1])
        cum.append(cum[-1] + d)
    return cum


# ── Segment-lokalisering ────────────────────────────────────────────────────

SEARCH_RADIUS_KM = 25.0
_WIDTH_FACTORS = [0.7, 0.85, 1.0, 1.15, 1.3, 1.5]
_SEARCH_STEP_POINTS = 3


def _candidate_score(elevation_gain_m: float, avg_gradient: float, db_climb: dict) -> float:
    """Lavere er bedre. Relativ fejl mod DB'ens højdemeter/hældning, 0 hvis intet at sammenligne med."""
    score = 0.0
    db_elev = db_climb.get("elevation_m")
    if db_elev:
        score += abs(elevation_gain_m - db_elev) / max(db_elev, 1)
    db_grad = db_climb.get("avg_gradient")
    if db_grad:
        score += abs(avg_gradient - db_grad) / max(db_grad, 1)
    return score


def locate_climb_segment(
    points: list[tuple[float, float, float]],
    cum_dist: list[float],
    stage_distance_km: float,
    km_from_start: float,
    length_km: float,
    db_climb: dict,
) -> list[tuple[float, float, float]]:
    """
    Lokaliserer stigningens segment i GPX-sporet.

    GPX'ens egen kumulative distance matcher sjældent den officielle
    etapedistance præcist — og afvigelsen er IKKE jævnt fordelt: GPS-støj
    fra sving koncentreres i de bakkede/snoede klatre-afsnit selv, så en ren
    proportional gætning systematisk overskyder (mere jo senere på ruten
    stigningen ligger — bekræftet empirisk på Tour de France 2026 etape 2,
    hvor overskuddet voksede fra ~3 km ved første stigning til ~14 km ved
    fjerde). Det proportionale gæt bruges derfor kun som udgangspunkt for en
    vinduessøgning: kandidatsegmenter omkring gættet scores mod DB'ens kendte
    højdemeter/hældning, og det bedst matchende segment vælges.
    """
    if stage_distance_km <= 0:
        raise ValueError("Ugyldig etapedistance")

    gpx_total = cum_dist[-1]
    scale = gpx_total / stage_distance_km
    naive_start_km = km_from_start * scale
    base_width_km = length_km * scale

    search_lo = max(0.0, naive_start_km - SEARCH_RADIUS_KM)
    search_hi = min(gpx_total, naive_start_km + SEARCH_RADIUS_KM)
    lo_idx = bisect.bisect_left(cum_dist, search_lo)
    hi_idx = max(bisect.bisect_left(cum_dist, search_hi), lo_idx + 1)

    best_pair: tuple[int, int] | None = None
    best_score: float | None = None

    for start_idx in range(lo_idx, hi_idx, _SEARCH_STEP_POINTS):
        start_km = cum_dist[start_idx]
        for factor in _WIDTH_FACTORS:
            end_km = start_km + base_width_km * factor
            if end_km > gpx_total:
                continue
            end_idx = min(bisect.bisect_left(cum_dist, end_km), len(points) - 1)
            if end_idx - start_idx < 2:
                continue

            dist_km = cum_dist[end_idx] - cum_dist[start_idx]
            if dist_km <= 0:
                continue
            elevation_gain_m = points[end_idx][2] - points[start_idx][2]
            avg_gradient = (elevation_gain_m / (dist_km * 1000)) * 100

            score = _candidate_score(elevation_gain_m, avg_gradient, db_climb)
            if best_score is None or score < best_score:
                best_score = score
                best_pair = (start_idx, end_idx)

    if best_pair is None:
        raise ValueError("Kunne ikke lokalisere et gyldigt GPX-segment for stigningen")

    start_idx, end_idx = best_pair
    segment = points[start_idx:end_idx + 1]
    if len(segment) < 2:
        raise ValueError("For få GPX-punkter i det lokaliserede segment")

    return segment


# ── Validering ──────────────────────────────────────────────────────────────

def derive_climb_stats(segment_points: list[tuple[float, float, float]]) -> dict:
    """Beregner nettohøjdemeter og gennemsnitshældning for et GPX-segment."""
    start_elev = segment_points[0][2]
    end_elev = segment_points[-1][2]
    elevation_gain_m = end_elev - start_elev

    dist_km = 0.0
    for i in range(1, len(segment_points)):
        dist_km += haversine_km(
            segment_points[i - 1][0], segment_points[i - 1][1],
            segment_points[i][0], segment_points[i][1],
        )

    avg_gradient = (elevation_gain_m / (dist_km * 1000)) * 100 if dist_km > 0 else 0.0

    return {
        "elevation_gain_m": round(elevation_gain_m),
        "avg_gradient": round(avg_gradient, 1),
        "distance_km": round(dist_km, 2),
    }


def within_tolerance(derived: dict, db_climb: dict) -> tuple[bool, str]:
    """
    Sammenligner GPX-udledte stats med DB'ens kendte klatredata.
    Returnerer (godkendt, forklaring). Springer et tjek over hvis DB ikke har
    den pågældende værdi. Samme ånd som climbfinder_agent.py's metrics_ok().
    """
    reasons = []

    db_elev = db_climb.get("elevation_m")
    if db_elev:
        diff = abs(derived["elevation_gain_m"] - db_elev)
        max_diff = max(100, db_elev * 0.25)
        if diff > max_diff:
            return False, f"højdemeter {derived['elevation_gain_m']}m vs DB {db_elev}m (diff {diff}m)"
        reasons.append(f"elev {derived['elevation_gain_m']}≈{db_elev}m")

    db_grad = db_climb.get("avg_gradient")
    if db_grad:
        diff = abs(derived["avg_gradient"] - db_grad)
        if diff > 2.5:
            return False, f"hældning {derived['avg_gradient']:.1f}% vs DB {db_grad}% (diff {diff:.1f}%)"
        reasons.append(f"grad {derived['avg_gradient']:.1f}≈{db_grad}%")

    return True, " | ".join(reasons) if reasons else "ingen metrics at tjekke"


# ── Sektionsberegning ───────────────────────────────────────────────────────

def _interp_at(xy_pairs: list[tuple[float, float]], x: float) -> float:
    """Lineær interpolation af y ved et givet x i en sorteret (x, y)-liste."""
    xs = [p[0] for p in xy_pairs]
    idx = bisect.bisect_left(xs, x)
    if idx == 0:
        return xy_pairs[0][1]
    if idx >= len(xy_pairs):
        return xy_pairs[-1][1]
    x0, y0 = xy_pairs[idx - 1]
    x1, y1 = xy_pairs[idx]
    frac = (x - x0) / (x1 - x0) if x1 > x0 else 0.0
    return y0 + frac * (y1 - y0)


def resample_elevation_profile(
    segment_points: list[tuple[float, float, float]], n: int = 200
) -> list[tuple[float, float]]:
    """
    Resampler et GPX-segment til n jævnt fordelte punkter langs distancen
    (lineær interpolation). Udjævner korte stigninger med få rå GPX-punkter,
    så sektionsgrænser ikke bliver støjede.
    """
    local_cum = [0.0]
    for i in range(1, len(segment_points)):
        d = haversine_km(
            segment_points[i - 1][0], segment_points[i - 1][1],
            segment_points[i][0], segment_points[i][1],
        )
        local_cum.append(local_cum[-1] + d)

    total = local_cum[-1]
    if total <= 0:
        raise ValueError("Segment har nul distance")

    xy_pairs = list(zip(local_cum, [p[2] for p in segment_points]))

    resampled = []
    for i in range(n):
        target = total * i / (n - 1)
        resampled.append((target, _interp_at(xy_pairs, target)))
    return resampled


def compute_gradient_sections(
    resampled: list[tuple[float, float]], n_sections: int = 20
) -> list[dict]:
    """Deler et resamplet højdeprofil i n_sections lige lange (efter distance) sektioner."""
    total = resampled[-1][0]
    section_len = total / n_sections

    sections = []
    for i in range(n_sections):
        start_km = i * section_len
        end_km = (i + 1) * section_len
        start_elev = _interp_at(resampled, start_km)
        end_elev = _interp_at(resampled, end_km)
        gradient = (end_elev - start_elev) / (section_len * 1000) * 100 if section_len > 0 else 0.0
        sections.append({
            "start_km":     round(start_km, 3),
            "end_km":       round(end_km, 3),
            "start_elev":   round(start_elev, 1),
            "end_elev":     round(end_elev, 1),
            "avg_gradient": round(gradient, 1),
        })
    return sections


# ── Farve ───────────────────────────────────────────────────────────────────

COLOR_STOPS: list[tuple[float, tuple[int, int, int]]] = [
    (0.0,  (255, 255, 255)),  # hvid
    (4.0,  (253, 224, 166)),  # lys rav
    (7.0,  (245, 148, 60)),   # orange
    (10.0, (214, 40, 40)),    # rød
    (13.0, (122, 12, 30)),    # mørkerød
    (15.0, (10, 10, 10)),     # sort
]


def gradient_to_color(gradient_pct: float) -> tuple[int, int, int]:
    """Kontinuerlig, stykkevis-lineær farveskala fra hvid (0%) til sort (15%+)."""
    g = max(0.0, gradient_pct)
    if g >= COLOR_STOPS[-1][0]:
        return COLOR_STOPS[-1][1]
    for (g0, c0), (g1, c1) in zip(COLOR_STOPS, COLOR_STOPS[1:]):
        if g0 <= g <= g1:
            frac = (g - g0) / (g1 - g0)
            return tuple(int(round(c0[k] + frac * (c1[k] - c0[k]))) for k in range(3))
    return COLOR_STOPS[-1][1]


# ── Rendering ───────────────────────────────────────────────────────────────

WIDTH, HEIGHT = 2400, 1200
BG_COLOR = (15, 23, 42)        # slate-900
TEXT_COLOR = (226, 232, 240)   # slate-200
GRID_COLOR = (51, 65, 85)      # slate-700
LINE_COLOR = (241, 245, 249)   # slate-100 (terrænkant)
BRAND_COLOR = (100, 116, 139)  # slate-500

PAD_LEFT, PAD_RIGHT, PAD_TOP, PAD_BOTTOM = 110, 40, 90, 90

_FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def _font(size: int):
    for p in _FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def render_climb_profile(
    climb_name: str,
    sections: list[dict],
    style: str,
    length_km: float,
    avg_gradient: float,
) -> Image.Image:
    """
    Renderer et ClimbFinder-inspireret stigningsprofil-billede.
    sections: output fra compute_gradient_sections().
    style: "full" (akser, %-labels, titel) eller "minimal" (kun kurve + højder).
    """
    if style not in ("full", "minimal"):
        raise ValueError(f"Ukendt stil: {style}")

    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    inner_w = WIDTH - PAD_LEFT - PAD_RIGHT
    inner_h = HEIGHT - PAD_TOP - PAD_BOTTOM

    all_elevs = [s["start_elev"] for s in sections] + [sections[-1]["end_elev"]]
    min_elev, max_elev = min(all_elevs), max(all_elevs)
    elev_range = max(max_elev - min_elev, 1.0)
    max_elev_padded = max_elev + elev_range * 0.08

    total_km = sections[-1]["end_km"]
    baseline_y = PAD_TOP + inner_h

    def to_xy(km: float, elev: float) -> tuple[float, float]:
        x = PAD_LEFT + (km / total_km) * inner_w
        y = PAD_TOP + inner_h - ((elev - min_elev) / (max_elev_padded - min_elev)) * inner_h
        return x, y

    # Terrænsektioner — hver farvet efter sin egen gennemsnitshældning
    for s in sections:
        x0, y0 = to_xy(s["start_km"], s["start_elev"])
        x1, y1 = to_xy(s["end_km"], s["end_elev"])
        color = gradient_to_color(s["avg_gradient"])
        draw.polygon([(x0, baseline_y), (x0, y0), (x1, y1), (x1, baseline_y)], fill=color)

    # Terrænkant
    outline_pts = [to_xy(s["start_km"], s["start_elev"]) for s in sections]
    outline_pts.append(to_xy(sections[-1]["end_km"], sections[-1]["end_elev"]))
    draw.line(outline_pts, fill=LINE_COLOR, width=4)

    start_elev = sections[0]["start_elev"]
    summit_elev = sections[-1]["end_elev"]

    if style == "full":
        for i in range(5):
            elev = min_elev + (max_elev_padded - min_elev) * i / 4
            _, y = to_xy(0, elev)
            draw.line([(PAD_LEFT, y), (WIDTH - PAD_RIGHT, y)], fill=GRID_COLOR, width=1)
            draw.text((PAD_LEFT - 15, y), f"{int(round(elev))}m", font=_font(24),
                       fill=TEXT_COLOR, anchor="rm")

        step = max(1, round(total_km / 8))
        km_marker = 0
        while km_marker <= total_km:
            x, _ = to_xy(km_marker, min_elev)
            draw.line([(x, baseline_y), (x, baseline_y + 8)], fill=GRID_COLOR, width=1)
            draw.text((x, baseline_y + 15), f"{km_marker}km", font=_font(22),
                       fill=TEXT_COLOR, anchor="ma")
            km_marker += step

        for s in sections:
            mid_km = (s["start_km"] + s["end_km"]) / 2
            mid_elev = (s["start_elev"] + s["end_elev"]) / 2
            x, y = to_xy(mid_km, mid_elev)
            draw.text((x, y - 20), f"{s['avg_gradient']:.0f}%", font=_font(26),
                       fill=(255, 255, 255), anchor="mb", stroke_width=2, stroke_fill=(0, 0, 0))

        draw.text((PAD_LEFT, 30), climb_name, font=_font(40), fill=TEXT_COLOR, anchor="lm")
        draw.text((PAD_LEFT, 65), f"{length_km:.1f} km @ {avg_gradient:.1f}%",
                   font=_font(26), fill=BRAND_COLOR, anchor="lm")
        draw.text((WIDTH - PAD_RIGHT, HEIGHT - 20), "klassementet.dk",
                   font=_font(22), fill=BRAND_COLOR, anchor="rb")

    x0, y0 = to_xy(0, start_elev)
    draw.text((x0, y0 + 15), f"{int(round(start_elev))}m", font=_font(30),
               fill=TEXT_COLOR, anchor="ma")
    x1, y1 = to_xy(total_km, summit_elev)
    draw.text((x1, y1 - 15), f"{int(round(summit_elev))}m", font=_font(30),
               fill=TEXT_COLOR, anchor="mb")

    return img


# ── Supabase ────────────────────────────────────────────────────────────────

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
        f"&select=id,stage_number,distance_km&limit=1",
        headers=SB_AUTH,
    )
    data = res.json()
    return data[0] if res.ok and data else None


def get_climbs_for_stage(stage_id: str) -> list[dict]:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stage_climbs"
        f"?stage_id=eq.{stage_id}"
        f"&select=id,name,km_from_start,length_km,elevation_m,avg_gradient,profile_image_url"
        f"&order=km_from_start.asc",
        headers=SB_AUTH,
    )
    return res.json() if res.ok else []


def get_stages_for_race(race_id: str) -> list[dict]:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages"
        f"?race_id=eq.{race_id}&select=id,stage_number,distance_km"
        f"&order=stage_number.asc",
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
        print(f"    Upload fejl {res.status_code}: {res.text[:120]}")
        return None
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{path}"


def update_climb_profile(climb_id: str, profile_url: str) -> bool:
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/stage_climbs?id=eq.{climb_id}",
        json={"profile_image_url": profile_url, "source": "generated"},
        headers=SB_HEADERS,
    )
    return res.ok


# ── Hovedpipeline ─────────────────────────────────────────────────────────────

def process_climb(
    stage: dict,
    climb: dict,
    gpx_points: list[tuple[float, float, float]],
    cum_dist: list[float],
    style: str,
    write_db: bool,
    overwrite: bool,
) -> str:
    """Genererer og gemmer profilbillede(r) for én stigning. Returnerer en statusbesked."""
    km_from_start = climb.get("km_from_start")
    length_km = climb.get("length_km")
    if km_from_start is None or not length_km:
        return f"  ✗ {climb['name']}: mangler km_from_start/length_km i DB"

    if write_db and climb.get("profile_image_url") and not overwrite:
        return f"  → {climb['name']}: har allerede et profilbillede, springer over (brug --overwrite)"

    try:
        segment = locate_climb_segment(
            gpx_points, cum_dist, stage["distance_km"],
            float(km_from_start), float(length_km), climb,
        )
    except ValueError as e:
        return f"  ✗ {climb['name']}: {e}"

    derived = derive_climb_stats(segment)
    ok, reason = within_tolerance(derived, climb)
    if not ok:
        return f"  ✗ {climb['name']}: GPX-segment matcher ikke DB-data — {reason}"

    resampled = resample_elevation_profile(segment)
    sections = compute_gradient_sections(resampled)

    styles = ["full", "minimal"] if style == "both" else [style]
    urls = []
    for s in styles:
        img = render_climb_profile(
            climb["name"], sections, s,
            length_km=float(length_km),
            avg_gradient=float(climb.get("avg_gradient") or derived["avg_gradient"]),
        )
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        path = f"generated/{climb['id']}.png" if write_db else f"test/{climb['id']}-{s}.png"
        url = upload_image(path, buf.getvalue())
        if not url:
            return f"  ✗ {climb['name']} ({s}): upload fejlede"
        urls.append(url)

        if write_db and not update_climb_profile(climb["id"], url):
            return f"  ✗ {climb['name']}: DB-opdatering fejlede"

    status = "opdateret i DB" if write_db else "genereret (test)"
    return f"  ✓ {climb['name']} — {reason} — {status}: " + " | ".join(urls)


def process_one_stage(race_slug: str, stage: dict, style: str, write_db: bool, overwrite: bool) -> dict:
    """
    Kører hele climb-profile-flowet for én allerede-opslået etape.
    Returnerer et resultat-sammendrag (bruges både af enkelt-etape- og --all-flowet).
    """
    stage_number = stage["stage_number"]
    summary = {"stage": stage_number, "ok": 0, "skipped": 0, "failed": 0, "no_climbs": False, "no_gpx": False}

    climbs = get_climbs_for_stage(stage["id"])
    if not climbs:
        print(f"  Etape {stage_number}: ingen stigninger, springer over")
        summary["no_climbs"] = True
        return summary

    print(f"\n--- Etape {stage_number} ---")
    print("Henter GPX...")
    gpx_points = download_stage_gpx(race_slug, stage_number)
    if not gpx_points:
        print(f"  Etape {stage_number}: kunne ikke hente/parse GPX-fil, springer over")
        summary["no_gpx"] = True
        return summary

    cum_dist = cumulative_distances_km(gpx_points)
    print(f"GPX: {len(gpx_points)} punkter, {cum_dist[-1]:.1f} km "
          f"(officiel distance: {stage['distance_km']} km)\n")

    for climb in climbs:
        result = process_climb(stage, climb, gpx_points, cum_dist, style, write_db, overwrite)
        print(result)
        if result.startswith("  ✓"):
            summary["ok"] += 1
        elif "springer over" in result:
            summary["skipped"] += 1
        else:
            summary["failed"] += 1

    return summary


def process_stage(race_slug: str, stage_number: int, style: str, write_db: bool, overwrite: bool) -> None:
    if write_db and style == "both":
        print("Fejl: --write-db kræver ét enkelt --style (full eller minimal), ikke 'both'")
        return

    race_id = get_race_id(race_slug)
    if not race_id:
        print(f"Løb ikke fundet: {race_slug}")
        return

    stage = get_stage(race_id, stage_number)
    if not stage or not stage.get("distance_km"):
        print(f"Etape {stage_number} ikke fundet eller mangler distance_km")
        return

    print(f"climb_profile_generator.py — {race_slug} etape {stage_number}")
    process_one_stage(race_slug, stage, style, write_db, overwrite)


def process_race_all_stages(race_slug: str, style: str, write_db: bool, overwrite: bool) -> None:
    if write_db and style == "both":
        print("Fejl: --write-db kræver ét enkelt --style (full eller minimal), ikke 'both'")
        return

    if race_slug not in CYCLINGSTAGE_GPX_PAGES:
        print(f"Ingen GPX-kilde konfigureret for '{race_slug}' (se CYCLINGSTAGE_GPX_PAGES) — springer løbet over.")
        return

    race_id = get_race_id(race_slug)
    if not race_id:
        print(f"Løb ikke fundet: {race_slug}")
        return

    stages = [s for s in get_stages_for_race(race_id) if s.get("distance_km")]
    if not stages:
        print(f"Ingen etaper med distance_km fundet for {race_slug}")
        return

    print(f"climb_profile_generator.py — {race_slug}, alle {len(stages)} etaper")

    summaries = [process_one_stage(race_slug, stage, style, write_db, overwrite) for stage in stages]

    total_ok = sum(s["ok"] for s in summaries)
    total_skipped = sum(s["skipped"] for s in summaries)
    total_failed = sum(s["failed"] for s in summaries)
    no_climb_stages = [s["stage"] for s in summaries if s["no_climbs"]]
    no_gpx_stages = [s["stage"] for s in summaries if s["no_gpx"]]

    print(f"\n{'=' * 60}")
    print(f"Samlet resultat — {race_slug}")
    print(f"  ✓ genereret/opdateret : {total_ok}")
    print(f"  → sprunget over (havde allerede billede): {total_skipped}")
    print(f"  ✗ fejlet (tolerance/lokalisering/upload) : {total_failed}")
    if no_climb_stages:
        print(f"  Etaper uden stigninger: {no_climb_stages}")
    if no_gpx_stages:
        print(f"  Etaper uden GPX-fil   : {no_gpx_stages}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--race", required=True, help="Løb-slug, fx tour-de-france-2026")
    stage_group = parser.add_mutually_exclusive_group(required=True)
    stage_group.add_argument("--stage", type=int, help="Etapenummer")
    stage_group.add_argument("--all", action="store_true", help="Kør for alle etaper i løbet")
    parser.add_argument("--style", choices=["full", "minimal", "both"], default="both",
                         help="Hvilken stilart der skal genereres (default: begge, kun ved test)")
    parser.add_argument("--write-db", action="store_true",
                         help="Upload til generated/ og patch profile_image_url (default: kun test/-upload)")
    parser.add_argument("--overwrite", action="store_true",
                         help="Ved --write-db: overskriv stigninger der allerede har et profilbillede")
    args = parser.parse_args()

    if args.all:
        process_race_all_stages(args.race, args.style, args.write_db, args.overwrite)
    else:
        process_stage(args.race, args.stage, args.style, args.write_db, args.overwrite)
