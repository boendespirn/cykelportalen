"""
fix_gradient_sections_backfill.py
Backfiller stage_climbs.gradient_sections, hvor feltet er NULL — se STG-003 i
state/issues.md.

Rodårsag: gpx_climb_agent.py sætter gradient_sections ved indsættelse, men
profile_reader_agent.py sletter og genindsætter ALLE klatringer på en etape
med Claude-vision-data (rigtige navn/længde/gradient) uden nogensinde at sætte
feltet — hvilket i praksis nulstillede det til NULL for stort set enhver
stigning i databasen (bekræftet: 149/149 rækker havde NULL før denne rettelse).
Konsekvens: en stigning uden ClimbFinder-/GPX-genereret profilbillede blev
usynlig i frontendens stignings-faner (se ClimbProfile.tsx hasVisualProfile()),
ikke bare "uden billede".

profile_reader_agent.py er rettet til fremover altid at sætte gradient_sections
ved indsættelse (samme formel, duplikeret bevidst — se filen). Dette script
backfiller de eksisterende rækker uden at køre hele vision/ClimbFinder-
pipelinen om (undgår at genoptage netværkskald og risikoen for at Claude
vision-genlæser et billede anderledes og regresserer i øvrigt korrekt data —
jf. lektionen i STG-007 om at teste ændringer snævert).

Rører KUN gradient_sections. Ingen andre felter (navn, længde, gradient,
elevation_m, profile_image_url, source) læses eller skrives.

Kør (dry-run — viser hvad der ville blive skrevet):
    python agents/fix_gradient_sections_backfill.py

Kør (skriv til DB):
    python agents/fix_gradient_sections_backfill.py --write

Kør for kun ét løb (anbefalet første test, jf. stigningsagentens guardrail
om at teste mod ét løb før hele databasen):
    python agents/fix_gradient_sections_backfill.py --race tour-de-france-2026 --write
"""

import os
import io
import sys
import math
import argparse

import requests
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SB_AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
SB_HEADERS = {**SB_AUTH, "Content-Type": "application/json", "Prefer": "return=minimal"}


# ── Samme formel som profile_reader_agent.py / gpx_climb_agent.py ────────────

def generate_gradient_sections(
    length_km: float,
    avg_gradient: float,
    max_gradient: float | None = None,
) -> list[dict]:
    if not length_km or not avg_gradient:
        return []
    max_gradient = max_gradient or avg_gradient * 1.5

    n_sections = max(2, int(length_km * 2))  # 500m sektioner
    sections = []

    for i in range(n_sections):
        progress = i / n_sections
        sine_factor = math.sin(progress * math.pi * 0.8 + 0.2)
        variation = (hash(f"{i}{avg_gradient}") % 100 - 50) / 250
        gradient = avg_gradient * (0.5 + sine_factor * 0.8) + variation * avg_gradient

        if 0.6 <= progress <= 0.8:
            gradient = min(gradient * 1.3, max_gradient)

        gradient = max(0.5, min(gradient, max_gradient))
        sections.append({"km": round(i * 0.5, 1), "gradient": round(gradient, 1)})

    return sections


# ── Supabase ──────────────────────────────────────────────────────────────────

def get_race_id(race_slug: str) -> str | None:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?slug=eq.{race_slug}&select=id&limit=1",
        headers=SB_AUTH,
    )
    data = res.json()
    return data[0]["id"] if res.ok and data else None


def get_stage_ids_for_race(race_id: str) -> set[str]:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages?race_id=eq.{race_id}&select=id",
        headers=SB_AUTH,
    )
    return {s["id"] for s in res.json()} if res.ok else set()


def get_null_gradient_rows() -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/stage_climbs"
            f"?select=id,name,stage_id,length_km,avg_gradient,max_gradient,profile_image_url"
            f"&gradient_sections=is.null"
            f"&limit=1000&offset={offset}",
            headers=SB_AUTH,
        )
        batch = res.json() if res.ok else []
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return rows


def update_gradient_sections(climb_id: str, sections: list[dict]) -> bool:
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/stage_climbs?id=eq.{climb_id}",
        json={"gradient_sections": sections},
        headers=SB_HEADERS,
    )
    return res.ok


def main(write: bool, race_slug: str | None) -> None:
    stage_filter: set[str] | None = None
    if race_slug:
        race_id = get_race_id(race_slug)
        if not race_id:
            print(f"Løb ikke fundet: {race_slug}")
            return
        stage_filter = get_stage_ids_for_race(race_id)
        print(f"Filtrerer til løb '{race_slug}' ({len(stage_filter)} etaper)")

    rows = get_null_gradient_rows()
    if stage_filter is not None:
        rows = [r for r in rows if r["stage_id"] in stage_filter]

    print(f"stage_climbs med gradient_sections=NULL: {len(rows)}")

    candidates = [r for r in rows if r.get("length_km") and r.get("avg_gradient")]
    skipped = [r for r in rows if r not in candidates]

    print(f"  -> kan genberegnes (har length_km + avg_gradient): {len(candidates)}")
    print(f"  -> springes over (mangler length_km/avg_gradient, intet sikkert at beregne fra): {len(skipped)}")
    if skipped:
        for r in skipped:
            print(f"     ⚠ springer over: {r['name']!r} (length_km={r.get('length_km')}, avg_gradient={r.get('avg_gradient')})")
    print()

    no_image_count = sum(1 for r in candidates if not r.get("profile_image_url"))
    print(f"  Heraf uden profile_image_url (i dag helt usynlige i frontend-fanen): {no_image_count}\n")

    updated, failed = 0, 0
    for row in candidates:
        sections = generate_gradient_sections(
            row["length_km"], row["avg_gradient"], row.get("max_gradient")
        )
        tag = "" if row.get("profile_image_url") else "  [ingen billede — var usynlig]"
        print(f"  {row['name']!r}: {len(sections)} sektioner ({row['length_km']}km @ {row['avg_gradient']}%){tag}")
        if write:
            if update_gradient_sections(row["id"], sections):
                updated += 1
            else:
                failed += 1
                print("    ✗ DB-opdatering fejlede")

    if write:
        print(f"\nFærdig: {updated} opdateret, {failed} fejlede")
    else:
        print(f"\nDry-run — ingen ændringer skrevet. Kør med --write for at rette {len(candidates)} rækker.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Skriv til DB (default: dry-run)")
    parser.add_argument("--race", help="Begræns til ét løb (slug), fx tour-de-france-2026")
    args = parser.parse_args()
    main(args.write, args.race)
