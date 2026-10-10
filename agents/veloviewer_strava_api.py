"""
veloviewer_strava_api.py
Hjælpefunktioner til Stravas officielle API — både til at FINDE
segment-kandidater (explore_segments, bounding-box-baseret) og til at
VERIFICERE dem mod vores DB-data (get_segment + segment_matches_climb).
Se veloviewer_agent.py for orkestreringen.

VIGTIGT (jf. docs/superpowers/specs/2026-07-07-veloviewer-climb-profiles-design.md
og Stravas API Agreement, https://www.strava.com/legal/api):
Strava Data hentet her (segmentnavn, distance, hældning, højdemeter) må
IKKE vises eller gemmes noget sted, der er synligt for andre end
kontoejeren selv — hverken i DB, frontend eller delte logs. Funktionerne
her returnerer derfor kun et bool-match + diagnosticeringstal til brug i
hukommelsen; kald-stedet må ikke persistere de rå Strava-felter.

Kør som selvstændig test (kalder kun det offentlige API, ingen browser):
    python agents/veloviewer_strava_api.py --test-segment 4286076
"""

import os
import re
import sys
import io
import time
import argparse
import unicodedata

import requests
from dotenv import load_dotenv

load_dotenv()

# Ord der ikke i sig selv identificerer et bjerg/en stigning — bruges til at
# udtrække de "betydende" ord i et klatrenavn (se _significant_tokens()).
_STOPWORDS = {
    "col", "de", "du", "des", "la", "le", "les", "d", "l", "cote", "côte",
    "montee", "montée", "monte", "muro", "di", "del", "della", "plan",
    "barrage", "lacets", "coll", "passo", "puerto", "par",
}

STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID", "")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET", "")
STRAVA_REFRESH_TOKEN = os.getenv("STRAVA_REFRESH_TOKEN", "")

TOKEN_URL = "https://www.strava.com/oauth/token"
API_BASE = "https://www.strava.com/api/v3"

_access_token_cache: dict = {"token": None, "expires_at": 0}

# Stravas rate limit nulstiller i rullende 15-minutters vinduer (200 kald/15 min,
# 2000/dag for "overall"; det separate, lavere "read"-loft — som /segments/explore
# og /segments/{id} begge trækker på — er 100 kald/15 min, 1000/dag). Ved 429
# venter vi vinduet ud og prøver automatisk igen, i stedet for at springe
# kandidaten/boksen over — så en lang kørsel (fx alle TdF-etaper) selv finder
# tempoet, den kan holde, uden at nogen skal overvåge den undervejs.
RATE_LIMIT_WAIT_SECONDS = 15 * 60
MAX_RATE_LIMIT_RETRIES = 6  # op til 1,5 time ventetid i alt, før vi giver op

# STG-021-fund (2026-07-08): Stravas 429 dækker over TO forskellige lofter, som
# begge udløser samme statuskode: det rullende 15-minutters vindue (kan altid
# ventes ud) OG det daglige loft (1000 read-kald/dag), som IKKE nulstiller
# ved at vente 15 minutter — det nulstiller først ved midnat UTC. Uden dette
# tjek ville _get_with_retry blindt bruge alle MAX_RATE_LIMIT_RETRIES (op til
# 1,5 time) på HVERT efterfølgende kald resten af dagen, når det daglige loft
# er ramt — spild af tid uden nogensinde at kunne lykkes. Vi læser derfor
# X-ReadRateLimit-Usage/-Limit-headeren (format "15min,daglig") og stopper med
# det samme, hvis det daglige antal er nået.
def _daily_limit_exhausted(res: requests.Response) -> bool:
    usage = res.headers.get("X-ReadRateLimit-Usage") or res.headers.get("x-readratelimit-usage")
    limit = res.headers.get("X-ReadRateLimit-Limit") or res.headers.get("x-readratelimit-limit")
    if not usage or not limit:
        return False
    try:
        daily_usage = int(usage.split(",")[1])
        daily_limit = int(limit.split(",")[1])
    except (IndexError, ValueError):
        return False
    return daily_usage >= daily_limit


