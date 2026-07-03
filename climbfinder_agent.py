"""
climbfinder_agent.py
Finder ClimbFinder-profilbilleder for stigninger og gemmer profile_image_url.

Verifikationslogik:
  1. Søger ClimbFinder på klatringens navn (multiple søgetermer)
  2. Henter CF-metrics (length, finishElevation, gradient) og verificerer
     mod vores DB-data. Forkert match afvises automatisk.
  3. Fallback via GPX: beregner summit-koordinater fra route_points
     og reverse-geokoder (Nominatim) → ny søgeterm

Kør:
  python climbfinder_agent.py --race criterium-du-dauphine-2026
  python climbfinder_agent.py --race tour-de-france-2026 --stage 15
  python climbfinder_agent.py --all          # alle løb med manglende profiler
  python climbfinder_agent.py --race giro-d-italia-2026 --overwrite
  python climbfinder_agent.py --all --overwrite   # kontroltjek: re-verificér ALT
"""

import os
import re
import sys
import io
import math
import time
import json
import argparse
import requests
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

CF_EMAIL    = os.getenv("CF_EMAIL", "")
CF_PASSWORD = os.getenv("CF_PASSWORD", "")
CF_BASE     = "https://uphill.climbfinder.com/v2"

DELAY = 1.2

PREFERRED_COUNTRIES = {"IT", "FR", "ES", "CH", "AT", "BE"}

CLIMB_PREFIXES = [
    "Col de la ", "Col du ", "Col de l'", "Col de ",
    "Col des ", "Côte de la ", "Côte du ", "Côte de l'", "Côte de ",
    "Côte des ", "Cote de la ", "Cote du ", "Cote de ",
    "Montée de ", "Montée du ", "Montée de la ",
    "Monte ", "Muro di ", "Passo del ", "Passo ",
    "Puerto de ", "Puerto del ",
    "Lacets du ", "Lacets de ",
    "Coll de ", "Coll del ",
    "Le ", "La ", "Les ",
    "Barrage de ", "Plan ",
]

# Override pr. klatringsnavn (None = skip)
SEARCH_OVERRIDES: dict[str, str | None] = {
    "Pila (Gressan)":                   "Pila Gressan",
    "Lacets du Grand Colombier":        "Grand Colombier",
    "Plateau de Solaison (Brison)":     "Plateau de Solaison",
    "Andalo-Lever":                     "Andalo",
    "COLLE GIOVO":                      "Colle Giovo",
    "Muro di Ca' del Poggio":           "Ca del Poggio",
    "Puy Mary - Pas de Peyrol":         "Puy Mary",
    "Le Salève - Col de la Croisette":  "Le Saleve",
    "Gavarnie-Gèdre":                   None,
    "Les Angles":                       None,
    "Orcières-Merlette":                None,
    "Borovets Pass":                    None,
    "Muro di Via Reputolo":             None,
    "Colla dei Scioli":                 None,
    "Cozzo Tunno":                      None,
    "Cote de Lerigneux":                None,
    "Cote de la Roche en Forez":        None,
    "Puy Boubou":                       None,
    "Tenero-Contra":                    None,
    "Metersrüte":                       None,
    "Col de Quaix-en-Charteuse":        None,
    "Cote de Rousset":                  None,
    # Korte circuit-stigninger og lokale stigninger — ikke på CF
    "Cote de Montjuic":                 None,
    "Côte de l'Estadi Olímpic":         None,
    "Mont Bessou":                      None,
    "Côte de Miel":                     None,
    "Côte de Pailherols":               None,
    "Barrage de Grand'Maison":          None,
    "Côte de Larringes":                None,
    # CF har kun lange versioner (CF-mål starter lavere end vores DB-segment)
    "Verrogne":                         None,
    "Leontica":                         None,
    "Schwägalp-Passhöhe":              None,
    "Col de la Croix":                  None,
    # CF giver geografisk forkert match (forkert land)
    "Saint-Barthélémy":                 None,
    "Torre":                            None,
    "Andalo-Lever":                     None,
}


