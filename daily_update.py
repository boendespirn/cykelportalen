"""
daily_update.py
Daglig opdatering af alle løb: startlister, etaper og datoer.

Logik:
  - Startliste:  opdateres for løb der starter indenfor de næste 90 dage
  - Etaper:      hentes for løb der endnu ikke har etapedata
  - Etaper re-sync: løb med etaper men manglende billeder (PCS opdaterer løbende)
  - Igangværende: noterer hvilke resultat-agenter der bør køres

Kør: python daily_update.py
     python daily_update.py --race tour-de-france
     python daily_update.py --force-stages
     python daily_update.py --startlists-only
"""

import os
import re
import sys
import io
import time
import subprocess
import requests
import argparse
from datetime import date, datetime
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
YEAR = 2026

# ── Komplet mapping: DB-base-slug → PCS-slug ─────────────────────────────────
# DB-slug er vores slug uden årstal (fx "tour-de-france")
# PCS-slug er det ProCyclingStats bruger i deres URLs

RACE_MAP: dict[str, str] = {
    # Grand Tours
    "giro-d-italia":                                    "giro-d-italia",
    "tour-de-france":                                   "tour-de-france",
    "la-vuelta-ciclista-a-espana":                      "vuelta-a-espana",

    # Etapeløb
    "tour-de-suisse":                                   "tour-de-suisse",
    "criterium-du-dauphine":                            "tour-auvergne-rhone-alpes",
    "tour-de-romandie":                                 "tour-de-romandie",
    "paris-nice":                                       "paris-nice",
    "tirreno-adriatico":                                "tirreno-adriatico",
    "volta-ciclista-a-catalunya":                       "volta-a-catalunya",
    "itzulia-basque-country":                           "itzulia-basque-country",
    "uae-tour":                                         "uae-tour",
    "santos-tour-down-under":                           "tour-down-under",
    "tour-de-pologne":                                  "tour-de-pologne",
    "renewi-tour":                                      "renewi-tour",
    "tour-of-guangxi":                                  "tour-of-guangxi",

    # Klassikere
    "strade-bianche":                                   "strade-bianche",
    "milano-sanremo":                                   "milan-san-remo",
    "e3-saxo-classic":                                  "e3-saxo-bank-classic",
    "in-flanders-fields-from-middelkerke-to-wevelgem":  "gent-wevelgem",
    "dwars-door-vlaanderen-a-travers-la-flandre":       "dwars-door-vlaanderen",
    "ronde-van-vlaanderen":                             "tour-of-flanders",
    "paris-roubaix-hauts-de-france":                    "paris-roubaix",
    "amstel-gold-race":                                 "amstel-gold-race",
    "la-fleche-wallonne":                               "la-fleche-wallonne",
    "liege-bastogne-liege":                             "liege-bastogne-liege",
    "eschborn-frankfurt":                               "eschborn-frankfurt",
    "dssk-donostia-san-sebastian-klasikoa":             "donostia-san-sebastian",
    "adac-cyclassics":                                  "cyclassics-hamburg",
    "bretagne-classic-cic":                             "bretagne-classic",
    "grand-prix-cycliste-de-quebec":                    "grand-prix-cycliste-de-quebec",
    "grand-prix-cycliste-de-montreal":                  "grand-prix-cycliste-de-montreal",
    "il-lombardia":                                     "il-lombardia",
    "mapei-cadel-evans-great-ocean-road-race-men":      "cadel-evans-great-ocean-road-race",
    "omloop-nieuwsblad":                                "omloop-het-nieuwsblad",
    "ronde-van-brugge-tour-of-bruges":                  "ronde-van-brugge",
    "copenhagen-sprint":                                "copenhagen-sprint",
}

# ── Supabase helpers ──────────────────────────────────────────────────────────