# Saettes naar Stravas DAGLIGE loft er naaet. Kaldere skal tjekke den og
# afbryde koerslen — ellers ser tomme svar ud som "ingen segmenter fundet",
# og en batch-koersel ville rapportere falske negativer resten af dagen.
daily_limit_reached = False


def _get_with_retry(url: str, params: dict) -> requests.Response | None:
    global daily_limit_reached
    token = get_access_token()
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        res = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=15)
        if res.status_code != 429:
            return res
        if _daily_limit_exhausted(res):
            daily_limit_reached = True
            print("    [rate limit] Stravas DAGLIGE read-loft (1000 kald/dag) er nået — "
                  "nulstiller først ved midnat UTC, så vi venter ikke vinduet ud. "
                  "Giver op for resten af kørslen, prøv igen efter midnat UTC.")
            return res
        if attempt == MAX_RATE_LIMIT_RETRIES:
            print(f"    [rate limit] Stadig ramt efter {attempt} forsøg — giver op for dette kald")
            return res
        print(f"    [rate limit] Stravas API-grænse ramt — venter {RATE_LIMIT_WAIT_SECONDS // 60} min og prøver igen...")
        time.sleep(RATE_LIMIT_WAIT_SECONDS)
        token = get_access_token()
    return None


def get_access_token() -> str:
    """
    Henter et gyldigt access token via refresh-token-flowet. Cacher i
    hukommelsen for processens levetid (Stravas access tokens holder i
    timevis, så vi undgår at génere et token pr. API-kald).
    """
    now = time.time()
    if _access_token_cache["token"] and _access_token_cache["expires_at"] > now + 60:
        return _access_token_cache["token"]

    if not (STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET and STRAVA_REFRESH_TOKEN):
        raise RuntimeError(
            "STRAVA_CLIENT_ID/STRAVA_CLIENT_SECRET/STRAVA_REFRESH_TOKEN mangler i .env"
        )

    res = requests.post(TOKEN_URL, data={
        "client_id": STRAVA_CLIENT_ID,
        "client_secret": STRAVA_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": STRAVA_REFRESH_TOKEN,
    }, timeout=15)
    res.raise_for_status()
    data = res.json()

    _access_token_cache["token"] = data["access_token"]
    _access_token_cache["expires_at"] = data.get("expires_at", now + 3600)
    return data["access_token"]


def get_segment(segment_id: int) -> dict | None:
    """
    Henter et segments offentlige metadata (distance/hældning/højdemeter)
    fra Stravas officielle API. Bruges KUN til intern tolerance-sammenligning
    — kald-stedet må ikke persistere eller vise disse felter, jf. modulets
    docstring.
    """
    res = _get_with_retry(f"{API_BASE}/segments/{segment_id}", {})
    if res is None:
        return None
    if res.status_code == 404:
        return None
    if res.status_code == 429:
        return None  # opgav efter MAX_RATE_LIMIT_RETRIES forsøg — behandles som "intet fundet"
    res.raise_for_status()
    d = res.json()
    return {
        "name": d.get("name"),
        "distance_km": (d.get("distance") or 0) / 1000,
        "average_grade": d.get("average_grade"),
        "elevation_high": d.get("elevation_high"),
        "elevation_low": d.get("elevation_low"),
    }


def explore_segments_cat(bounds: str, min_cat: int | None = None, max_cat: int | None = None,
                          activity_type: str = "riding") -> list[dict]:
    """
    Som explore_segments(), men med Stravas klatrekategori-filter.

    Uden filter rangerer /segments/explore efter popularitet, og i bjergrige
    omraader er top-10 typisk korte, populaere fragmenter ("Sprint Tourmalet",
    300 m) frem for selve bjerget — bekraeftet 2026-07-22: en ufiltreret
    soegning i Tourmalet-boksen indeholdt IKKE en eneste HC-stigning, mens
    min_cat=4 straks gav de rigtige. Vi kender nu klatrens officielle
    ASO-kategori (aso_roadbook_agent.py), saa filteret kan bruges maalrettet.
    """
    params = {"bounds": bounds, "activity_type": activity_type}
    if min_cat is not None:
        params["min_cat"] = min_cat
    if max_cat is not None:
        params["max_cat"] = max_cat
    res = _get_with_retry(f"{API_BASE}/segments/explore", params)
    if res is None or res.status_code != 200:
        return []
    return res.json().get("segments", [])


