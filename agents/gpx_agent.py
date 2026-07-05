"""
gpx_agent.py
Downloader GPX-ruter fra cyclingstage.com og gemmer koordinater i stages.route_points.

Kør: python gpx_agent.py                          # alle kendte løb
     python gpx_agent.py --race giro-d-italia-2026
"""

import os, sys, io, re, time, json, argparse, requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SB_AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
SB_HEADERS = {**SB_AUTH, "Content-Type": "application/json", "Prefer": "return=minimal"}

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Løb-slug → cyclingstage.com GPX-side
RACES = {
    "giro-d-italia-2026":         "https://www.cyclingstage.com/giro-2026-gpx",
    "tour-de-france-2026":        "https://www.cyclingstage.com/tour-de-france-2026-gpx",
    "criterium-du-dauphine-2026": "https://www.cyclingstage.com/criterium-du-dauphine-2026-gpx",
    "tour-de-suisse-2026":        "https://www.cyclingstage.com/tour-de-suisse-2026-gpx",
}

MAX_POINTS = 400  # Maks antal koordinatpar gemt per etape


def get_gpx_urls(gpx_page_url: str) -> dict[int, str]:
    """Scraper en cyclingstage GPX-side og returnerer {etapenr: gpx_url}."""
    res = requests.get(gpx_page_url, headers={"User-Agent": UA}, timeout=15)
    if not res.ok:
        print(f"  Kan ikke hente GPX-side: {res.status_code}")
        return {}
    soup = BeautifulSoup(res.text, "html.parser")
    result: dict[int, str] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".gpx" not in href:
            continue
        m = re.search(r"stage-(\d+)", href)
        if not m:
            continue
        n = int(m.group(1))
        url = href if href.startswith("http") else "https://cdn.cyclingstage.com" + href
        result[n] = url
    return result


def parse_gpx(content: str) -> list[list[float]] | None:
    """Parser GPX XML og returnerer samplede [lat, lon]-par."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        print(f"    XML-fejl: {e}")
        return None

    # Prøv begge GPX-namespace-versioner (1.0 og 1.1)
    points = []
    for ns_uri in ("http://www.topografix.com/GPX/1/1", "http://www.topografix.com/GPX/1/0"):
        ns = {"g": ns_uri}
        points = root.findall(".//g:trkpt", ns)
        if not points:
            points = root.findall(".//g:rtept", ns)
        if not points:
            points = root.findall(".//g:wpt", ns)
        if points:
            break

    # Fallback: namespace-agnostisk søgning
    if not points:
        points = [el for el in root.iter() if el.tag.endswith("trkpt") or el.tag.endswith("rtept")]

    if not points:
        return None

    coords = [[float(p.get("lat")), float(p.get("lon"))] for p in points]

    # Downsample jævnt til MAX_POINTS
    if len(coords) > MAX_POINTS:
        step = len(coords) / MAX_POINTS
        coords = [coords[int(i * step)] for i in range(MAX_POINTS)]
        coords.append([float(points[-1].get("lat")), float(points[-1].get("lon"))])

    return coords


def download_gpx(url: str) -> list[list[float]] | None:
    try:
        res = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        if not res.ok:
            print(f"    HTTP {res.status_code}")
            return None
        return parse_gpx(res.text)
    except Exception as e:
        print(f"    Download-fejl: {e}")
        return None


def get_race_id(slug: str) -> str | None:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?slug=eq.{slug}&select=id&limit=1",
        headers=SB_AUTH,
    )
    return res.json()[0]["id"] if res.ok and res.json() else None


def get_stages(race_id: str) -> list[dict]:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages"
        f"?race_id=eq.{race_id}&select=id,stage_number&order=stage_number.asc",
        headers=SB_AUTH,
    )
    return res.json() if res.ok else []


def save_route(stage_id: str, points: list) -> bool:
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/stages?id=eq.{stage_id}",
        json={"route_points": points},
        headers=SB_HEADERS,
    )
    return res.ok


def run(race_slug: str | None) -> None:
    races = {race_slug: RACES[race_slug]} if race_slug else RACES

    for slug, gpx_page_url in races.items():
        if race_slug and slug not in RACES:
            print(f"Ukendt løb: {slug}. Kendte: {', '.join(RACES)}")
            continue

        print(f"\n{slug}")
        race_id = get_race_id(slug)
        if not race_id:
            print("  Løb ikke fundet i DB")
            continue

        stages = get_stages(race_id)
        gpx_urls = get_gpx_urls(gpx_page_url)
        print(f"  {len(stages)} etaper i DB, {len(gpx_urls)} GPX-filer på cyclingstage")

        updated = 0
        for stage in stages:
            n = stage["stage_number"]
            gpx_url = gpx_urls.get(n)
            if not gpx_url:
                print(f"  E{n}: ingen GPX-URL")
                continue

            points = download_gpx(gpx_url)
            if not points:
                print(f"  E{n}: GPX-fejl")
                continue

            if save_route(stage["id"], points):
                print(f"  E{n} ✓  {len(points)} punkter  ({gpx_url.split('/')[-1]})")
                updated += 1
            else:
                print(f"  E{n}: DB-fejl")

            time.sleep(0.4)

        print(f"  Færdig: {updated}/{len(stages)} etaper opdateret")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--race", default=None, help="Løb-slug, udelad for alle")
    args = parser.parse_args()
    run(args.race)
