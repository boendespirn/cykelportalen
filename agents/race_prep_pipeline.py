"""
race_prep_pipeline.py
Kører alle agenter, der er nødvendige for at gøre et løb klar til publikation.

Bruger:
  python race_prep_pipeline.py tour-de-suisse                # indeværende sæson, PCS-slug
  python race_prep_pipeline.py tour-de-france --year 2023    # historisk sæson
  python race_prep_pipeline.py tour-de-france --stage 7      # kun én etape

Trinnene står IKKE her. De kommer fra agent_catalog.JOBS["fuld_forberedelse"]
— præcis de samme trin, som knappen "Fuld forberedelse" i admin-dashboardet
kører. Det var en bevidst omlægning 2026-09-09: så længe listen fandtes to
steder, kom de to ud af trit, og denne fil kørte stadig climbfinder_agent.py og
rider_photo_agent.py, længe efter at begge var taget ud af dashboardet. Skal
rækkefølgen ændres, ændres den i agent_catalog.py, og begge veje følger med.

Kør `python agent_catalog.py` for at se de kommandoer, kataloget giver.

Ved --historic tilføjes et afsluttende trin (historic_recap_agent.py), der
skriver den tilbageskuende fortælling til historiske etapesider ud fra vores
egne verificerede resultater sammen med TourTracker-kilden
(se agents/tourtracker_id_map.json).
"""

import subprocess
import sys
import os
import io
import requests
from dotenv import load_dotenv

# Windows' standard konsol-codepage (cp1252) kan ikke encode emoji/pile (▶/✓/✗)
# i print()-kaldene nedenfor — krasjer med UnicodeEncodeError, når stdout ikke
# er en interaktiv UTF-8-terminal (fx redirected til en logfil). Samme fix som
# stage_pcs_agent.py allerede bruger.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

load_dotenv()

# api.py ligger i repo-roden (én mappe over agents/) — tilføj til sys.path så
# vi kan genbruge submit_indexnow() derfra i stedet for at duplikere
# IndexNow-POST-logikken her (jf. SEO-010).
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def notify_indexnow(db_slug: str) -> None:
    """Melder løbets side + alle etapesider til IndexNow (Bing/Yandex) efter en
    pipeline-kørsel, så de nyoprettede/opdaterede sider bliver fundet hurtigere.
    Rammer ikke Google (se SEO-010) — kun et billigt, lavrisiko supplement.
    Fejler aldrig pipelinen: alle fejl fanges og logges, intet trin afbrydes."""
    try:
        from api import submit_indexnow  # genbruger den eksisterende funktion, ingen duplikering

        urls = [f"https://klassementet.dk/{db_slug}"]

        if SUPABASE_URL and SUPABASE_KEY:
            headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
            race_rows = requests.get(
                f"{SUPABASE_URL}/rest/v1/races",
                params={"slug": f"eq.{db_slug}", "select": "id"},
                headers=headers,
                timeout=15,
            ).json()
            if race_rows:
                stage_rows = requests.get(
                    f"{SUPABASE_URL}/rest/v1/stages",
                    params={"race_id": f"eq.{race_rows[0]['id']}", "select": "stage_number"},
                    headers=headers,
                    timeout=15,
                ).json()
                for s in stage_rows:
                    n = s.get("stage_number")
                    if n:
                        urls.append(f"https://klassementet.dk/{db_slug}/stage/{n}")

        submit_indexnow(urls)
        print(f"\n[IndexNow] Meldt {len(urls)} URL'er (løb + etaper) for {db_slug}")
    except Exception as e:
        print(f"\n[IndexNow] Kunne ikke melde URL'er til IndexNow (ikke-kritisk): {e}")


def run(cmd: list[str], label: str, cwd: str | None = None) -> bool:
    print(f"\n{'='*60}")
    print(f"▶ {label}")
    print(f"  {' '.join(cmd)}")
    print("=" * 60)
    result = subprocess.run(cmd, cwd=cwd or os.path.dirname(os.path.abspath(__file__)))
    ok = result.returncode == 0
    print(f"\n{'✓' if ok else '✗'} {label} {'OK' if ok else 'FEJL (fortsætter alligevel)'}")
    return ok


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("pcs_slug", help="PCS race-slug, fx tour-de-suisse")
    parser.add_argument("--year", type=int, default=None,
                        help="Sæsonår, fx 2023 (default: indeværende sæson, jf. startlist_agent.YEAR)")
    parser.add_argument("--stage", type=int, default=None,
                        help="Kør kun for denne etape. Trin, der kun giver mening for hele "
                             "løbet (startliste, rytterstats, TV-tider), springes over.")
    parser.add_argument("--historic", action="store_true",
                        help="Tilføj den historiske fortælling til sidst. Sættes automatisk, "
                             "hvis --year peger på en tidligere sæson end indeværende.")
    args = parser.parse_args()
    pcs_slug = args.pcs_slug.lower().strip()

    from startlist_agent import PCS_TO_DB_SLUG, YEAR as CURRENT_YEAR
    year = args.year if args.year is not None else CURRENT_YEAR
    historic = args.historic or year < CURRENT_YEAR
    db_base = PCS_TO_DB_SLUG.get(pcs_slug, pcs_slug)
    db_slug = f"{db_base}-{year}"

    import agent_catalog

    print("\nRace Prep Pipeline")
    print(f"PCS-slug : {pcs_slug}")
    print(f"DB-slug  : {db_slug}")
    print(f"År       : {year}{' (historisk)' if historic else ''}")
    print(f"Omfang   : {agent_catalog.scope_label(args.stage)}")

    try:
        steps = agent_catalog.build_commands("fuld_forberedelse", db_slug, args.stage)
        if historic:
            steps += agent_catalog.build_commands("historisk_fortaelling", db_slug, args.stage)
    except ValueError as e:
        print(f"\nFEJL: {e}")
        sys.exit(1)

    results = []
    for i, step in enumerate(steps, 1):
        label = f"{i}/{len(steps)} {step['label']}"
        results.append((label, run(step["cmd"], label, step["cwd"])))

    print(f"\n{'='*60}")
    print("Pipeline færdig — oversigt:")
    for label, ok in results:
        print(f"  {'✓' if ok else '✗'} {label}")

    notify_indexnow(db_slug)


if __name__ == "__main__":
    main()
