"""
climbfinder_agent.py
Finder ClimbFinder-profilbilleder for Giro-stigninger og gemmer i stage_climbs.profile_image_url.

Bruger requests.Session til at logge ind og kalde ClimbFinder API.
Fallback: ingen profil (frontend bruger SVG-gradient-illustration).

Kør: python climbfinder_agent.py --race giro-d-italia-2026
     python climbfinder_agent.py --race giro-d-italia-2026 --stage 7
     python climbfinder_agent.py --race giro-d-italia-2026 --overwrite
"""

import os
import re
import sys
import io
import json
import time
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

CF_EMAIL    = "jonasb409@gmail.com"
CF_PASSWORD = "luksusclimb123"
CF_BASE     = "https://uphill.climbfinder.com/v2"

DELAY = 1.2

# Foretrukne lande (Grand Tour-lande)
PREFERRED_COUNTRIES = {"IT", "FR", "ES", "CH", "AT"}

# Overstyring af søgetermer — None = skip denne finish (ikke på ClimbFinder)
SEARCH_OVERRIDES: dict[str, str | None] = {
    "Pila (Gressan)":            "Pila Gressan",
    "Alleghe (Piani di Pezzè)":  "Alleghe",
    # Ingen god ClimbFinder-match:
    "Andalo":        None,
    "Novi Ligure":   None,
    "Pieve di Soligo": None,
    "Veliko Tarnovo": None,
    "Sofia":         None,
    "Fermo":         None,  # "San Fermo" er i Como, ikke Marche
    "Carì":          None,  # Ingen IT-match på ClimbFinder
}


# ── ClimbFinder session ────────────────────────────────────────────────────────

