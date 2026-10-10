"""
veloviewer_agent.py
Ny prioritet 1 i stignings-pipelinen: finder det korrekte Strava-segment for
en stigning via Stravas officielle /segments/explore-API (bounding box
beregnet fra klatrens eget GPX-udtræk), verificerer det mod vores DB-data
(veloviewer_strava_api.py), og gemmer kun det bare segment-ID
(stage_climbs.veloviewer_segment_id) — frontend bygger selv VeloViewers
embed-URL derfra (jf. docs/superpowers/specs/2026-07-07-veloviewer-climb-profiles-design.md).

Ingen login, ingen browser nødvendig — kun Stravas officielle API (OAuth via
STRAVA_CLIENT_ID/STRAVA_CLIENT_SECRET/STRAVA_REFRESH_TOKEN i .env).

Søgestrategi (revideret 2026-07-22 — den oprindelige gav kun 10% dækning):
  1. Klatrens spor i GPX'en forankres til det REELLE toppunkt (højeste
     GPX-punkt inden for ±3 km af den officielle top-km), ikke til et
     proportionalt gæt.
  2. Kandidater samles fra flere /segments/explore-kald: hele klatrens boks,
     en kategori-filtreret søgning (min_cat/max_cat ud fra vores officielle
     ASO-kategori) og de to halvdele hver for sig — explore giver kun 10
     segmenter pr. kald, så flere vinkler giver markant flere kandidater.
  3. Verifikation sker på GEOMETRI: kandidatens egen rutelinje sammenlignes
     med klatrens GPX-spor. Navnetjek bruges IKKE — Strava-navne er
     brugerskabte, og det korrekte segment for "Côte d'Engins" hedder
     "D531 Climb" (100% geometrisk sammenfald). Nedkørsler frasorteres på
     negativ gradient, da de ligger oven i stigningen geografisk.
  4. Ingen /segments/{id}-opslag: explore-svaret indeholder allerede alt det
     nødvendige, hvilket sparer ~10 læsekald pr. kandidat — det er dét, der
     gør det muligt at scanne hele databasen inden for Stravas daglige loft.

Stigninger uden godkendt match falder som normalt tilbage til
climbfinder_agent.py/climb_profile_generator.py.

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
import bisect
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

DELAY = 1.0  # pause mellem Strava API-kald pr. kandidat


class DailyLimitReached(Exception):
    """Stravas daglige læse-loft er brugt op — kørslen skal stoppe helt.

    Uden dette ville tomme API-svar resten af dagen blive tolket som
    "ingen segmenter fundet", så en batch-kørsel stille rapporterede falske
    negativer for alle resterende stigninger.
    """


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
        f"&select=id,name,km_from_start,length_km,elevation_m,avg_gradient,category,veloviewer_segment_id"
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

def compute_bbox(points: list[tuple[float, float, float]], pad_ratio: float = 0.0) -> str:
    """Bounding box (min_lat,min_lng,max_lat,max_lng) om et GPX-punktsæt, evt. udvidet med pad_ratio."""
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    lat_pad = (max_lat - min_lat) * pad_ratio or 0.01 * pad_ratio
    lon_pad = (max_lon - min_lon) * pad_ratio or 0.01 * pad_ratio
    return f"{min_lat - lat_pad:.6f},{min_lon - lon_pad:.6f},{max_lat + lat_pad:.6f},{max_lon + lon_pad:.6f}"


# Vores officielle ASO-kategori -> Stravas climb_category-skala
ASO_TO_STRAVA_CAT = {"HC": 5, "1": 4, "2": 3, "3": 2, "4": 1}

SUMMIT_SNAP_KM = 3.0   # sådan langt må vi lede efter det reelle toppunkt

_gpx_cache: dict[tuple[str, int], list | None] = {}


def stage_gpx(race_slug: str, stage_number: int):
    """GPX for en etape, cachet — alle etapens stigninger deler samme fil."""
    key = (race_slug, stage_number)
    if key not in _gpx_cache:
        _gpx_cache[key] = cpg.download_stage_gpx(race_slug, stage_number)
    return _gpx_cache[key]


def climb_path_from_gpx(points: list, cum_dist: list[float], stage_distance_km: float,
                         db_climb: dict) -> list[tuple[float, float]]:
    """
    Klatrens (lat, lon)-spor, forankret til det REELLE toppunkt.

    GPX'ens kumulative distance afviger typisk 4-5% fra den officielle, så et
    rent proportionalt gæt rammer skævt. Vi kender til gengæld klatrens
    officielle top-km (km_from_start + length_km, jf. aso_roadbook_agent.py) —
    så vi snapper til det højeste GPX-punkt inden for ±SUMMIT_SNAP_KM af det
    skalerede gæt og går derfra klatrens længde tilbage. Det er samme trick
    som stage_profile_generator.py bruger til at placere sine topmarkører, og
    det er mere robust end locate_climb_segment()s scoring, som kan vælge et
    forkert delsegment (bekræftet: Col de Coudons gav et 16,3 km spor for en
    10,7 km klatring).
    """
    gpx_total = cum_dist[-1]
    scale = gpx_total / stage_distance_km
    length_gpx = db_climb["length_km"] * scale

    def spor(summit_km_gaet: float):
        """Spor + faktisk GPX-stigning for ét gaet paa toppens placering."""
        summit_km = min(max(summit_km_gaet, 0.0), gpx_total)
        lo = bisect.bisect_left(cum_dist, max(0.0, summit_km - SUMMIT_SNAP_KM))
        hi = bisect.bisect_left(cum_dist, min(gpx_total, summit_km + SUMMIT_SNAP_KM))
        if hi <= lo:
            return None, None
        summit_idx = max(range(lo, hi), key=lambda i: points[i][2])
        start_idx = bisect.bisect_left(cum_dist, max(0.0, cum_dist[summit_idx] - length_gpx))
        if summit_idx - start_idx < 2:
            return None, None
        # Afvis et spor, der er blevet KLIPPET af etapens start. Uden dette
        # kunne "top"-fortolkningen af en klatring, hvis beregnede start ligger
        # foer km 0, give et kunstigt kort spor, som saa vandt sammenligningen
        # paa hoejdemeter — bekraeftet paa Port de Envalira (km_from_start 15,7
        # mod laengde 24,4), hvor det gav et 15,7 km spor i stedet for 24,4 km
        # og dermed 68% rute-sammenfald paa et ellers perfekt segment.
        faktisk_km = cum_dist[summit_idx] - cum_dist[start_idx]
        if faktisk_km < length_gpx * 0.8:
            return None, None
        udsnit = points[start_idx:summit_idx + 1]
        return [(q[0], q[1]) for q in udsnit], udsnit[-1][2] - udsnit[0][2]

    # Fortolkning A: km_from_start er klatrens START (den hidtidige antagelse).
    sti_a, stigning_a = spor((db_climb["km_from_start"] + db_climb["length_km"]) * scale)

    # Fortolkning B: km_from_start er klatrens TOP.
    #
    # Maalt 2026-08-20 paa Vuelta 2026 er feltet inkonsistent: 31 af 58
    # stigninger passer bedst som START, 27 bedst som TOP (kilderne er en
    # blanding af 'pcs', 'vision' og 'generated'). Anker vi forkert, ligger
    # sammenligningssporet et helt andet sted paa etapen, og saa afviser
    # geo_overlap() det RIGTIGE segment — bekraeftet paa Alto de Velefique,
    # hvor Stravas segment ligger paa ruten km 122,3-135,2 (17-41 m fra den),
    # mens vi sammenlignede mod km 132-143.
    #
    # Vi skifter kun til B, naar GPX'ens EGEN hoejdekurve modsiger A og
    # bekraefter B. Stemmer A (som paa Tour de France, hvor feltet er
    # konsistent), roeres intet — aendringen kan altsaa ikke give regression
    # dér, hvor forankringen allerede virker.
    forventet = (db_climb["length_km"] or 0) * (db_climb.get("avg_gradient") or 0) * 10
    if sti_a and forventet:
        tolerance = max(150.0, forventet * 0.35)
        if abs((stigning_a or 0) - forventet) > tolerance:
            sti_b, stigning_b = spor(db_climb["km_from_start"] * scale)
            if sti_b and abs((stigning_b or 0) - forventet) < abs((stigning_a or 0) - forventet):
                return sti_b

    if not sti_a:
        raise ValueError("toppunkt uden for GPX-sporet eller for kort spor")
    return sti_a


# Stravas egen klatre-score: laengde i meter x gennemsnitsgradient i procent.
# Graenserne er Stravas offentligt dokumenterede kategoritrin.
_STRAVA_SCORE_TRIN = [(128000, 5), (64000, 4), (32000, 3), (16000, 2), (8000, 1)]


def estimated_strava_cat(db_climb: dict) -> int | None:
    """
    Anslaar Stravas climb_category ud fra klatrens egne maal.

    ASO_TO_STRAVA_CAT daekker kun loeb med et ASO-roadbook. Vuelta a Espana
    arrangeres af Unipublic, saa `category` er NULL for samtlige 58 stigninger
    i 2026-udgaven — og dermed blev den kategori-filtrerede soegevinkel aldrig
    brugt. Det er praecis den vinkel, modulets docstring udpeger som
    afgoerende: uden filter rangerer /segments/explore efter POPULARITET, og
    top-10 bliver korte fragmenter ("Sprint du Colombier", 0,53 km) i stedet
    for selve bjerget.

    Vi udleder derfor kategorien af laengde x gradient, som er internt
    konsistente felter (til forskel fra elevation_m, jf. expected_gain_m()).
    Anslaaet bruges KUN til at udvide soegningen — kandidaten skal stadig
    igennem den uaendrede geometriske verifikation, saa et forkert gaet kan
    koste et manglende match, aldrig et forkert et.
    """
    length, grade = db_climb.get("length_km"), db_climb.get("avg_gradient")
    if not length or not grade or grade <= 0:
        return None
    score = length * 1000 * grade
    for graense, cat in _STRAVA_SCORE_TRIN:
        if score >= graense:
            return cat
    return None


def search_vectors(climb_path: list[tuple[float, float]], db_climb: dict,
                    fallback_path: list[tuple[float, float]] | None) -> list[list[tuple]]:
    """
    Søgevinkler i to runder, billigst først.

    /segments/explore giver kun 10 segmenter pr. kald, rangeret efter
    popularitet, så ét opslag rammer ofte kun korte, populære fragmenter.
    Flere vinkler giver markant flere kandidater — men hver vinkel koster et
    læsekald, og Stravas daglige loft er 1000. Derfor eskaleres kun for de
    stigninger, hvor runde 1 ikke fandt noget.
    """
    cat = db_climb.get("category")
    first: list[tuple] = [(compute_bbox(climb_path), None)]
    strava_cat = ASO_TO_STRAVA_CAT.get(cat) or estimated_strava_cat(db_climb)
    if strava_cat:
        first.append((compute_bbox(climb_path), (max(0, strava_cat - 1), 5)))

    second: list[tuple] = []
    half = len(climb_path) // 2
    if half > 2:
        second.append((compute_bbox(climb_path[:half]), None))
        second.append((compute_bbox(climb_path[half:]), None))
    if fallback_path and len(fallback_path) > 2:
        second.append((compute_bbox(fallback_path), None))
    return [first, second]


class StravaSegmentSpaerret(RuntimeError):
    """Strava svarer, men nægter adgang til segmentdata."""


def fetch_segments(bounds: str, cat_range: tuple[int, int] | None) -> list[dict]:
    try:
        if cat_range:
            segments = strava_api.explore_segments_cat(bounds, min_cat=cat_range[0], max_cat=cat_range[1])
        else:
            segments = strava_api.explore_segments(bounds)
    except requests.HTTPError as e:
        # 401/404 fra segment-endpointet betyder ikke, at nøglen er forkert:
        # /athlete og /segments/starred svarer 200 med samme token (afprøvet
        # 2026-10-10). Strava har lukket segment-adgangen for appen, og så er
        # ingen stigning i noget løb matchbar. Uden den her skelnen kastede
        # agenten en rå traceback ved den første stigning i hver eneste
        # kørsel — en fejl, der altid står der, holder man op med at læse.
        kode = e.response.status_code if e.response is not None else None
        if kode in (401, 403, 404):
            raise StravaSegmentSpaerret(
                f"Strava svarede {kode} på segment-opslaget. Token og konto "
                "virker (/athlete svarer 200), så det er adgangen til "
                "SEGMENTDATA, der er lukket for denne app. Ingen stigning kan "
                "matches, før adgangen er genåbnet hos Strava."
            ) from e
        raise
    time.sleep(DELAY)
    return segments


def find_veloviewer_segment(race_slug: str, stage_number: int, stage_distance_km: float,
                             db_climb: dict) -> int | None:
    """
    Finder klatrens Strava-segment ved at sammenligne GEOMETRI: kandidaternes
    egen rutelinje (som /segments/explore selv leverer) mod klatrens spor i
    vores GPX. Ingen /segments/{id}-opslag undervejs — explore-svaret
    indeholder allerede distance, gradient, højdemeter og rutegeometri, og at
    droppe detaljekaldene sparer ~10 læsekald pr. kandidat.

    Returnerer segment-ID ved match, ellers None (aldrig gættet på —
    jf. CLAUDE.md §7).
    """
    points = stage_gpx(race_slug, stage_number)
    if not points:
        print(f"    [skip] ingen GPX-kilde for {race_slug} etape {stage_number}")
        return None
    if db_climb.get("km_from_start") is None or not db_climb.get("length_km"):
        print("    [skip] mangler km_from_start/length_km i DB")
        return None

    cum_dist = cpg.cumulative_distances_km(points)
    # Den gamle, scoring-baserede lokalisering bruges nu kun som ekstra
    # søgevinkel (og som nødplan, hvis top-forankringen ikke kan lade sig gøre).
    try:
        located = cpg.locate_climb_segment(
            points, cum_dist, stage_distance_km,
            db_climb["km_from_start"], db_climb["length_km"], db_climb,
        )
        fallback_path = [(p[0], p[1]) for p in located]
    except ValueError:
        fallback_path = None

    try:
        climb_path = climb_path_from_gpx(points, cum_dist, stage_distance_km, db_climb)
    except ValueError as e:
        if not fallback_path:
            print(f"    [skip] kunne ikke placere klatren i GPX-sporet ({e})")
            return None
        climb_path, fallback_path = fallback_path, None

    seen: dict[int, dict] = {}
    for round_vectors in search_vectors(climb_path, db_climb, fallback_path):
        for bounds, cat_range in round_vectors:
            for seg in fetch_segments(bounds, cat_range):
                seen[seg["id"]] = seg

        accepted: list[tuple[float, int, str, float]] = []
        for seg in seen.values():
            ok, reason = strava_api.segment_matches_climb_geo(seg, db_climb, climb_path)
            if not ok:
                continue
            on_route, coverage = strava_api.geo_overlap(
                strava_api.decode_polyline(seg["points"]), climb_path)
            len_gap = abs(1 - ((seg.get("distance") or 0) / 1000) / db_climb["length_km"])
            accepted.append((on_route * coverage, seg["id"], reason, len_gap))

        if accepted:
            # Bedst geometrisk sammenfald først; ved uafgjort vinder den
            # kandidat, hvis længde ligger tættest på klatrens egen.
            accepted.sort(key=lambda a: (-a[0], a[3]))
            _, segment_id, reason, _ = accepted[0]
            extra = f", {len(accepted) - 1} andre bestod også" if len(accepted) > 1 else ""
            print(f"    [match] segment {segment_id} godkendt ({reason}{extra})")
            return segment_id

    # Rapportér den taettest-paa kandidat. Et bart "ingen bestod" siger intet om,
    # OM det rigtige segment slet ikke blev fundet (daekning lav paa alle), eller
    # om det blev fundet og kasseret paa en tolerance — to helt forskellige
    # problemer, der kraever helt forskellige loesninger.
    if seen:
        near = []
        for seg in seen.values():
            if not seg.get("points"):
                continue
            on_route, coverage = strava_api.geo_overlap(
                strava_api.decode_polyline(seg["points"]), climb_path)
            _, reason = strava_api.segment_matches_climb_geo(seg, db_climb, climb_path)
            near.append((coverage, on_route, seg, reason))
        if near:
            near.sort(key=lambda n: -n[0])
            cov, onr, seg, reason = near[0]
            print(f"    [intet match] {len(seen)} kandidater. Bedste: {seg['id']} "
                  f"\"{(seg.get('name') or '')[:40]}\" {(seg.get('distance') or 0)/1000:.2f} km "
                  f"@ {seg.get('avg_grade')}% — rute {onr:.0%}, daekning {cov:.0%} → {reason}")
            return None
    print(f"    [intet match] {len(seen)} kandidater, ingen bestod verifikationen")
    return None


# ── Orkestrering ────────────────────────────────────────────────────────────────

def process_stage(race_slug: str, stage: dict, overwrite: bool, write_db: bool) -> None:
    climbs = get_climbs_for_stage(stage["id"], only_missing=not overwrite)
    if not climbs:
        print(f"  Etape {stage['stage_number']}: ingen stigninger at behandle.")
        return

    for climb in climbs:
        if strava_api.daily_limit_reached:
            raise DailyLimitReached()
        print(f"  → {climb['name']} (km {climb.get('km_from_start')}, {climb.get('length_km')} km)")
        match_id = find_veloviewer_segment(race_slug, stage["stage_number"], stage["distance_km"], climb)
        if strava_api.daily_limit_reached:
            raise DailyLimitReached()
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

    try:
        if args.all:
            for slug in cpg.CYCLINGSTAGE_GPX_PAGES:
                process_race(slug, args.stage, args.overwrite, args.write_db)
        else:
            process_race(args.race, args.stage, args.overwrite, args.write_db)
    except StravaSegmentSpaerret as e:
        print(f"\n=== STOPPET: {e} ===")
        print("Stigningerne får i stedet vores egen profil tegnet ud fra "
              "GPX-ruten (trin 2 i jobbet 'Stigningsprofiler').")
        sys.exit(1)
    except DailyLimitReached:
        print("\n=== STOPPET: Stravas daglige læse-loft (1000 kald) er brugt op. ===")
        print("Loftet nulstilles ved midnat UTC. Kør kommandoen igen derefter —")
        print("allerede matchede stigninger springes over, medmindre --overwrite bruges.")
        sys.exit(2)