def sb_get(table: str, params: str, retries: int = 3) -> list:
    for attempt in range(retries):
        try:
            res = requests.get(
                f"{SUPABASE_URL}/rest/v1/{table}?{params}",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                timeout=15,
            )
            return res.json() if res.ok else []
        except Exception as e:
            if attempt < retries - 1:
                print(f"  [DB retry {attempt+1}] {e}")
                time.sleep(3)
            else:
                print(f"  [DB fejl] {e}")
                return []
    return []


def sb_patch(table: str, where: str, data: dict) -> bool:
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/{table}?{where}",
        json=data,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    return res.ok


# ── Subprocess helpers ────────────────────────────────────────────────────────

def notify_indexnow(slug: str, race_id: str) -> None:
    """Melder løbets side + dens etapesider til IndexNow (Bing/Yandex), når
    startliste eller etapedata er blevet oprettet/opdateret for løbet i denne
    kørsel. Rammer ikke Google (se SEO-010) — kun et billigt, lavrisiko
    supplement til crawl-signalet. Fejler aldrig kørslen: alle fejl fanges."""
    try:
        from api import submit_indexnow  # genbruger den eksisterende funktion, ingen duplikering

        urls = [f"https://klassementet.dk/{slug}"]
        stage_rows = sb_get("stages", f"race_id=eq.{race_id}&select=stage_number")
        for s in stage_rows:
            n = s.get("stage_number")
            if n:
                urls.append(f"https://klassementet.dk/{slug}/stage/{n}")

        submit_indexnow(urls)
        print(f"  [IndexNow] Meldt {len(urls)} URL'er")
    except Exception as e:
        print(f"  [IndexNow] Fejl (ikke-kritisk): {e}")


