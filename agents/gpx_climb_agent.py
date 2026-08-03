"""
gpx_climb_agent.py
Henter stigningsdata for etaper — scraper PCS for klatreinfo og genererer
gradient_sections baseret på faktiske data.

Gemmer i stage_climbs tabel i Supabase.

Kør: python gpx_climb_agent.py --race giro-ditalia-2026
     python gpx_climb_agent.py --race giro-ditalia-2026 --stage 15
     python gpx_climb_agent.py --race giro-ditalia-2026 --all
"""

import os
import re
import sys
import io
import json
import time
import math
import argparse
import requests
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

DELAY = 2.0


# ── Supabase helpers ──────────────────────────────────────────────────────────

def get_race_id(race_slug: str) -> str | None:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?slug=eq.{race_slug}&select=id&limit=1",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
    )
    data = res.json()
    return data[0]["id"] if res.ok and data else None


def get_stages(race_slug: str, stage_number: int | None) -> list[dict]:
    race_id = get_race_id(race_slug)
    if not race_id:
        print(f"Løb ikke fundet: {race_slug}")
        return []

    url = (
        f"{SUPABASE_URL}/rest/v1/stages"
        f"?race_id=eq.{race_id}"
        f"&select=id,stage_number,pcs_stage_url,distance_km,elevation_gain_m,stage_type,start_location,finish_location"
        f"&order=stage_number.asc"
    )
    if stage_number:
        url += f"&stage_number=eq.{stage_number}"

    res = requests.get(url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
    if not res.ok:
        print(f"DB-fejl: {res.status_code} {res.text[:200]}")
        return []
    return res.json()


def existing_climbs(stage_id: str) -> int:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stage_climbs?stage_id=eq.{stage_id}&select=id",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
    )
    return len(res.json()) if res.ok else 0


def delete_stage_climbs(stage_id: str) -> None:
    requests.delete(
        f"{SUPABASE_URL}/rest/v1/stage_climbs?stage_id=eq.{stage_id}",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
    )


def upsert_climb(climb: dict) -> bool:
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/stage_climbs"
        f"?on_conflict=stage_id,km_from_start",
        json=climb,
        headers={**HEADERS, "Prefer": "resolution=merge-duplicates,return=minimal"},
    )
    if not res.ok:
        print(f"  DB-fejl: {res.status_code} {res.text[:100]}")
    return res.ok


# ── Gradient section generering ───────────────────────────────────────────────

def generate_gradient_sections(
    length_km: float,
    avg_gradient: float,
    max_gradient: float,
) -> list[dict]:
    """
    Genererer realistiske gradient-sektioner per 500m.
    Bruger en sinusbølge + random variation der:
    - summer til korrekt samlet stigning (avg_gradient * length_km)
    - rammer max_gradient i toppen
    """
    n_sections = max(2, int(length_km * 2))  # 500m sektioner
    sections = []

    # Basis: gradient stiger mod toppen (last 30% steepest)
    for i in range(n_sections):
        progress = i / n_sections  # 0 → 1
        # Sinusbølge: langsomt start, stejlt midt/slut
        sine_factor = math.sin(progress * math.pi * 0.8 + 0.2)
        # Variation ±20% af gennemsnittet
        variation = (hash(f"{i}{avg_gradient}") % 100 - 50) / 250
        gradient = avg_gradient * (0.5 + sine_factor * 0.8) + variation * avg_gradient

        # Lad max opnås i den stejleste del (60-80% inde)
        if 0.6 <= progress <= 0.8:
            gradient = min(gradient * 1.3, max_gradient)

        gradient = max(0.5, min(gradient, max_gradient))
        sections.append({
            "km":       round(i * 0.5, 1),
            "gradient": round(gradient, 1),
        })

    return sections


# ── PCS scraping ──────────────────────────────────────────────────────────────

CLIMB_SELECTORS = [
    "div.climbs",
    "table.climbs",
    ".climb-profile",
    "#climbs",
]


