"""
climb_profile_generator.py
Genererer klassementet.dk's egne stigningsprofil-billeder direkte fra raa
GPX-hoejdedata, som fallback naar ClimbFinder ikke har et verificeret match.

Stil: terraensilhuet delt i 10 sektioner, farvet efter haeldning
(hvid 0% -> roed 10% -> moerkeroed ~13% -> sort 15%+), i to varianter
("full" med akser/labels, "minimal" uden).

Kilde til GPX: cyclingstage.com (samme kilde som gpx_agent.py, men parset
med hoejde bevaret og uden downsampling).

Kør (test — genererer begge stilarter, uploader kun til test/-sti, ingen DB-skrivning):
     python agents/climb_profile_generator.py --race tour-de-france-2026 --stage 2

Kør (produktion — skriver profile_image_url for stigninger uden billede):
     python agents/climb_profile_generator.py --race tour-de-france-2026 --stage 2 \
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
        m = re.fullmatch(r".*stage-(\d+)-route\.gpx", href)
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

def locate_climb_segment(
    points: list[tuple[float, float, float]],
    cum_dist: list[float],
    stage_distance_km: float,
    km_from_start: float,
    length_km: float,
) -> list[tuple[float, float, float]]:
    """
    Lokaliserer stigningens segment i GPX-sporet ved proportional position,
    fordi GPX'ens egen kumulative distance sjældent matcher den officielle
    etapedistance præcist (GPS-støj i sving inflaterer GPX-distancen).
    """
    if stage_distance_km <= 0:
        raise ValueError("Ugyldig etapedistance")

    gpx_total = cum_dist[-1]
    start_target = (km_from_start / stage_distance_km) * gpx_total
    end_target = ((km_from_start + length_km) / stage_distance_km) * gpx_total

    start_idx = bisect.bisect_left(cum_dist, start_target)
    end_idx = bisect.bisect_left(cum_dist, end_target)

    start_idx = max(0, min(start_idx, len(points) - 1))
    end_idx = max(0, min(end_idx, len(points) - 1))

    if end_idx <= start_idx:
        raise ValueError("Kunne ikke lokalisere et gyldigt GPX-segment for stigningen")

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
    resampled: list[tuple[float, float]], n_sections: int = 10
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
