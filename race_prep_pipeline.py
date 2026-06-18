"""
race_prep_pipeline.py
Kører alle agenter der er nødvendige for at gøre et løb klar til publikation.

Bruger:
  python race_prep_pipeline.py tour-de-suisse        # bruger PCS-slug
  python race_prep_pipeline.py tour-de-france
  python race_prep_pipeline.py giro-d-italia

Pipeline-trin (i rækkefølge):
  1. Startliste         — henter alle ryttere med bib-numre fra PCS
  2. Etapedata          — bekræfter/opdaterer etaper og profilbilleder
  3. Høj-kval profiler  — erstatter lave PCS-profiler med /info/profiles versioner
  4. Rytterbilleder     — opdaterer manglende/brudte fotos fra PCS
  5. Rytterstats        — henter vægt og højde for ryttere der mangler det
  6. Stigningsprofiler  — ClimbFinder-profiler for individuelle stigninger

Kør resultater separat (løbende under løbet):
  python giro_results_agent.py --db-slug RACE-SLUG-2026 --pcs-slug PCS-SLUG --stages N
"""

import subprocess
import sys
import os


def run(cmd: list[str], label: str) -> bool:
    print(f"\n{'='*60}")
    print(f"▶ {label}")
    print(f"  {' '.join(cmd)}")
    print("=" * 60)
    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))
    ok = result.returncode == 0
    print(f"\n{'✓' if ok else '✗'} {label} {'OK' if ok else 'FEJL (fortsætter alligevel)'}")
    return ok


def main():
    if len(sys.argv) < 2:
        print("Brug: python race_prep_pipeline.py <pcs-slug>")
        print("Eks:  python race_prep_pipeline.py tour-de-suisse")
        sys.exit(1)

    pcs_slug = sys.argv[1].lower().strip()

    from startlist_agent import PCS_TO_DB_SLUG, YEAR
    db_base = PCS_TO_DB_SLUG.get(pcs_slug, pcs_slug)
    db_slug = f"{db_base}-{YEAR}"

    print(f"\nRace Prep Pipeline")
    print(f"PCS-slug : {pcs_slug}")
    print(f"DB-slug  : {db_slug}")
    print(f"År       : {YEAR}")

    py = sys.executable

    steps = [
        (
            [py, "startlist_agent.py", pcs_slug],
            "1/6 Startliste (PCS)",
        ),
        (
            [py, "stage_pcs_agent.py", pcs_slug],
            "2/6 Etapedata og basisprofilbilleder (PCS)",
        ),
        (
            [py, "pcs_profile_image_agent.py", "--race", db_slug, "--overwrite"],
            "3/6 Høj-kvalitets profilbilleder (/info/profiles)",
        ),
        (
            [py, "rider_photo_agent.py", "--race", db_slug],
            "4/6 Rytterbilleder",
        ),
        (
            [py, "rider_stats_agent.py", "--race", db_slug],
            "5/6 Rytterstats (vægt + højde)",
        ),
        (
            [py, "climbfinder_agent.py", "--race", db_slug],
            "6/6 Stigningsprofiler (ClimbFinder)",
        ),
    ]

    results = []
    for cmd, label in steps:
        ok = run(cmd, label)
        results.append((label, ok))

    print(f"\n{'='*60}")
    print("Pipeline færdig — oversigt:")
    for label, ok in results:
        print(f"  {'✓' if ok else '✗'} {label}")

    print(f"\nNæste trin når løbet kører:")
    print(f"  python giro_results_agent.py --db-slug {db_slug} --pcs-slug {pcs_slug} --stages N")
    print(f"  (kør efter hver etape er afsluttet)")


if __name__ == "__main__":
    main()