# ── ClimbFinder session ────────────────────────────────────────────────────────

def cf_login() -> requests.Session | None:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    })
    session.get("https://climbfinder.com/en/login")
    time.sleep(0.5)
    res = session.post(
        "https://climbfinder.com/en/form/login",
        data={"email": CF_EMAIL, "password": CF_PASSWORD,
              "referer": "https://climbfinder.com/en", "route": "0"},
        headers={"Referer": "https://climbfinder.com/en/login"},
        allow_redirects=True,
    )
    if "remember" not in session.cookies and ("login" in res.url or not res.ok):
        print(f"  Login fejlede — status {res.status_code}")
        return None
    for name in ("remember", "cisession"):
        vals = [c.value for c in session.cookies if c.name == name and c.domain == "climbfinder.com"]
        if vals:
            session.cookies.set(name, vals[0], domain="uphill.climbfinder.com")
    print("  Logget ind")
    return session


def cf_search(session: requests.Session, term: str) -> list[dict]:
    """Returnerer liste af CF-kandidater for søgetermen."""
    res = session.get(
        f"{CF_BASE}/search",
        params={"term": term, "language": "en"},
        headers={"Accept": "application/json", "Referer": "https://climbfinder.com/en",
                 "Origin": "https://climbfinder.com"},
    )
    if not res.ok:
        return []
    return res.json().get("data", {}).get("climbs", [])


def cf_get_detail(session: requests.Session, climb_id: int) -> dict | None:
    """Henter ClimbFinder-detaljer inkl. metrics og profilbillede."""
    res = session.get(
        f"{CF_BASE}/climbs/{climb_id}",
        headers={"Accept": "application/json", "Referer": "https://climbfinder.com/en",
                 "Origin": "https://climbfinder.com"},
    )
    if not res.ok:
        return None
    d = res.json().get("data", {})
    return {
        "id":              d.get("id"),
        "name":            d.get("name"),
        "slug":            d.get("slug"),
        "profile":         d.get("profile"),
        "length_km":       (d.get("length") or 0) / 1000,
        "finish_elevation": d.get("finishElevation"),
        "gradient_pct":    (d.get("gradient") or 0) * 100,
        "country":         d.get("countryIso"),
    }


# ── Metrisk verifikation ───────────────────────────────────────────────────────

