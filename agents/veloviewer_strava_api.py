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


def _get_with_retry(url: str, params: dict) -> requests.Response | None:
    token = get_access_token()
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        res = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=15)
        if res.status_code != 429:
            return res
        if _daily_limit_exhausted(res):
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

    db_elev = db_climb.get("elevation_m")
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