def run_script(script: str, *args: str, label: str = "") -> bool:
    cmd = [sys.executable, script, *args]
    print(f"    → {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, timeout=300, capture_output=False)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"    [TIMEOUT] {label or script}")
        return False
    except Exception as e:
        print(f"    [FEJL] {e}")
        return False


# ── Hoved ─────────────────────────────────────────────────────────────────────

def parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except Exception:
        return None


def get_pcs_slug(db_slug: str) -> str | None:
    base = re.sub(r"-\d{4}$", "", db_slug)
    return RACE_MAP.get(base)


def run(target_slug: str | None = None, force_stages: bool = False, startlists_only: bool = False):
    today = date.today()
    print(f"=== daily_update.py — {today.isoformat()} ===\n")

    # Hent alle løb fra DB
    races = sb_get(
        "races",
        f"start_date=gte.{YEAR}-01-01&start_date=lte.{YEAR}-12-31"
        f"&select=id,slug,name,start_date,end_date,race_type&order=start_date.asc",
    )
    print(f"{len(races)} løb fundet i DB\n")

    ongoing_races = []
    updated_startlists = 0
    updated_stages = 0
    skipped = 0

    for race in races:
        slug = race["slug"]

        # Filtrer til ét løb hvis --race er angivet
        if target_slug and target_slug not in slug:
            continue

        pcs_slug = get_pcs_slug(slug)
        start = parse_date(race["start_date"])
        end   = parse_date(race["end_date"]) or start
        name  = race["name"]

        if not start:
            continue

        days_until = (start - today).days
        is_ongoing = start <= today <= end
        is_past    = end < today

        if is_ongoing:
            ongoing_races.append((name, slug, pcs_slug))

        print(f"{'='*55}")
        print(f"{name}  ({slug})")
        print(f"  Start: {start}  |  Slut: {end}  |  Om: {days_until}d  |  PCS: {pcs_slug or '—'}")

        if not pcs_slug:
            print(f"  ⚠ Ingen PCS-slug — springer over")
            skipped += 1
            print()
            continue

        # Afsluttede løb springes over (startliste er fastlåst)
        if is_past and not force_stages:
            print(f"  [Afsluttet] Springer over")
            print()
            continue

        race_changed = False  # sporer om løbs-/etapesider blev oprettet/opdateret (til IndexNow, SEO-010)

        # ── Startliste ────────────────────────────────────────────────────────
        # Normal: løb indenfor 90 dage. --startlists-only: alle kommende løb.
        if startlists_only:
            run_sl = not is_past
        else:
            run_sl = is_ongoing or (0 <= days_until <= 90)

        if run_sl:
            count_rows = sb_get("startlists", f"race_id=eq.{race['id']}&select=id&limit=1")
            has_startlist = len(count_rows) > 0
            action = "Opdaterer" if has_startlist else "Henter"
            print(f"  [{action} startliste]")
            ok = run_script("startlist_agent.py", pcs_slug, label=f"startlist {slug}")
            if ok:
                updated_startlists += 1
                race_changed = True
            time.sleep(2)  # Kort pause så Supabase ikke throttler
        else:
            print(f"  [Startliste] Starter om {days_until}d — springer over (>90d)")

        if startlists_only:
            if race_changed:
                notify_indexnow(slug, race["id"])
            print()
            continue

        # ── Etapedata ─────────────────────────────────────────────────────────
        # Hent etaper hvis de mangler ELLER force_stages er sat
        stage_rows = sb_get("stages", f"race_id=eq.{race['id']}&select=id,elevation_image_url&limit=1")
        has_stages = len(stage_rows) > 0
        missing_img = has_stages and not stage_rows[0].get("elevation_image_url")

        if not has_stages or force_stages or missing_img:
            reason = "mangler" if not has_stages else ("mangler billeder" if missing_img else "force")
            print(f"  [Etaper — {reason}]")
            is_oneday = race.get("race_type") == "oneday"
            extra_args = ["--oneday"] if is_oneday else []
            ok = run_script("stage_pcs_agent.py", pcs_slug, *extra_args, label=f"stages {slug}")
            if ok:
                updated_stages += 1
                race_changed = True

                # Opdater end_date baseret på seneste etapedato
                max_date_rows = sb_get(
                    "stages",
                    f"race_id=eq.{race['id']}&select=date&order=date.desc&limit=1",
                )
                if max_date_rows and max_date_rows[0].get("date"):
                    new_end = max_date_rows[0]["date"]
                    if new_end != race.get("end_date"):
                        sb_patch("races", f"id=eq.{race['id']}", {"end_date": new_end})
                        print(f"  → end_date opdateret: {new_end}")
        else:
            print(f"  [Etaper] {len(stage_rows)} etaper i DB — OK")

        if race_changed:
            notify_indexnow(slug, race["id"])

        print()

    # ── Opsummering ───────────────────────────────────────────────────────────
    print(f"\n{'='*55}")
    print(f"FÆRDIG  —  {today.isoformat()}")
    print(f"  Startlister opdateret: {updated_startlists}")
    print(f"  Etapedata opdateret:   {updated_stages}")
    print(f"  Springer over (ingen PCS-slug): {skipped}")

    if ongoing_races:
        print(f"\n  Henter resultater for igangværende løb:")
        for r_name, r_slug, r_pcs in ongoing_races:
            if not r_pcs:
                print(f"    • {r_name} — ingen PCS-slug, springer over")
                continue
            year = int(r_slug[-4:]) if r_slug[-4:].isdigit() else YEAR
            print(f"    • {r_name}")
            run_script(
                "giro_results_agent.py",
                "--db-slug", r_slug,
                "--pcs-slug", r_pcs,
                "--year", str(year),
                label=f"results {r_slug}",
            )

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--race",           help="Kør kun ét løb (del af slug)")
    parser.add_argument("--force-stages",   action="store_true", help="Gen-scrape etaper for alle løb")
    parser.add_argument("--startlists-only",action="store_true", help="Kør kun startliste-opdatering")
    args = parser.parse_args()

    run(
        target_slug=args.race,
        force_stages=args.force_stages,
        startlists_only=args.startlists_only,
    )