def metrics_ok(cf: dict, db: dict) -> tuple[bool, str]:
    """
    Sammenligner CF-metrics med vores DB-data.
    Returnerer (godkendt, forklaring).
    Springer over tjek hvis vi ikke har den pågældende DB-værdi.

    Tolerancerne var tidligere alt for løse (længde 0.5-2.0x, højde ±300-450m,
    hældning ±4%) — det tillod reelt forkerte bjerge at blive godkendt, hvis de
    blot lignede lidt (bekræftet bug: TdF 2026 "Côte de Begues" (6.3 km, DB) blev
    matchet til ClimbFinders "Côte de Benagues" (3.2 km) — en helt anden bakke i
    Frankrig, ikke Barcelona — fordi ratio 0.51 lige akkurat lå inden for 0.5-2.0.
    Strammet 2026-07-03 til realistiske toleranceer for at være samme bjerg.
    """
    reasons = []

    # Længdetjek (vigtigst — afviger ikke mere end ±33%)
    db_len = db.get("length_km")
    cf_len = cf.get("length_km", 0)
    len_ratio = None
    if db_len and cf_len and cf_len > 0:
        len_ratio = cf_len / db_len
        if len_ratio < 0.75 or len_ratio > 1.33:
            return False, f"længde {cf_len:.1f} km vs DB {db_len:.1f} km (ratio {len_ratio:.2f})"
        reasons.append(f"len {cf_len:.1f}≈{db_len:.1f}km")

    # Højdemeter-tjek. db_elev er klatrede højdemeter (gain), IKKE tophøjde —
    # cf['finish_elevation'] er derimod CF's tophøjde over havet (summit altitude),
    # en helt anden fysisk størrelse (se STG-007). De to kan ikke sammenlignes
    # direkte. Beregner i stedet CF's egen implicerede gain fra dens length+
    # gradient (samme formel som DB'ens elevation_m), og sammenligner den mod
    # db_elev — apples-to-apples, ligesom within_tolerance() i
    # climb_profile_generator.py.
    db_elev = db.get("elevation_m")
    cf_grad_for_gain = cf.get("gradient_pct", 0)
    cf_gain = cf_len * cf_grad_for_gain * 10 if cf_len and cf_grad_for_gain else None
    if db_elev and cf_gain:
        diff = abs(cf_gain - db_elev)
        max_diff = max(150, db_elev * 0.35)
        if diff > max_diff:
            return False, f"beregnet højdemeter {cf_gain:.0f}m vs DB {db_elev}m (diff {diff:.0f}m)"
        reasons.append(f"gain {cf_gain:.0f}≈{db_elev}m")

    # Hældiningstjek (maks 1.5% forskel)
    db_grad = db.get("avg_gradient")
    cf_grad = cf.get("gradient_pct", 0)
    if db_grad and cf_grad:
        diff = abs(cf_grad - db_grad)
        if diff > 1.5:
            return False, f"hældning {cf_grad:.1f}% vs DB {db_grad:.1f}% (diff {diff:.1f}%)"
        reasons.append(f"grad {cf_grad:.1f}≈{db_grad:.1f}%")

    return True, " | ".join(reasons) if reasons else "ingen metrics at tjekke"


# ── GPS-hjælpere ──────────────────────────────────────────────────────────────

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def summit_coords(route_points: list, distance_km: float,
                  km_from_start: float, length_km: float) -> tuple[float, float] | None:
    """Beregner GPS-koordinater for stigningens top."""
    if not route_points or not distance_km:
        return None
    summit_km = km_from_start + length_km
    idx = round(summit_km / distance_km * (len(route_points) - 1))
    idx = max(0, min(idx, len(route_points) - 1))
    pt = route_points[idx]
    return (pt[0], pt[1])  # [lat, lon]


def nominatim_name(lat: float, lon: float) -> str | None:
    """Reverse-geokoder koordinater via Nominatim og returnerer vejnavn."""
    try:
        res = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 15},
            headers={"User-Agent": "Klassementet/1.0 (jonasb408@gmail.com)"},
            timeout=10,
        )
        if not res.ok:
            return None
        data = res.json()
        addr = data.get("address", {})
        # Prøv road, hamlet, village, town, county i prioriteret rækkefølge
        for key in ("road", "hamlet", "village", "suburb", "town", "county"):
            val = addr.get(key)
            if val:
                return val
        return data.get("display_name", "").split(",")[0]
    except Exception:
        return None


# ── Søgetermsgenerering ────────────────────────────────────────────────────────

def make_search_terms(climb_name: str) -> list[str]:
    cleaned = re.sub(r"\s*\([^)]*\)", "", climb_name).strip()
    terms = [cleaned]
    for prefix in CLIMB_PREFIXES:
        if cleaned.lower().startswith(prefix.lower()):
            without = cleaned[len(prefix):].strip()
            if without and without not in terms:
                terms.append(without)
            break
    words = cleaned.split()
    if len(words) >= 3:
        terms.append(" ".join(words[1:]))
    if len(words) >= 2:
        terms.append(" ".join(words[-2:]))
    if len(words) >= 2:
        last = words[-1]
        if len(last) > 4 and last not in terms:
            terms.append(last)
    seen, unique = set(), []
    for t in terms:
        if t and t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


# ── Hoved-søgefunktion med verifikation ──────────────────────────────────────

