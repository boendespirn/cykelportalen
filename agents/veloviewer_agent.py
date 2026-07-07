"""
veloviewer_agent.py
Ny prioritet 1 i stignings-pipelinen: finder det korrekte Strava-segment for
en stigning via Stravas officielle /segments/explore-API (bounding box
beregnet fra klatrens eget GPX-udtræk), verificerer det mod vores DB-data
(veloviewer_strava_api.py), og gemmer kun det bare segment-ID
(stage_climbs.veloviewer_segment_id) — frontend bygger selv VeloViewers
embed-URL derfra (jf. docs/superpowers/specs/2026-07-07-veloviewer-climb-profiles-design.md).

Ingen login, ingen browser nødvendig — kun Stravas officielle API (OAuth via
STRAVA_CLIENT_ID/STRAVA_CLIENT_SECRET/STRAVA_REFRESH_TOKEN i .env). Strava
Route Builder + appens segment-liste blev afprøvet under udvikling, men
droppet til fordel for denne simplere metode: /segments/explore returnerer
kun top-10 mest populære segmenter i en boks, men berømte Tour de
France-klatre ER de mest populære segmenter i deres område (verificeret:
Col du Tourmalet fundet med præcis navnet "Col du Tourmalet (par Sainte
Marie de Campan)" og godkendt af tolerance-tjekket). Mindre kendte, lokale
stigninger finder muligvis intet match her — de falder som normalt tilbage
til climbfinder_agent.py/climb_profile_generator.py.

Kør (test, ingen DB-skrivning):
    python agents/veloviewer_agent.py --race tour-de-france-2026 --stage 6

Kør (produktion):
    python agents/veloviewer_agent.py --race tour-de-france-2026 --stage 6 --write-db
    python agents/veloviewer_agent.py --all --write-db
"""

import os
import re
import sys
import io
import time
import argparse

import requests
from dotenv import load_dotenv

load_dotenv()

import climb_profile_generator as cpg
import veloviewer_strava_api as strava_api

sys.stdout.reconfigure(line_buffering=True, write_through=True)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

# Udvider klatrens egen GPX-bbox med denne andel på hver led, så vi ikke
# misser et segment, der starter/slutter lidt uden for vores udtrukne vindue.
BBOX_PADDING_RATIO = 0.2
DELAY = 1.0  # pause mellem Strava API-kald pr. kandidat


# ── Supabase helpers (samme mønster som climbfinder_agent.py) ─────────────────

def sb_get(table: str, query: str) -> list[dict]:
    res = requests.get(f"{SUPABASE_URL}/rest/v1/{table}{query}", headers=SB_HEADERS)
    return res.json() if res.ok else []


def get_race(race_slug: str) -> dict | None:
    rows = sb_get("races", f"?slug=eq.{race_slug}&select=id,name&limit=1")
    return rows[0] if rows else None


def get_stages(race_id: str, stage_number: int | None) -> list[dict]:
    url = (
        f"?race_id=eq.{race_id}"
        f"&select=id,stage_number,distance_km"
        f"&order=stage_number.asc"
    )
    if stage_number:
        url += f"&stage_number=eq.{stage_number}"
    return sb_get("stages", url)


def get_climbs_for_stage(stage_id: str, only_missing: bool) -> list[dict]:
    url = (
        f"?stage_id=eq.{stage_id}"
        f"&select=id,name,km_from_start,length_km,elevation_m,avg_gradient,veloviewer_segment_id"
        f"&order=km_from_start.asc"
    )
    rows = sb_get("stage_climbs", url)
    return [r for r in rows if not r.get("veloviewer_segment_id")] if only_missing else rows


def update_veloviewer_segment(climb_id: str, segment_id: int) -> bool:
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/stage_climbs?id=eq.{climb_id}",
        json={"veloviewer_segment_id": segment_id},
        headers=SB_HEADERS,
    )
    return res.status_code in (200, 204)


# ── Segment-matching ───────────────────────────────────────────────────────────

