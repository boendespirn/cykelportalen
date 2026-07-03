"""
fix_elevation_gain_backfill.py
Retter stage_climbs.elevation_m, hvor feltet fejlagtigt indeholder stigningens
tophøjde (summit altitude over havet) i stedet for højdemeter klatret (gain).
Se STG-007 i state/issues.md for baggrund og udbredelse (118/129 ramte rækker
på tværs af hele databasen, ikke kun Tour de France).

Genberegner elevation_m = round(length_km * avg_gradient * 10) for enhver
række hvor både length_km og avg_gradient findes, og nuværende elevation_m
afviger markant fra den beregnede værdi (mistænkelig for at være altitude).
Rører aldrig rækker uden length_km/avg_gradient — der er intet sikkert at
genberegne fra.

Kør (dry-run — viser alle ændringer uden at skrive):
    python agents/fix_elevation_gain_backfill.py

Kør (skriv til DB):
    python agents/fix_elevation_gain_backfill.py --write
"""

import os
import io
import sys
import argparse

import requests
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SB_AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
SB_HEADERS = {**SB_AUTH, "Content-Type": "application/json", "Prefer": "return=minimal"}

# Samme heuristik som brugt i audit-kørslen der opdagede bugget:
# elevation_m er mistænkelig, hvis den er markant større end det, længde og
# gennemsnitshældning alene kan forklare som klatrede højdemeter.
RATIO_THRESHOLD = 1.6
ABS_DIFF_THRESHOLD = 250


def get_all_climbs() -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/stage_climbs"
            f"?select=id,name,length_km,avg_gradient,elevation_m"
            f"&elevation_m=not.is.null&length_km=not.is.null&avg_gradient=not.is.null"
            f"&limit=1000&offset={offset}",
            headers=SB_AUTH,
        )
        batch = res.json() if res.ok else []
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return rows


def find_suspect_rows(rows: list[dict]) -> list[tuple[dict, int]]:
    suspects = []
    for r in rows:
        expected_gain = r["length_km"] * r["avg_gradient"] * 10
        if expected_gain <= 0:
            continue
        actual = r["elevation_m"]
        ratio = actual / expected_gain
        if ratio > RATIO_THRESHOLD or (actual - expected_gain) > ABS_DIFF_THRESHOLD:
            suspects.append((r, round(expected_gain)))
    return suspects


def update_elevation(climb_id: str, new_value: int) -> bool:
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/stage_climbs?id=eq.{climb_id}",
        json={"elevation_m": new_value},
        headers=SB_HEADERS,
    )
    return res.ok


def main(write: bool) -> None:
    rows = get_all_climbs()
    print(f"stage_climbs med elevation_m + length_km + avg_gradient: {len(rows)}")

    suspects = find_suspect_rows(rows)
    print(f"Mistænkelige rækker (elevation_m ligner tophøjde, ikke gain): {len(suspects)}\n")

    updated, failed = 0, 0
    for row, expected in sorted(suspects, key=lambda x: -x[0]["elevation_m"]):
        old = row["elevation_m"]
        print(f"  {row['name']!r}: {old}m → {expected}m "
              f"(len={row['length_km']}km, grad={row['avg_gradient']}%)")
        if write:
            if update_elevation(row["id"], expected):
                updated += 1
            else:
                failed += 1
                print("    ✗ DB-opdatering fejlede")

    if write:
        print(f"\nFærdig: {updated} opdateret, {failed} fejlede")
    else:
        print(f"\nDry-run — ingen ændringer skrevet. Kør med --write for at rette {len(suspects)} rækker.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Skriv de rettede værdier til DB (default: dry-run)")
    args = parser.parse_args()
    main(args.write)