def find_verified_profile(
    session: requests.Session,
    climb_name: str,
    db_climb: dict,
    summit_lat_lon: tuple[float, float] | None = None,
) -> str | None:
    """
    Søger ClimbFinder og verificerer matchet via metrics (og evt. koordinater).
    Returnerer profile image URL eller None.
    """
    # Eksplicit override
    if climb_name in SEARCH_OVERRIDES:
        override = SEARCH_OVERRIDES[climb_name]
        if override is None:
            print("    → Skip (override)")
            return None
        search_terms = [override]
    else:
        search_terms = make_search_terms(climb_name)

    # Tilføj GPS-baseret term som fallback hvis vi har koordinater
    if summit_lat_lon:
        search_terms.append("__GPS__")  # Signal til at bruge GPS-fallback

    for term in search_terms:
        if term == "__GPS__":
            # GPS-fallback: reverse-geokod summit og søg på vejnavn
            if not summit_lat_lon:
                continue
            lat, lon = summit_lat_lon
            osm_name = nominatim_name(lat, lon)
            time.sleep(1)  # Nominatim rate limit
            if not osm_name:
                continue
            print(f"    GPS-fallback → Nominatim: '{osm_name}'")
            term = osm_name
        else:
            print(f"    Søger: '{term}'")

        candidates = cf_search(session, term)
        time.sleep(DELAY)

        if not candidates:
            continue

        # Foretræk kendte lande; ellers alle
        preferred = [c for c in candidates if c.get("countryIso") in PREFERRED_COUNTRIES]
        to_try = preferred if preferred else candidates[:3]

        for candidate in to_try[:3]:
            detail = cf_get_detail(session, candidate["id"])
            time.sleep(DELAY)
            if not detail:
                continue

            ok, reason = metrics_ok(detail, db_climb)

            if ok:
                print(f"    ✓ Match: {detail['name']} ({detail['country']}) — {reason}")
                if not detail.get("profile"):
                    print("    → Ingen profilbillede på CF")
                    continue
                return detail["profile"]
            else:
                print(f"    ✗ Afvist: {detail['name']} — {reason}")

    print("    → Ingen verificeret match")
    return None


# ── Supabase helpers ───────────────────────────────────────────────────────────

def sb_get(table: str, query: str) -> list[dict]:
    res = requests.get(f"{SUPABASE_URL}/rest/v1/{table}{query}", headers=SB_HEADERS)
    return res.json() if res.ok else []


def get_race(race_slug: str) -> dict | None:
    rows = sb_get("races", f"?slug=eq.{race_slug}&select=id,name&limit=1")
    return rows[0] if rows else None


def get_all_races_with_missing() -> list[dict]:
    climbs = sb_get("stage_climbs", "?profile_image_url=is.null&select=stage_id")
    if not climbs:
        return []
    stage_ids = list({c["stage_id"] for c in climbs})
    sid_list = ",".join(f'"{s}"' for s in stage_ids)
    stages = sb_get("stages", f"?id=in.({sid_list})&select=race_id")
    race_ids = list({s["race_id"] for s in stages})
    rid_list = ",".join(f'"{r}"' for r in race_ids)
    return sb_get("races", f"?id=in.({rid_list})&select=id,slug,name")


def get_all_races_with_climbs() -> list[dict]:
    """Alle løb med mindst én stage_climbs-række — bruges til fuld re-verifikation
    (--all --overwrite), i modsætning til get_all_races_with_missing(), som kun
    finder løb med huller og derfor springer fuldt dækkede løb helt over."""
    climbs = sb_get("stage_climbs", "?select=stage_id")
    if not climbs:
        return []
    stage_ids = list({c["stage_id"] for c in climbs})
    sid_list = ",".join(f'"{s}"' for s in stage_ids)
    stages = sb_get("stages", f"?id=in.({sid_list})&select=race_id")
    race_ids = list({s["race_id"] for s in stages})
    rid_list = ",".join(f'"{r}"' for r in race_ids)
    return sb_get("races", f"?id=in.({rid_list})&select=id,slug,name")