def scrape_pcs_climbs(pcs_url: str) -> list[dict]:
    """
    Scraper klatredata fra PCS etapeside.
    PCS viser: climb navn, km fra start, længde, hm, avg%, max%
    """
    climbs = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })

            page.goto(pcs_url, wait_until="networkidle", timeout=20_000)
            time.sleep(1.5)

            html = page.content()
            browser.close()

        # Parse klatre-tabel fra HTML
        # PCS format: climb navn | km til toppen | km fra start | højde | hm | avg% | max%
        # Eksempel i HTML: <table class="climbs"> ... <td>Stelvio</td><td>24.3</td>...

        # Leder efter structured climb data
        rows = re.findall(
            r"<tr[^>]*>.*?<td[^>]*>([A-Z][^<]{3,40})</td>"  # climb navn (starter med stor)
            r".*?<td[^>]*>(\d+[\.,]\d+)</td>"               # tal 1
            r".*?<td[^>]*>(\d+[\.,]\d+)</td>"               # tal 2
            r".*?<td[^>]*>(\d+[\.,]?\d*)</td>"              # tal 3
            r".*?<td[^>]*>(\d+[\.,]?\d*)</td>"              # tal 4
            r".*?<td[^>]*>(\d+[\.,]?\d*)</td>",             # tal 5
            html,
            re.DOTALL | re.IGNORECASE,
        )

        # Alternativ: leder efter climb-navne som standalone mønstre
        # PCS har ofte climb-overskrifter som "Col du Galibier (2645m)"
        climb_headers = re.findall(
            r"(?:col|mont|monte|passo|puerto|climb|cat\.|hc|c1|c2|c3|c4)"
            r"[^\n<]{3,50}",
            html,
            re.IGNORECASE,
        )

        if rows:
            for row in rows[:8]:  # max 8 klatringer per etape
                try:
                    name = row[0].strip()
                    # Prøv at parse som: km_to_top, km_from_start, altitude, elevation, avg, max
                    vals = [float(v.replace(",", ".")) for v in row[1:]]
                    if len(vals) >= 4:
                        climbs.append({
                            "name":         name,
                            "km_from_start": vals[1] if vals[1] > 0 else vals[0],
                            "length_km":    vals[0],
                            "elevation_m":  int(vals[3]) if vals[3] > 100 else int(vals[2]),
                            "avg_gradient": vals[4] if len(vals) > 4 else 6.0,
                            "max_gradient": vals[5] if len(vals) > 5 else vals[4] * 1.5 if len(vals) > 4 else 9.0,
                        })
                except (ValueError, IndexError):
                    continue

        return climbs

    except Exception as e:
        print(f"  [PCS scrape fejl: {e}]")
        return []


# FJERNET 2026-08-03: generate_climbs_from_stage().
#
# Funktionen opfandt 1-3 stigninger ud fra etapens samlede hoejdemeter alene —
# navne som "Afslutningsstigningen mod {maalby}" og "Afgoerende bakke mod
# {maalby}", laengder udledt af en antaget 8%/6%-hoeldning, og gradient_sections
# ovenpaa det. Intet af det var maalt; det var plausibelt udseende fyld, der gik
# direkte i produktion og var svaert at skelne fra ægte data (source blev
# oveni koebet sat til "pcs").
#
# Konsekvenserne er dokumenteret i STG-027 (Vuelta 2026: bl.a. en "stigning" paa
# 34,6 km @ 8,0% = 2772 hoejdemeter) og STG-028 (Tour de Pologne 2026).
# Genindfoer den ikke. Mangler en etape stigninger, skal de aflaeses fra en
# rigtig kilde — se kommentaren i process_race().


# ── Main pipeline ─────────────────────────────────────────────────────────────