# ── Geometrisk matchning ─────────────────────────────────────────────────────
#
# /segments/explore returnerer selv segmentets fulde rute som encoded polyline
# ("points") sammen med distance, gradient, hoejdemeter og kategori. Vi kan
# derfor bade finde OG verificere en kandidat uden et eneste /segments/{id}-
# opslag — det sparer ~10 laesekald pr. kandidat og er det, der overhovedet
# goer det muligt at scanne hele databasen inden for Stravas daglige loft.
#
# Polylinjen bruges KUN i hukommelsen til denne sammenligning. Den maa aldrig
# persisteres eller vises, jf. modulets docstring og Stravas API Agreement.

_CELL_DEG = 0.0006          # gittercelle ~66 m i breddegrad


def decode_polyline(encoded: str) -> list[tuple[float, float]]:
    """Google encoded polyline -> [(lat, lon), ...]."""
    points: list[tuple[float, float]] = []
    lat = lon = index = 0
    while index < len(encoded):
        for is_lat in (True, False):
            shift = result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else (result >> 1)
            if is_lat:
                lat += delta
            else:
                lon += delta
        points.append((lat / 1e5, lon / 1e5))
    return points


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _densify(points: list[tuple[float, float]], step_m: int = 25) -> list[tuple[float, float]]:
    """
    Indsaetter mellempunkter, saa der aldrig er mere end step_m mellem to punkter.

    Uden dette maales naerhed kun mod de raa polylinje-hjoerner, som paa en lang
    stigning kan ligge hundredvis af meter fra hinanden — et korrekt segment
    ville da fejlagtigt se ud til kun at daekke halvdelen af klatren.
    """
    if len(points) < 2:
        return list(points)
    out = [points[0]]
    for a, b in zip(points, points[1:]):
        gap_m = _haversine_km(a[0], a[1], b[0], b[1]) * 1000
        steps = int(gap_m // step_m)
        for i in range(1, steps + 1):
            f = i / (steps + 1)
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
        out.append(b)
    return out


def _cells(points: list[tuple[float, float]], lat0: float) -> set:
    import math
    lon_scale = max(math.cos(math.radians(lat0)), 0.2)
    return {(int(p[0] / _CELL_DEG), int(p[1] * lon_scale / _CELL_DEG)) for p in points}


def _fraction_near(points: list[tuple[float, float]], cellset: set, lat0: float) -> float:
    import math
    lon_scale = max(math.cos(math.radians(lat0)), 0.2)
    hits = 0
    for p in points:
        cy, cx = int(p[0] / _CELL_DEG), int(p[1] * lon_scale / _CELL_DEG)
        if any((cy + dy, cx + dx) in cellset for dy in (-1, 0, 1) for dx in (-1, 0, 1)):
            hits += 1
    return hits / len(points) if points else 0.0


def geo_overlap(segment_points: list[tuple[float, float]],
                climb_points: list[tuple[float, float]]) -> tuple[float, float]:
    """
    Returnerer (paa_rute, daekning):
      paa_rute  = hvor stor del af SEGMENTET der foelger klatrens rute
                  (lav vaerdi = segmentet stikker af ad en anden vej)
      daekning  = hvor stor del af KLATREN segmentet daekker
                  (lav vaerdi = segmentet er kun et fragment af stigningen)
    """
    seg = _densify(segment_points)
    climb = _densify(climb_points)
    if not seg or not climb:
        return 0.0, 0.0
    lat0 = climb[0][0]
    return (_fraction_near(seg, _cells(climb, lat0), lat0),
            _fraction_near(climb, _cells(seg, lat0), lat0))


# Taerskler for at godkende et match. Bevidst strenge: hellere ingen embed
# (og falde tilbage til vores egen genererede profil) end en profil for den
# forkerte vej — jf. CLAUDE.md §6 om datakorrekthed frem for daekning.
ON_ROUTE_MIN = 0.85    # segmentet må ikke stikke af ad en anden vej
COVERAGE_MIN = 0.80    # segmentet skal daekke stoerstedelen af stigningen
#
# 0.80 er valgt empirisk: Strava-segmenter starter sjaeldent praecis hvor
# roadbogens klatring starter, saa aegte match lander typisk paa 84-100%
# daekning (bekraeftet: "SASSENAGE B&C - Engins Haut" 10.37 km mod vores
# 11.6 km). Kombineret med laengde-ratio 0.75-1.33, gradient inden for 2% og
# ON_ROUTE_MIN kan et fragment ikke slippe igennem — kun en let afkortet
# udgave af den rigtige stigning.


def expected_gain_m(db_climb: dict) -> float | None:
    """
    Klatrens HOEJDEMETER (stigning) — det tal hoejdetjekket skal maale imod.

    `elevation_m` er ikke paalideligt hoejdemeter i hele databasen. Maalt
    2026-08-20 er medianen af elevation_m / (laengde x gennemsnitsgradient)
    1.00 for Tour de France 2026, men 2.70 for Vuelta 2026 — der indeholder
    feltet overvejende TOPHOEJDEN (Coll d'Ordino staar med 1982 m, mens
    stigningen reelt vinder ca. 693 m). Stravas `elev_difference` ER stigning,
    saa en direkte sammenligning afviste korrekte segmenter paa et
    hoejdemeter-diff, der i virkeligheden var forskellen mellem havoverflade og
    bjergtop.

    Derfor: brug elevation_m naar det er konsistent med laengde x gradient
    (inden for 25%) — saa opfoerer tjekket sig praecis som foer for de loeb,
    hvor feltet er korrekt. Ellers regnes hoejdemeteren ud af de to felter, der
    ER internt konsistente. Kan ingen af delene lade sig goere, returneres None,
    og kalderen springer hoejdetjekket over frem for at gaette.
    """
    elev = db_climb.get("elevation_m")
    length = db_climb.get("length_km")
    grade = db_climb.get("avg_gradient")
    computed = length * grade * 10 if (length and grade) else None

    if elev and computed:
        return elev if 0.75 <= elev / computed <= 1.25 else computed
    return elev or computed


def segment_matches_climb_geo(segment: dict, db_climb: dict,
                               climb_points: list[tuple[float, float]]) -> tuple[bool, str]:
    """
    Verificerer en /segments/explore-kandidat mod vores DB-klatring — paa
    GEOMETRI i stedet for navn.

    Navnetjekket (name_plausible_match) er bevidst droppet her: Strava-navne er
    brugerskabte, og korrekte segmenter hedder ofte noget helt andet end
    bjerget — bekraeftet 2026-07-22 er det rigtige segment for "Côte d'Engins"
    navngivet "D531 Climb" (100% geometrisk sammenfald), og et aegte
    Tourmalet-segment hedder "Ullrich vs. Lance 2003=24min". Navnetjekket var
    dermed selv en hovedaarsag til den lave daekning (10%).

    `segment` er raa explore-respons; `climb_points` er klatrens [(lat, lon)]
    fra vores GPX. Returnerer (godkendt, forklaring) — forklaringen indeholder
    Strava-tal og maa kun bruges i lokale logs, aldrig vises offentligt.
    """
    grade = segment.get("avg_grade")
    if grade is None:
        return False, "mangler gradient"
    if grade <= 0:
        # Samme vej den forkerte vej: nedkoersler ligger geometrisk oven i
        # stigningen og ville ellers score perfekt (bekraeftet: "descente
        # Engins" var hoejest scorende kandidat for Côte d'Engins).
        return False, f"nedkoersel ({grade:.1f}%)"

    db_len = db_climb.get("length_km")
    seg_len = (segment.get("distance") or 0) / 1000
    if db_len and seg_len > 0:
        ratio = seg_len / db_len
        # Nedre graense saenket til 0.65 (2026-08-20): 0.75 var STRENGERE end
        # den geometriske port, den sidder foran, og vetoede derfor segmenter,
        # geometrien allerede havde godkendt — bekraeftet paa Col de Sant
        # Andrieu, hvor segment 715848 laa 100% paa ruten og daekkede 81% af
        # klatren, men blev kasseret paa ratio 0.74. Et FRAGMENT kan stadig
        # ikke slippe igennem: med ON_ROUTE ~1.0 medfoerer ratio 0.65 en
        # daekning omkring 0.65, og COVERAGE_MIN = 0.80 afviser den. Det er
        # altsaa fortsat geometrien, der doemmer — dette er kun et billigt
        # forfilter, der frasorterer aabenlyse misforhold.
        # Gaelder KUN denne GPX-variant. segment_matches_climb_summit() har
        # ingen daekningsport, saa dér er laengde-ratioen baerende og uaendret.
        if ratio < 0.65 or ratio > 1.33:
            return False, f"laengde-ratio {ratio:.2f} uden for tolerance"

    db_grad = db_climb.get("avg_gradient")
    if db_grad is not None and abs(grade - db_grad) > 2.0:
        return False, f"gradient-diff {abs(grade - db_grad):.1f}% uden for tolerance"

    db_elev = expected_gain_m(db_climb)
    seg_gain = segment.get("elev_difference")
    if db_elev and seg_gain is not None:
        diff = abs(seg_gain - db_elev)
        if diff > max(150, db_elev * 0.35):
            return False, f"hoejdemeter-diff {diff:.0f}m uden for tolerance"

    pts = segment.get("points")
    if not pts:
        return False, "ingen rutegeometri i svaret"
    on_route, coverage = geo_overlap(decode_polyline(pts), climb_points)
    if on_route < ON_ROUTE_MIN:
        return False, f"kun {on_route:.0%} af segmentet ligger paa ruten"
    if coverage < COVERAGE_MIN:
        return False, f"daekker kun {coverage:.0%} af stigningen"
    return True, f"rute {on_route:.0%}, daekning {coverage:.0%}, {seg_len:.2f} km @ {grade:.1f}%"


# Kalibreret 2026-08-07 mod de 21 stigninger, der allerede har et
# GPX-verificeret segment: afstanden fra Nominatims geokodning af klatrenavnet
# til segmentets toppunkt var median 0,30 km og 15 af 18 under 0,81 km, mens kun
# 1 ud af 306 FORKERTE par lå under 2 km. 2,0 km rammer altså både recall og
# præcision. Se modul-docstringen i veloviewer_nogpx_agent.py for kalibreringen.
SUMMIT_MAX_KM = 2.0


def segment_matches_climb_summit(segment: dict, db_climb: dict,
                                  anchor: tuple[float, float]) -> tuple[bool, str]:
    """
    Verificerer en /segments/explore-kandidat UDEN rutedata (GPX).

    Erstatter geo_overlap()-kontrollen med et identitetstjek: ligger segmentets
    TOPPUNKT på det geokodede pas? Det er nødvendigt, fordi tolerancerne på
    længde/højdemeter/hældning alene er dokumenteret utilstrækkelige — de lod
    "Ste Marie - Tourmalet 10kms" passere som Col d'Aspin (se
    name_plausible_match). Formsammenligning af højdekurven blev afprøvet som
    alternativ 2026-08-07 og forkastet: de fleste asfaltstigninger har samme
    normaliserede form, så korrekte og forkerte par overlappede fuldstændigt.

    Toppunktet er polylinjens SIDSTE punkt: Strava-segmenter er retningsbestemte,
    og vi kræver positiv gennemsnitshældning, så slutpunktet er pr. definition
    det høje. Det sparer et /streams-kald pr. kandidat.

    `anchor` er (lat, lon) for klatrens top fra geokodning. Returnerer
    (godkendt, forklaring) — forklaringen indeholder Strava-tal og må kun
    bruges i lokale logs, aldrig vises offentligt (se modulets docstring).
    """
    grade = segment.get("avg_grade")
    if grade is None:
        return False, "mangler gradient"
    if grade <= 0:
        # Nedkørslen ligger geografisk oven i stigningen og har samme toppunkt,
        # så uden dette filter ville den score perfekt. Bekræftet 2026-08-07:
        # "Słodyczki DH" (-8,1%) blev godkendt som stigningen Słodyczki, fordi
        # metrics-varianten segment_matches_climb() mangler netop dette tjek.
        return False, f"nedkoersel ({grade:.1f}%)"

    db_len = db_climb.get("length_km")
    seg_len = (segment.get("distance") or 0) / 1000
    if not db_len or seg_len <= 0:
        return False, "mangler laengde at sammenligne paa"
    ratio = seg_len / db_len
    if ratio < 0.75 or ratio > 1.33:
        return False, f"laengde-ratio {ratio:.2f} uden for tolerance"

    db_grad = db_climb.get("avg_gradient")
    if db_grad is not None and abs(grade - db_grad) > 2.0:
        return False, f"gradient-diff {abs(grade - db_grad):.1f}% uden for tolerance"

    db_elev = expected_gain_m(db_climb)
    seg_gain = segment.get("elev_difference")
    if db_elev and seg_gain is not None:
        diff = abs(seg_gain - db_elev)
        if diff > max(150, db_elev * 0.35):
            return False, f"hoejdemeter-diff {diff:.0f}m uden for tolerance"

    pts = segment.get("points")
    if not pts:
        return False, "ingen rutegeometri i svaret"
    decoded = decode_polyline(pts)
    if len(decoded) < 2:
        return False, "for kort rutegeometri"
    summit = decoded[-1]
    d_summit = _haversine_km(summit[0], summit[1], anchor[0], anchor[1])
    if d_summit > SUMMIT_MAX_KM:
        return False, f"toppunkt {d_summit:.2f} km fra det geokodede pas"

    return True, (f"top {d_summit:.2f} km fra pas, {seg_len:.2f} km @ {grade:.1f}%, "
                  f"laengde-ratio {ratio:.2f}")


def explore_segments(bounds: str, activity_type: str = "riding") -> list[dict]:
    """
    Finder kandidat-segmenter inden for en bounding box via Stravas officielle
    /segments/explore. Returnerer op til 10 segmenter, rangeret efter Stravas
    egen popularitet — IKKE en udtømmende liste over alt i boksen. For kendte,
    højtprioriterede klatre (Tour de France-bjerge) er de næsten altid blandt
    de mest populære segmenter i deres område, så loftet er sjældent et
    problem her; for mindre lokale stigninger i segment-tætte områder kan det
    rigtige segment blive skygget af mere populære naboer — i så fald finder
    denne funktion intet brugbart, og klatren falder tilbage til den
    eksisterende climbfinder_agent.py/climb_profile_generator.py-kæde.

    `bounds` er "min_lat,min_lng,max_lat,max_lng".
    """
    res = _get_with_retry(f"{API_BASE}/segments/explore", {"bounds": bounds, "activity_type": activity_type})
    if res is None or res.status_code == 429:
        return []  # opgav efter MAX_RATE_LIMIT_RETRIES forsøg
    res.raise_for_status()
    return res.json().get("segments", [])


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _significant_tokens(name: str) -> set[str]:
    """Udtrækker de ord i et klatrenavn, der reelt identificerer bjerget (ikke "Col", "de" osv.)."""
    n = _strip_accents(name).lower()
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    return {w for w in n.split() if w not in _STOPWORDS and len(w) >= 3}


def name_plausible_match(db_climb_name: str, segment_name: str | None) -> bool:
    """
    /segments/explore søger geografisk, ikke på navn — et rent talmæssigt
    tolerance-match kan derfor ramme et helt andet, men geografisk
    nærliggende segment (bekræftet: "Col d'Aspin" matchede tal-mæssigt mod
    segmentet "Ste Marie - Tourmalet 10kms", som reelt er en del af
    Tourmalet-tilkørslen). Kræver derfor at mindst ét betydende ord fra
    DB-navnet også optræder i segmentnavnet, som en ekstra guard mod netop
    denne fejlklasse (samme ånd som STG-004/STG-009).
    """
    if not segment_name:
        return False
    tokens = _significant_tokens(db_climb_name)
    if not tokens:
        return True  # intet betydende ord at tjekke imod (fx meget korte navne) — spring guard over
    seg_norm = _strip_accents(segment_name).lower()
    return any(tok in seg_norm for tok in tokens)


def segment_matches_climb(segment: dict, db_climb: dict) -> tuple[bool, str]:
    """
    Sammenligner et Strava-segment mod vores DB-klatredata. Samme
    tolerance-mønster som climbfinder_agent.py's metrics_ok() og
    climb_profile_generator.py's within_tolerance() — ±33% længde,
    højdemeter inden for max(150m, 35%), hældning inden for ±1.5% —
    samt et navnetjek (name_plausible_match) mod netop dette API's
    geografiske (ikke navne-baserede) søgning.
    Returnerer (godkendt, forklaring) — forklaringen er kun til brug i
    interne logs for scriptets ejer, aldrig til visning andre steder.
    """
    if db_climb.get("name") and not name_plausible_match(db_climb["name"], segment.get("name")):
        return False, f"navn stemmer ikke overens med '{db_climb['name']}'"

    reasons = []

    db_len = db_climb.get("length_km")
    seg_len = segment.get("distance_km", 0)
    if db_len and seg_len and seg_len > 0:
        ratio = seg_len / db_len
        if ratio < 0.75 or ratio > 1.33:
            return False, f"længde-ratio {ratio:.2f} uden for tolerance"
        reasons.append(f"len ratio {ratio:.2f}")

    db_elev = expected_gain_m(db_climb)
    seg_high = segment.get("elevation_high")
    seg_low = segment.get("elevation_low")
    if db_elev and seg_high is not None and seg_low is not None:
        seg_gain = seg_high - seg_low
        diff = abs(seg_gain - db_elev)
        max_diff = max(150, db_elev * 0.35)
        if diff > max_diff:
            return False, f"højdemeter-diff {diff:.0f}m uden for tolerance ({max_diff:.0f}m)"
        reasons.append(f"gain diff {diff:.0f}m")

    db_grad = db_climb.get("avg_gradient")
    seg_grad = segment.get("average_grade")
    if db_grad is not None and seg_grad is not None:
        diff = abs(seg_grad - db_grad)
        if diff > 1.5:
            return False, f"hældnings-diff {diff:.1f}% uden for tolerance"
        reasons.append(f"grad diff {diff:.1f}%")

    if not reasons:
        return False, "intet at sammenligne mod (DB mangler alle nøgletal)"
    return True, ", ".join(reasons)


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-segment", type=int, required=True,
                         help="Strava segment-ID, henter og printer diagnosticering (kun til lokal test)")
    args = parser.parse_args()

    print(f"Henter access token via refresh-flow...")
    token = get_access_token()
    print(f"  OK — access token modtaget (udløber om {int(_access_token_cache['expires_at'] - time.time())}s)")

    print(f"Henter segment {args.test_segment} fra Stravas API...")
    seg = get_segment(args.test_segment)
    if seg is None:
        print("  Segment ikke fundet (404).")
        sys.exit(1)

    print(f"  OK — segment hentet. distance_km={seg['distance_km']:.2f}, "
          f"average_grade={seg['average_grade']}, "
          f"elevation_high={seg['elevation_high']}, elevation_low={seg['elevation_low']}")
    print("(Denne udskrift er kun til lokal test af dig som kontoejer — "
          "produktionskoden i veloviewer_agent.py må aldrig logge disse felter et sted, andre kan se dem.)")
