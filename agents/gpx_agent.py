"""
gpx_agent.py
Downloader GPX-ruter fra cyclingstage.com og gemmer koordinater i
stages.route_points — det er dem, kortet tegner ruten af.

Løbene og GPX-opslaget kommer fra climb_profile_generator, så der kun findes
ÉN liste over, hvilke løb vi har en rute til.

Kør: python gpx_agent.py                          # alle kendte løb
     python gpx_agent.py --race il-lombardia-2026
"""

import os, sys, io, time, argparse, requests
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import climb_profile_generator as cpg

# climb_profile_generator pakker selv sys.stdout ind ved import ovenfor. Pakker
# vi den ind EN GANG TIL om den samme buffer, mister dens wrapper sin sidste
# reference, bliver frigivet og lukker bufferen — hvorefter alt print dør med
# "I/O operation on closed file". Derfor kun, hvis der ikke allerede er en
# UTF-8-wrapper. Samme fælde er beskrevet i data_sources.py._agent_attr().
if not isinstance(sys.stdout, io.TextIOWrapper) or (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SB_AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
SB_HEADERS = {**SB_AUTH, "Content-Type": "application/json", "Prefer": "return=minimal"}

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

MAX_POINTS = 400  # Maks antal koordinatpar gemt per etape


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
    # Løbene kommer fra climb_profile_generator, ikke fra en liste her.
    # Den lokale RACES-liste kendte kun 4 løb og var ikke blevet rørt, siden
    # CYCLINGSTAGE_GPX_PAGES voksede til 20+ — så alle klassikerne, heriblandt
    # Il Lombardia, kunne ikke få rutepunkter, og kortet tegnede en stiplet
    # streg mellem start og mål i stedet for den faktiske rute. To lister over
    # de samme løb kommer altid ud af trit; nu er der én.
    alle = cpg.CYCLINGSTAGE_GPX_PAGES
    slugs = [race_slug] if race_slug else list(alle)

    for slug in slugs:
        if slug not in alle:
            print(f"Ukendt løb: {slug}. Kendte: {', '.join(sorted(alle))}")
            continue

        print(f"\n{slug}")
        race_id = get_race_id(slug)
        if not race_id:
            print("  Løb ikke fundet i DB")
            continue

        stages = get_stages(race_id)
        print(f"  {len(stages)} etaper i DB")

        updated = 0
        for stage in stages:
            n = stage["stage_number"]
            # Samme opslag som resten af pipelinen: det kender både
            # etapeløbenes "stage-N"-filer og endagsløbenes "route.gpx".
            gpx_url = cpg.get_gpx_url_for_stage(slug, n)
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
