"""
race_prep_pipeline.py
Kører alle agenter der er nødvendige for at gøre et løb klar til publikation.

Bruger:
  python race_prep_pipeline.py tour-de-suisse                # indeværende sæson, bruger PCS-slug
  python race_prep_pipeline.py tour-de-france
  python race_prep_pipeline.py giro-d-italia
  python race_prep_pipeline.py tour-de-france --year 2023    # historisk sæson

Pipeline-trin (i rækkefølge):
  1. Startliste         — henter alle ryttere med bib-numre fra PCS
  2. Etapedata          — bekræfter/opdaterer etaper og profilbilleder
  3. Høj-kval profiler  — erstatter lave PCS-profiler med /info/profiles versioner
  4. Rytterbilleder     — opdaterer manglende/brudte fotos fra PCS
  5. Rytterstats        — henter vægt og højde for ryttere der mangler det
  6. Stigninger (opret) — gpx_climb_agent.py. OPRETTER stage_climbs-rækkerne i
                          første omgang (klatreinfo + gradient_sections fra PCS).
                          Uden dette trin har trin 7-8 intet at arbejde på — de
                          tilføjer kun billeder til allerede eksisterende rækker
                          (se STG-023, fundet 2026-07-15 under SEO-022-backfillen).
  7. Stigningsprofiler  — ClimbFinder-profiler for individuelle stigninger
  8. Stigningsprofiler-fallback — climb_profile_generator.py (GPX-baseret) for
                          stigninger ClimbFinder ikke fandt/verificerede.
                          Springer automatisk og ufarligt over løb uden
                          konfigureret GPX-kilde (se CYCLINGSTAGE_GPX_PAGES).
  9. Resultater          — results_agent.py --all-stages. For et afsluttet (historisk)
                          løb hentes samtlige etapers resultater+klassement i denne
                          kørsel, i modsætning til den løbende opdatering under et
                          igangværende løb (som i stedet kører uden --all-stages,
                          løbende efter hver etape — se docstring i results_agent.py).

Ved --historic (letvægts-flow, jf. docs/superpowers/specs/2026-07-15-historiske-
etapesider-letvaegt.md): trin 6-8 (individuelle stigningsprofiler) springes bevidst
over — det var den reelle flaskehals for at levere historiske sider hurtigt, og
historiske sider viser kun hel-etape-højdeprofilen (fra trin 2), ikke pr.-stigning-
nedbrydning. I stedet tilføjes et nyt afsluttende trin:
 10. Historisk fortælling — historic_recap_agent.py --all-stages. Kører EFTER
                          resultater (trin 9), da narrativ-agenten bruger vores
                          egne verificerede etaperesultater som faktuel grundlag
                          sammen med TourTracker-kilden (se agents/tourtracker_id_map.json).

Bemærk: `--year` er kun understøttet af trin 1-2 (startlist_agent.py/stage_pcs_agent.py),
som er de eneste trin, der tager et bart PCS-slug og selv skal udlede DB-slug/PCS-URL.
Trin 3-9 tager alle `--race DB-SLUG` (som allerede indeholder årstallet, fx
"tour-de-france-2023") og er derfor årgang-agnostiske i sig selv.

Ikke inkluderet endnu (fremtidig forbedring, ikke blokerende): `profile_reader_agent.py`
(Claude vision-baseret genlæsning af klatredata fra højdeprofil-billedet, mere
præcis end gpx_climb_agent.py's rå PCS-scrape) og `veloviewer_agent.py`
(Strava-segment-baseret visuel profil, nu prioritet 1 for 2026 jf. STG-020) —
begge kan tilføjes som selvstændige forbedringstrin senere uden at blokere
selve klatre-opret-trinnet (6) ovenfor.
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
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("pcs_slug", help="PCS race-slug, fx tour-de-suisse")
    parser.add_argument("--year", type=int, default=None,
                         help="Sæsonår, fx 2023 (default: indeværende sæson, jf. startlist_agent.YEAR)")
    parser.add_argument("--historic", action="store_true",
                         help="Kør resultat-trinnet (9/9) med --all-stages i stedet for kun seneste etape, "
                              "og spring rytterbilleder (4/9) over, da de sjældnere er relevante for gamle sæsoner. "
                              "Sættes automatisk til True hvis --year peger på en tidligere sæson end indeværende.")
    args = parser.parse_args()
    pcs_slug = args.pcs_slug.lower().strip()

    from startlist_agent import PCS_TO_DB_SLUG, YEAR as CURRENT_YEAR
    year = args.year if args.year is not None else CURRENT_YEAR
    historic = args.historic or year < CURRENT_YEAR
    db_base = PCS_TO_DB_SLUG.get(pcs_slug, pcs_slug)
    db_slug = f"{db_base}-{year}"

    print(f"\nRace Prep Pipeline")
    print(f"PCS-slug : {pcs_slug}")
    print(f"DB-slug  : {db_slug}")
    print(f"År       : {year}{' (historisk)' if historic else ''}")

    py = sys.executable
    year_args = ["--year", str(year)]

    steps = [
        (
            [py, "startlist_agent.py", pcs_slug, *year_args],
            "1/9 Startliste (PCS)",
        ),
        (
            [py, "stage_pcs_agent.py", pcs_slug, *year_args],
            "2/9 Etapedata og basisprofilbilleder (PCS)",
        ),
        (
            [py, "pcs_profile_image_agent.py", "--race", db_slug, "--overwrite"],
            "3/9 Høj-kvalitets profilbilleder (/info/profiles)",
        ),
        (
            [py, "rider_photo_agent.py", "--race", db_slug],
            "4/9 Rytterbilleder",
        ),
        (
            [py, "rider_stats_agent.py", "--race", db_slug],
            "5/9 Rytterstats (vægt + højde)",
        ),
        (
            [py, "gpx_climb_agent.py", "--race", db_slug],
            "6/9 Stigninger — opret stage_climbs-rækker (PCS)",
        ),
        (
            [py, "climbfinder_agent.py", "--race", db_slug],
            "7/9 Stigningsprofiler (ClimbFinder)",
        ),
        (
            [py, "climb_profile_generator.py", "--race", db_slug, "--all",
             "--style", "full", "--write-db"],
            "8/9 Stigningsprofiler-fallback (GPX-generator)",
        ),
        (
            [py, "results_agent.py", "--race", db_slug, *(["--all-stages"] if historic else [])],
            "9/9 Resultater + klassement" + (" (alle etaper, historisk)" if historic else " (seneste etape)"),
        ),
    ]

    # Rytterbilleder er lavere prioritet for historiske sæsoner (mange ryttere
    # stoppet, ingen SEO-værdi i friske fotos af en gammel startliste) — spring
    # trinnet over ved --historic i stedet for at bruge tid/PCS-kald på det.
    # Stignings-trinnene (6-8) springes også over ved --historic — historiske
    # sider viser bevidst ikke individuelle stigningsprofiler (se spec i
    # docstringen ovenfor); det var den reelle flaskehals for hurtig levering.
    if historic:
        skip_prefixes = ("4/9", "6/9", "7/9", "8/9")
        steps = [(cmd, label) for cmd, label in steps if not label.startswith(skip_prefixes)]
        steps.append((
            [py, "historic_recap_agent.py", "--race", db_slug, "--all-stages"],
            "10/9 Historisk fortælling (narrativ-agent)",
        ))

    results = []
    for cmd, label in steps:
        ok = run(cmd, label)
        results.append((label, ok))

    print(f"\n{'='*60}")
    print("Pipeline færdig — oversigt:")
    for label, ok in results:
        print(f"  {'✓' if ok else '✗'} {label}")

    if not historic:
        print(f"\nNæste trin når løbet kører:")
        print(f"  python results_agent.py --race {db_slug}")
        print(f"  (kør efter hver etape er afsluttet, uden --all-stages)")

    notify_indexnow(db_slug)


if __name__ == "__main__":
    main()