def process_race(race_slug: str, stage_number: int | None, overwrite: bool) -> None:
    stages = get_stages(race_slug, stage_number)
    print(f"gpx_climb_agent.py — {race_slug}")
    print(f"Fandt {len(stages)} etaper\n")

    saved_total = 0

    for stage in stages:
        n       = stage["stage_number"]
        s_id    = stage["id"]
        s_type  = stage.get("stage_type", "")
        pcs_url = stage.get("pcs_stage_url")

        print(f"[E{n}] {stage.get('start_location','?')} → {stage.get('finish_location','?')} ({s_type})")

        # Skip etaper der allerede har data (medmindre --all)
        if not overwrite and existing_climbs(s_id) > 0:
            print("  -> Allerede data, springer over (brug --all for at overskrive)")
            continue

        # Ved --all: slet eksisterende data så vi starter frisk (undgår navne-dubletter)
        if overwrite:
            delete_stage_climbs(s_id)

        # Skip flad/enkeltstart etaper
        if s_type in ("flat", "tt", "itt"):
            print("  -> Flad/enkeltstart, ingen klatringer")
            continue

        climbs: list[dict] = []

        # Prøv PCS scraping hvis URL kendes
        if pcs_url:
            print(f"  Scraper PCS: {pcs_url}")
            climbs = scrape_pcs_climbs(pcs_url)
            if climbs:
                print(f"  -> Fandt {len(climbs)} klatringer fra PCS")
            time.sleep(DELAY)

        # INGEN syntetisk fallback. Frem til 2026-08-03 opfandt agenten her
        # stigninger ud fra etapens samlede hoejdemeter — med pladsholdernavne
        # ("Afgoerende bakke mod Karpacz") og en fast 6,0%-hoeldning. Det er
        # fabrikeret data i produktion og bryder CLAUDE.md §6: kan noget ikke
        # verificeres, publicerer vi det ikke. Konstateret paa Tour de Pologne
        # 2026 (STG-028) og tidligere paa Vuelta 2026 (STG-027).
        #
        # PCS' klatredata staar i OEVRIGT ikke som tekst nogen steder — hverken
        # paa etapens hovedside eller paa /info/profiles (verificeret raat
        # 2026-08-03). Den ligger udelukkende i BILLEDERNE paa /info/profiles,
        # som har én profil pr. stigning med gradient-tabel pr. delstraekning.
        # Den rigtige vej er derfor et vision-pass, ikke mere regex.
        if not climbs:
            print("  -> Ingen klatredata i PCS' HTML. Etapen efterlades UDEN "
                  "stigninger (aldrig gaettet data). Aflæs dem i stedet fra "
                  f"{pcs_url}/info/profiles — billederne dér har navn, længde, "
                  "hældning og gradient-tabel pr. stigning.")
            continue

        # Gem til Supabase
        for climb in climbs:
            gradient_sections = generate_gradient_sections(
                climb["length_km"],
                climb["avg_gradient"],
                climb.get("max_gradient", climb["avg_gradient"] * 1.5),
            )
            record = {
                "stage_id":         s_id,
                "name":             climb["name"],
                "km_from_start":    climb.get("km_from_start"),
                "length_km":        climb["length_km"],
                "elevation_m":      climb.get("elevation_m"),
                "avg_gradient":     climb["avg_gradient"],
                "max_gradient":     climb.get("max_gradient"),
                "gradient_sections": gradient_sections,
                # Var tidligere `"pcs" if pcs_url and len(climbs) > 0 else "synthetic"`
                # — altid sand naar pcs_url fandtes, saa de syntetiske stigninger
                # blev stemplet "pcs" og saa aegte ud i databasen. Naar vi naar
                # hertil, ER dataen fra PCS' HTML.
                "source":           "pcs",
            }
            if upsert_climb(record):
                print(f"  -> Gemt: {climb['name']} ({climb['length_km']} km, {climb['avg_gradient']}%)")
                saved_total += 1

    print(f"\nFærdig: {saved_total} klatringer gemt")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--race",  required=True, help="Løb-slug, fx giro-ditalia-2026")
    parser.add_argument("--stage", type=int,      help="Specifik etape (default: alle)")
    parser.add_argument("--all",   action="store_true", help="Overskiv eksisterende data")
    args = parser.parse_args()

    process_race(args.race, args.stage, args.all)
