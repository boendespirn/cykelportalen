"""
profile_reader_agent.py
Bruger Claude vision til at aflæse klatredata fra etapehøjdeprofil-billeder.
Erstatter syntetiske stage_climbs med rigtige data (navn, km fra start, længde, gradient, kategori).
Kører derefter ClimbFinder-søgning for hvert klatrernavn.

Kør: python profile_reader_agent.py --race giro-d-italia-2026
     python profile_reader_agent.py --race giro-d-italia-2026 --stage 19
     python profile_reader_agent.py --race giro-d-italia-2026 --all   (overskriver eksisterende)
"""

import os
import re
import sys
import io
import json
import time
import argparse
import requests
import anthropic
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")

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

VISION_PROMPT = """This is a cycling stage elevation profile from a professional race.

Extract ONLY the officially categorized climbs (marked with a UCI category: HC, 1, 2, 3, 4, or C/sprint mountain passes). Do NOT include sponsor segments (e.g. "Red Bull KM", "Intermediate Sprint", etc.) — only real named climbs.

For each climb return a JSON object with these exact fields:
- "name": the official climb name as printed on the image (e.g. "Passo Giau", "Col du Galibier")
- "km_from_start": the km value where the climb bracket starts on the bottom axis
- "length_km": length in km as a decimal number (from the "X.X km" label)
- "avg_gradient": average gradient as a decimal number without % (e.g. 8.2 from "8.2%/19%")
- "max_gradient": max gradient as a decimal number without % (e.g. 19 from "8.2%/19%")
- "altitude_m": summit altitude in meters (integer shown above the summit)
- "category": "HC", "1", "2", "3", "4", or "C"

Return ONLY a valid JSON array, no markdown fences, no explanation."""


# ── Supabase ──────────────────────────────────────────────────────────────────

def sb_get(table: str, query: str) -> list[dict]:
    res = requests.get(f"{SUPABASE_URL}/rest/v1/{table}{query}", headers=SB_HEADERS)
    return res.json() if res.ok else []


def get_race_id(slug: str) -> str | None:
    rows = sb_get("races", f"?slug=eq.{slug}&select=id&limit=1")
    return rows[0]["id"] if rows else None


def get_stages(race_id: str, stage_number: int | None) -> list[dict]:
    url = (
        f"?race_id=eq.{race_id}"
        f"&select=id,stage_number,finish_location,stage_type,elevation_image_url,distance_km"
        f"&order=stage_number.asc"
    )
    if stage_number:
        url += f"&stage_number=eq.{stage_number}"
    stages = sb_get("stages", url)
    return [s for s in stages if s.get("elevation_image_url")]


def has_real_climbs(stage_id: str) -> bool:
    """True hvis etapen allerede har ikke-syntetiske klatringer (kender vi på name-feltet)."""
    rows = sb_get("stage_climbs", f"?stage_id=eq.{stage_id}&select=name&limit=1")
    if not rows:
        return False
    name = rows[0].get("name", "")
    # Syntetiske navne starter med "Afslutnings" eller "Mellemliggende" eller "Afgørende"
    return not any(name.startswith(p) for p in ("Afslutnings", "Mellemliggende", "Afgørende"))


def delete_climbs(stage_id: str) -> None:
    requests.delete(
        f"{SUPABASE_URL}/rest/v1/stage_climbs?stage_id=eq.{stage_id}",
        headers=SB_HEADERS,
    )


def insert_climb(record: dict) -> bool:
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/stage_climbs",
        json=record,
        headers=SB_HEADERS,
    )
    return res.status_code in (200, 201)


# ── Vision: aflæs profil-billede ──────────────────────────────────────────────

