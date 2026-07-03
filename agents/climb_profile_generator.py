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