def get_stages(race_id: str, stage_number: int | None) -> list[dict]:
    url = (
        f"?race_id=eq.{race_id}"
        f"&select=id,stage_number,finish_location,stage_type,distance_km,route_points"
        f"&order=stage_number.asc"
    )
    if stage_number:
        url += f"&stage_number=eq.{stage_number}"
    return sb_get("stages", url)


def get_climbs_for_stage(stage_id: str, only_missing: bool) -> list[dict]:
    url = (
        f"?stage_id=eq.{stage_id}"
        f"&select=id,name,km_from_start,length_km,elevation_m,avg_gradient,profile_image_url"
        f"&order=km_from_start.asc"
    )
    rows = sb_get("stage_climbs", url)
    return [r for r in rows if not r.get("profile_image_url")] if only_missing else rows


def update_climb_profile(climb_id: str, profile_url: str | None) -> bool:
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/stage_climbs?id=eq.{climb_id}",
        json={"profile_image_url": profile_url},
        headers=SB_HEADERS,
    )
    return res.status_code in (200, 204)


def clear_stale_override_images(stage_id: str) -> int:
    """
    Rydder profile_image_url for stigninger, hvis navnet nu står i SEARCH_OVERRIDES
    som None ("kan ikke verificeres"), men stadig har et billede liggende fra en
    tidligere kørsel (fx før overriden blev tilføjet, eller før metrics-verifikation
    fandtes). Uden dette bliver et kendt-forkert match aldrig rettet, fordi
    get_climbs_for_stage(only_missing=True) springer klatringer med et sat
    profile_image_url over — og --overwrite kræves normalt ikke for hver kørsel.
    Kører derfor altid, uafhængigt af --overwrite.
    """
    climbs = get_climbs_for_stage(stage_id, only_missing=False)
    cleared = 0
    for climb in climbs:
        name = (climb.get("name") or "").strip()
        has_override_none = name in SEARCH_OVERRIDES and SEARCH_OVERRIDES[name] is None
        if has_override_none and climb.get("profile_image_url"):
            if update_climb_profile(climb["id"], None):
                print(f"  ⚠ Ryddet forældet/uverificeret match: {name} "
                      f"({climb.get('profile_image_url')})")
                cleared += 1
            else:
                print(f"  ✗ Kunne ikke rydde {name} (DB-fejl)")
    return cleared


# ── Hovedpipeline ─────────────────────────────────────────────────────────────