def cf_login() -> requests.Session | None:
    """Logger ind på ClimbFinder og returnerer en authenticated Session."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    })

    # Hent login-siden (sætter evt. session-cookies)
    session.get("https://climbfinder.com/en/login")
    time.sleep(0.5)

    res = session.post(
        "https://climbfinder.com/en/form/login",
        data={
            "email":    CF_EMAIL,
            "password": CF_PASSWORD,
            "referer":  "https://climbfinder.com/en",
            "route":    "0",
        },
        headers={"Referer": "https://climbfinder.com/en/login"},
        allow_redirects=True,
    )

    if "remember" not in session.cookies and ("login" in res.url or not res.ok):
        print(f"  Login fejlede — status {res.status_code}, URL: {res.url}")
        return None

    # Kopier login-cookies til API-subdomænet (uphill.climbfinder.com).
    # Brug direkte iteration for at undgå CookieConflictError ved duplikater.
    for name in ("remember", "cisession"):
        vals = [c.value for c in session.cookies if c.name == name and c.domain == "climbfinder.com"]
        if vals:
            session.cookies.set(name, vals[0], domain="uphill.climbfinder.com")

    print("  Logget ind")
    return session


def cf_search(session: requests.Session, term: str) -> dict | None:
    """
    Søger ClimbFinder efter 'term'.
    Returnerer { id, name, countryIso } for bedste match, eller None.
    """
    res = session.get(
        f"{CF_BASE}/search",
        params={"term": term, "language": "en"},
        headers={
            "Accept": "application/json",
            "Referer": "https://climbfinder.com/en",
            "Origin": "https://climbfinder.com",
        },
    )
    if not res.ok:
        return None

    climbs = res.json().get("data", {}).get("climbs", [])
    if not climbs:
        return None

    # Foretræk kendte cykelraces-lande
    preferred = [c for c in climbs if c.get("countryIso") in PREFERRED_COUNTRIES]
    return preferred[0] if preferred else climbs[0]


def cf_get_profile(session: requests.Session, climb_id: int) -> dict | None:
    """Henter detaljer (slug + profile URL) for en specifik klatring."""
    res = session.get(
        f"{CF_BASE}/climbs/{climb_id}",
        headers={
            "Accept": "application/json",
            "Referer": "https://climbfinder.com/en",
            "Origin": "https://climbfinder.com",
        },
    )
    if not res.ok:
        return None

    d = res.json().get("data", {})
    return {
        "slug":    d.get("slug"),
        "profile": d.get("profile"),
        "name":    d.get("name"),
    }


# ── Supabase helpers ───────────────────────────────────────────────────────────

def sb_get(table: str, query: str) -> list[dict]:
    res = requests.get(f"{SUPABASE_URL}/rest/v1/{table}{query}", headers=SB_HEADERS)
    return res.json() if res.ok else []


def get_race_id(race_slug: str) -> str | None:
    rows = sb_get("races", f"?slug=eq.{race_slug}&select=id&limit=1")
    return rows[0]["id"] if rows else None


def get_stages(race_id: str, stage_number: int | None) -> list[dict]:
    url = (
        f"?race_id=eq.{race_id}"
        f"&select=id,stage_number,finish_location,stage_type"
        f"&order=stage_number.asc"
    )
    if stage_number:
        url += f"&stage_number=eq.{stage_number}"
    return sb_get("stages", url)


def get_climbs_for_stage(stage_id: str, only_missing: bool) -> list[dict]:
    url = f"?stage_id=eq.{stage_id}&select=id,name,profile_image_url"
    rows = sb_get("stage_climbs", url)
    return [r for r in rows if not r.get("profile_image_url")] if only_missing else rows


# ── Søgning med fallback ───────────────────────────────────────────────────────

def clean_term(finish_location: str) -> str:
    """Renser finish_location til søgbar streng (fjerner parenteser)."""
    return re.sub(r"\s*\([^)]*\)", "", finish_location).strip()


def find_profile(session: requests.Session, finish_location: str) -> str | None:
    """
    Finder ClimbFinder-profilbillede for en finish-location.
    Returnerer image URL eller None.
    """
    # Eksplicit override
    if finish_location in SEARCH_OVERRIDES:
        term = SEARCH_OVERRIDES[finish_location]
        if term is None:
            print("    -> Ingen ClimbFinder-profil (eksplicit skip)")
            return None
    else:
        term = clean_term(finish_location)

    print(f"    Søger: '{term}'")
    match = cf_search(session, term)
    time.sleep(DELAY)

    # Fallback: prøv kun første ord
    if not match:
        first_word = term.split()[0]
        if first_word != term and len(first_word) > 3:
            print(f"    Fallback: '{first_word}'")
            match = cf_search(session, first_word)
            time.sleep(DELAY)

    if not match:
        print("    -> Ingen match fundet")
        return None

    print(f"    Fandt: {match['name']} ({match.get('countryIso')}, id={match['id']})")
    detail = cf_get_profile(session, match["id"])
    time.sleep(DELAY)

    if not detail or not detail.get("profile"):
        return None

    print(f"    Profil: {detail['profile']}")
    return detail["profile"]


# ── Opdatering af Supabase ─────────────────────────────────────────────────────

def update_stage_profile(stage_id: str, profile_url: str) -> bool:
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/stage_climbs?stage_id=eq.{stage_id}",
        json={"profile_image_url": profile_url},
        headers=SB_HEADERS,
    )
    return res.status_code in (200, 204)


# ── Hovedpipeline ─────────────────────────────────────────────────────────────

def process_race(race_slug: str, stage_number: int | None, overwrite: bool) -> None:
    race_id = get_race_id(race_slug)
    if not race_id:
        print(f"Løb ikke fundet: {race_slug}")
        return

    stages = get_stages(race_id, stage_number)
    print(f"climbfinder_agent.py — {race_slug}")
    print(f"Fandt {len(stages)} etaper\n")

    print("Logger ind på ClimbFinder...")
    session = cf_login()
    if not session:
        return
    print()

    updated_total = 0
    profile_cache: dict[str, str | None] = {}

    for stage in stages:
        n      = stage["stage_number"]
        s_id   = stage["id"]
        s_type = stage.get("stage_type", "")
        finish = stage.get("finish_location", "")

        climbs = get_climbs_for_stage(s_id, only_missing=not overwrite)
        if not climbs:
            continue

        print(f"[E{n}] {finish} ({s_type}) — {len(climbs)} stigning(er)")

        if finish in profile_cache:
            profile_url = profile_cache[finish]
        else:
            profile_url = find_profile(session, finish)
            profile_cache[finish] = profile_url

        if not profile_url:
            continue

        if update_stage_profile(s_id, profile_url):
            print(f"    -> Gemt for {len(climbs)} stigning(er)")
            updated_total += len(climbs)
        else:
            print("    -> DB-fejl ved opdatering")

    print(f"\nFærdig: {updated_total} stigninger opdateret med ClimbFinder-profil")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--race",      required=True)
    parser.add_argument("--stage",     type=int)
    parser.add_argument("--overwrite", action="store_true", help="Overskiv eksisterende profiler")
    args = parser.parse_args()

    process_race(args.race, args.stage, args.overwrite)