def read_climbs_from_image(image_url: str) -> list[dict]:
    """
    Sender etapebilledet til Claude og returnerer liste af klatringer.
    Returnerer [] ved fejl.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "url", "url": image_url},
                    },
                    {"type": "text", "text": VISION_PROMPT},
                ],
            }],
        )
        raw = msg.content[0].text.strip()

        # Rens evt. markdown-kodeblok
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        climbs = json.loads(raw)
        return climbs if isinstance(climbs, list) else []

    except (json.JSONDecodeError, anthropic.APIError, IndexError) as e:
        print(f"    [Vision fejl: {e}]")
        return []


# ── ClimbFinder ───────────────────────────────────────────────────────────────

def cf_login() -> requests.Session | None:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    session.get("https://climbfinder.com/en/login")
    time.sleep(0.5)
    session.post(
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
    for name in ("remember", "cisession"):
        vals = [c.value for c in session.cookies if c.name == name and c.domain == "climbfinder.com"]
        if vals:
            session.cookies.set(name, vals[0], domain="uphill.climbfinder.com")

    if not any(c.name == "remember" for c in session.cookies):
        print("  ClimbFinder login fejlede")
        return None
    return session


CF_HEADERS = {
    "Accept":  "application/json",
    "Referer": "https://climbfinder.com/en",
    "Origin":  "https://climbfinder.com",
}

PREFERRED_COUNTRIES = {"IT", "FR", "ES", "CH", "AT"}


def _name_similarity(search: str, result: str) -> bool:
    """
    Kræver at mindst ét betydningsfuldt ord fra søgetermen
    optræder i resultatet (case-insensitiv).
    Undgår falske positive som "COI" → "Le Coin Perdu".
    """
    # Rens: fjern parenteser, lowercase
    search_clean = re.sub(r"\([^)]*\)", "", search).strip().lower()
    result_lower = result.lower()

    # Ord der er for korte eller generiske til at matche på
    skip = {"le", "la", "les", "de", "du", "des", "from", "via", "the", "di", "del", "della"}

    words = [w for w in re.split(r"\W+", search_clean) if len(w) >= 3 and w not in skip]
    if not words:
        return True  # Kan ikke vurdere — accepter

    return any(re.search(rf"\b{re.escape(w)}\b", result_lower) for w in words)


def _clean_search_term(name: str) -> str:
    """Renser parentetisk indhold og normaliserer til søgestreng."""
    return re.sub(r"\s*\([^)]*\)", "", name).strip()


def cf_find_profile(session: requests.Session, climb_name: str) -> str | None:
    """Søger ClimbFinder og returnerer profil-URL eller None."""
    term = _clean_search_term(climb_name)

    res = session.get(
        f"{CF_BASE}/search",
        params={"term": term, "language": "en"},
        headers=CF_HEADERS,
    )
    time.sleep(DELAY)
    if not res.ok:
        return None

    climbs = res.json().get("data", {}).get("climbs", [])

    # Filtrer: foretrukne lande + navnelighed
    preferred = [
        c for c in climbs
        if c.get("countryIso") in PREFERRED_COUNTRIES
        and _name_similarity(term, c.get("name", ""))
    ]
    # Fallback: kun navnelighed (alle lande)
    if not preferred:
        preferred = [c for c in climbs if _name_similarity(term, c.get("name", ""))]

    match = preferred[0] if preferred else None
    if not match:
        return None

    detail_res = session.get(
        f"{CF_BASE}/climbs/{match['id']}",
        headers=CF_HEADERS,
    )
    time.sleep(DELAY)
    if not detail_res.ok:
        return None

    return detail_res.json().get("data", {}).get("profile")


# ── Hovedpipeline ─────────────────────────────────────────────────────────────

def process_race(race_slug: str, stage_number: int | None, overwrite: bool) -> None:
    if not ANTHROPIC_KEY:
        print("Fejl: ANTHROPIC_API_KEY mangler i .env")
        return

    race_id = get_race_id(race_slug)
    if not race_id:
        print(f"Løb ikke fundet: {race_slug}")
        return

    stages = get_stages(race_id, stage_number)
    print(f"profile_reader_agent.py — {race_slug}")
    print(f"Fandt {len(stages)} etaper med højdeprofil-billede\n")

    print("Logger ind på ClimbFinder...")
    cf_session = cf_login()
    if not cf_session:
        print("Fortsætter uden ClimbFinder (ingen profil-billeder)")
    else:
        print("Logget ind.\n")

    inserted_total = 0

    for stage in stages:
        n      = stage["stage_number"]
        s_id   = stage["id"]
        s_type = stage.get("stage_type", "")
        img    = stage["elevation_image_url"]

        # Spring over flad/enkeltstart
        if s_type in ("flat", "tt", "itt"):
            continue

        # Spring over hvis allerede har rigtige data (medmindre --all)
        if not overwrite and has_real_climbs(s_id):
            print(f"[E{n}] Allerede rigtige klatredata — springer over")
            continue

        print(f"[E{n}] {stage.get('finish_location', '')} ({s_type})")
        print(f"  Aflæser billede med Claude vision...")

        climbs = read_climbs_from_image(img)

        if not climbs:
            print("  -> Ingen klatringer fundet i billedet")
            continue

        print(f"  -> Fandt {len(climbs)} klatringer: {[c.get('name','?') for c in climbs]}")

        # Slet gamle syntetiske data
        delete_climbs(s_id)

        for i, climb in enumerate(climbs):
            name         = climb.get("name", "Ukendt stigning")
            km_from      = climb.get("km_from_start")
            length_km    = climb.get("length_km")
            avg_grad     = climb.get("avg_gradient")
            max_grad     = climb.get("max_gradient")
            altitude     = climb.get("altitude_m")
            category     = climb.get("category")

            # Beregn elevation_m fra length og gradient hvis altitude mangler
            elevation_m = None
            if altitude:
                elevation_m = int(altitude)
            elif length_km and avg_grad:
                elevation_m = int(length_km * avg_grad * 10)

            # Søg ClimbFinder
            profile_url = None
            if cf_session:
                print(f"  Søger ClimbFinder: '{name}'")
                profile_url = cf_find_profile(cf_session, name)
                if profile_url:
                    print(f"    -> {profile_url}")
                else:
                    print(f"    -> Ingen match")

            record = {
                "stage_id":        s_id,
                "name":            name,
                "km_from_start":   km_from,
                "length_km":       length_km,
                "elevation_m":     elevation_m,
                "avg_gradient":    avg_grad,
                "max_gradient":    max_grad,
                "profile_image_url": profile_url,
                "source":          "vision",
            }

            if insert_climb(record):
                inserted_total += 1
            else:
                print(f"  -> DB-fejl ved insert af {name}")

        print()

    print(f"Færdig: {inserted_total} klatringer indsat")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--race",  required=True)
    parser.add_argument("--stage", type=int)
    parser.add_argument("--all",   action="store_true", help="Overskiv eksisterende rigtige data")
    args = parser.parse_args()

    process_race(args.race, args.stage, args.all)