def process_race(race_slug: str, stage_number: int | None, overwrite: bool) -> int:
    race = get_race(race_slug)
    if not race:
        print(f"Løb ikke fundet: {race_slug}")
        return 0

    stages = get_stages(race["id"], stage_number)
    print(f"\nclimbfinder_agent.py — {race['name']}")
    print(f"Fandt {len(stages)} etaper (med metrics-verifikation + GPS-fallback)")

    # Ryd forældede/uverificerede matches FØR login — kræver ikke CF-session,
    # og skal ske uanset om login lykkes eller om --overwrite er sat.
    total_cleared = 0
    for stage in stages:
        total_cleared += clear_stale_override_images(stage["id"])
    if total_cleared:
        print(f"Ryddede {total_cleared} forældet(e)/uverificeret(e) match(es) (jf. SEARCH_OVERRIDES)\n")

    print("Logger ind på ClimbFinder...")
    session = cf_login()
    if not session:
        return 0
    print()

    updated, skipped = 0, 0
    name_cache: dict[str, str | None] = {}

    for stage in stages:
        n           = stage["stage_number"]
        s_id        = stage["id"]
        finish      = stage.get("finish_location", "")
        distance_km = float(stage.get("distance_km") or 0)
        route_pts   = stage.get("route_points")  # [[lat,lon], ...]

        climbs = get_climbs_for_stage(s_id, only_missing=not overwrite)
        if not climbs:
            continue

        print(f"[E{n}] {finish} — {len(climbs)} stigning(er)" +
              (f" (GPX: {len(route_pts)} punkter)" if route_pts else " (ingen GPX)"))

        for climb in climbs:
            climb_name = (climb.get("name") or "").strip()
            if not climb_name:
                continue

            # Permanent override=None betyder "kendt IKKE på ClimbFinder" —
            # denne agent skal aldrig røre et eksisterende billede for sådan
            # en stigning (det kan stamme fra climb_profile_generator.py's
            # GPX-fallback, som findes netop fordi CF ikke har klatringen).
            # Uden dette ryddede --overwrite alle fallback-billeder hver
            # gang den kørte, fordi find_verified_profile() altid returnerer
            # None for disse — se STG-007-opfølgning.
            if climb_name in SEARCH_OVERRIDES and SEARCH_OVERRIDES[climb_name] is None:
                print(f"  • {climb_name}: permanent override — springer helt over "
                      f"(rører ikke evt. eksisterende billede)")
                continue

            print(f"  • {climb_name} "
                  f"({climb.get('length_km') or '?'}km, "
                  f"{climb.get('avg_gradient') or '?'}%, "
                  f"{climb.get('elevation_m') or '?'}m)")

            # Beregn summit-koordinater fra GPX hvis muligt
            s_lat_lon = None
            if route_pts and distance_km and climb.get("km_from_start") is not None and climb.get("length_km"):
                s_lat_lon = summit_coords(
                    route_pts, distance_km,
                    float(climb["km_from_start"]), float(climb["length_km"])
                )
                if s_lat_lon:
                    print(f"    GPS summit: {s_lat_lon[0]:.4f}, {s_lat_lon[1]:.4f}")

            # Brug cache (men kun hvis metrics-match var verificeret)
            if climb_name in name_cache:
                profile_url = name_cache[climb_name]
                if profile_url:
                    print(f"    → (fra cache)")
            else:
                profile_url = find_verified_profile(session, climb_name, climb, s_lat_lon)
                name_cache[climb_name] = profile_url

            if not profile_url:
                skipped += 1
                # Ryd en tidligere (nu forkastet) match — ellers overlever et
                # forkert billede stille og roligt, blot fordi ingen ny kandidat
                # kunne verificeres denne kørsel (samme fejlmønster som den
                # oprindelige stale-override-bug, men for det generelle tilfælde).
                if climb.get("profile_image_url"):
                    update_climb_profile(climb["id"], None)
                    print("    → Ryddet tidligere match (bestod ikke verifikation nu)")
                continue

            if update_climb_profile(climb["id"], profile_url):
                print(f"    → Gemt ✓")
                updated += 1
            else:
                print("    → DB-fejl")
        print()

    print(f"Færdig: {updated} opdateret | {skipped} ikke fundet/afvist")
    return updated


def run_all(overwrite: bool) -> None:
    if overwrite:
        # --all --overwrite = fuld re-verifikation (kontroltjek): tjek ALLE
        # eksisterende matches mod de nuværende (strammede) tolerancer, ikke
        # kun løb med huller — ellers springes fuldt dækkede løb helt over.
        races = get_all_races_with_climbs()
        if not races:
            print("Ingen løb med stigninger fundet.")
            return
        print(f"Fuld re-verifikation — løb med stigninger: {len(races)}")
    else:
        races = get_all_races_with_missing()
        if not races:
            print("Ingen løb med manglende ClimbFinder-profiler.")
            return
        print(f"Løb med manglende profiler: {len(races)}")
    total = 0
    for race in races:
        total += process_race(race["slug"], stage_number=None, overwrite=overwrite)
    print(f"\nAlt færdig: {total} profiler tilføjet totalt")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--race", help="Kør for ét løb (slug)")
    group.add_argument("--all",  action="store_true", help="Alle løb med manglende profiler")
    parser.add_argument("--stage",     type=int,          help="Kun én etape")
    parser.add_argument("--overwrite", action="store_true", help="Overskiv eksisterende profiler")
    args = parser.parse_args()

    if args.all:
        run_all(args.overwrite)
    else:
        process_race(args.race, args.stage, args.overwrite)