def compute_padded_bbox(points: list[tuple[float, float, float]]) -> str:
    """Bounding box (min_lat,min_lng,max_lat,max_lng) om et GPX-punktsæt, udvidet med BBOX_PADDING_RATIO."""
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    lat_pad = (max_lat - min_lat) * BBOX_PADDING_RATIO or 0.01
    lon_pad = (max_lon - min_lon) * BBOX_PADDING_RATIO or 0.01
    return f"{min_lat - lat_pad:.6f},{min_lon - lon_pad:.6f},{max_lat + lat_pad:.6f},{max_lon + lon_pad:.6f}"


def find_veloviewer_segment(race_slug: str, stage_number: int, stage_distance_km: float,
                             db_climb: dict) -> int | None:
    """
    Udtrækker klatrens GPX-segment (genbruger climb_profile_generator.py's
    vinduessøgning), beregner dens bounding box, og finder + verificerer et
    Strava-segment via det officielle API. Returnerer segment-ID ved match,
    ellers None (aldrig gættet på — jf. CLAUDE.md §7).
    """
    points = cpg.download_stage_gpx(race_slug, stage_number)
    if not points:
        print(f"    [skip] ingen GPX-kilde for {race_slug} etape {stage_number}")
        return None

    cum_dist = cpg.cumulative_distances_km(points)
    try:
        segment_points = cpg.locate_climb_segment(
            points, cum_dist, stage_distance_km,
            db_climb["km_from_start"], db_climb["length_km"], db_climb,
        )
    except ValueError as e:
        print(f"    [skip] kunne ikke lokalisere GPX-segment: {e}")
        return None

    bounds = compute_padded_bbox(segment_points)
    candidates = strava_api.explore_segments(bounds)
    if not candidates:
        print("    [intet match] /segments/explore fandt intet i boksen")
        return None

    for cand in candidates:
        seg = strava_api.get_segment(cand["id"])
        if not seg:
            continue
        ok, reason = strava_api.segment_matches_climb(seg, db_climb)
        if ok:
            print(f"    [match] segment {cand['id']} godkendt ({reason})")
            return cand["id"]
        time.sleep(DELAY)

    print("    [intet match] falder tilbage til climbfinder_agent.py/climb_profile_generator.py")
    return None


# ── Orkestrering ────────────────────────────────────────────────────────────────

def process_stage(race_slug: str, stage: dict, overwrite: bool, write_db: bool) -> None:
    climbs = get_climbs_for_stage(stage["id"], only_missing=not overwrite)
    if not climbs:
        print(f"  Etape {stage['stage_number']}: ingen stigninger at behandle.")
        return

    for climb in climbs:
        print(f"  → {climb['name']} (km {climb.get('km_from_start')}, {climb.get('length_km')} km)")
        match_id = find_veloviewer_segment(race_slug, stage["stage_number"], stage["distance_km"], climb)
        if match_id is None:
            continue

        if write_db:
            if update_veloviewer_segment(climb["id"], match_id):
                print(f"    [gemt] veloviewer_segment_id={match_id}")
            else:
                print("    [FEJL] kunne ikke skrive til DB")
        else:
            print(f"    [dry-run] ville have gemt veloviewer_segment_id={match_id}")


def process_race(race_slug: str, stage_number: int | None, overwrite: bool, write_db: bool) -> None:
    race = get_race(race_slug)
    if not race:
        print(f"Løb ikke fundet: {race_slug}")
        return
    stages = get_stages(race["id"], stage_number)
    if not stages:
        print(f"Ingen etaper fundet for {race_slug}" + (f" etape {stage_number}" if stage_number else ""))
        return
    for stage in stages:
        print(f"[{race_slug}] Etape {stage['stage_number']}")
        process_stage(race_slug, stage, overwrite, write_db)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--race", help="Kør for ét løb (slug)")
    group.add_argument("--all", action="store_true", help="Alle løb i CYCLINGSTAGE_GPX_PAGES")
    parser.add_argument("--stage", type=int, help="Kun én etape")
    parser.add_argument("--overwrite", action="store_true", help="Genkør selv allerede-matchede stigninger")
    parser.add_argument("--write-db", action="store_true", help="Skriv veloviewer_segment_id til DB (ellers dry-run)")
    args = parser.parse_args()

    if args.all:
        for slug in cpg.CYCLINGSTAGE_GPX_PAGES:
            process_race(slug, args.stage, args.overwrite, args.write_db)
    else:
        process_race(args.race, args.stage, args.overwrite, args.write_db)
