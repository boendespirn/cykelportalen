"""
race_completeness.py
Beregner, hvor fuldstændigt et løbs data er — målt på hvad vi FAKTISK kan
skaffe, ikke på et teoretisk ideal.

Hvert tjek svarer ét af tre:
  ok           alt der kan skaffes, er skaffet
  mangler      noget mangler, og en agent kan hente det
  ikke_muligt  det findes ikke og kommer aldrig — fx en aflyst etape uden
               resultat, eller et løb helt uden bjergetaper

Den tredje tilstand er ikke pynt. Uden den ville en aflyst etape stå som et
permanent rødt kryds, man lærer at ignorere — og så er hele dashboardet
værdiløst. Et tjek må kun råbe op, når der er noget at gøre ved det.

Alle tjek læses direkte fra databasen. Intet gættes, og intet caches.

Importeres af api.py. Kør `python race_completeness.py <løbs-slug>` for at se
resultatet i terminalen.
"""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

DK_TZ = ZoneInfo("Europe/Copenhagen")


def today_dk() -> str:
    """Dagens dato i dansk tid som ISO-streng. Serveren kører i UTC, og
    date.today() ville derfor kalde gårsdagens etape for "i dag" mellem midnat
    og kl. 02 dansk tid — samme fælde som today_dk() i api.py fanger."""
    return datetime.now(DK_TZ).date().isoformat()

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

OK          = "ok"
MISSING     = "mangler"
IMPOSSIBLE  = "ikke_muligt"

# PostgREST leverer maks. 1000 rækker pr. kald uanset limit. Klassementer
# løber let over det (21 etaper x 4 klassementer x 20 pladser = 1680), så alt
# der kan blive stort, hentes sidevis. Ellers ser høje etapenumre tomme ud.
PAGE = 1000


def _get(path: str, params: str = "") -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        url = f"{SUPABASE_URL}/rest/v1/{path}?{params}&offset={offset}&limit={PAGE}"
        res = requests.get(url, headers=HEADERS, timeout=30)
        if not res.ok:
            return rows
        page = res.json()
        if not isinstance(page, list):
            return rows
        rows += page
        if len(page) < PAGE:
            return rows
        offset += PAGE


def _check(key, label, status, detail, fixed_by=(), missing_items=()):
    return {
        "key": key,
        "label": label,
        "status": status,
        "detail": detail,
        "fixed_by": list(fixed_by),
        "missing_items": list(missing_items)[:25],
    }


def _stage_label(s: dict) -> str:
    return f"E{s['stage_number']}"


def race_completeness(race_slug: str) -> dict | None:
    races = _get("races", f"slug=eq.{race_slug}&select=id,name,slug,start_date,end_date")
    if not races:
        return None
    race = races[0]
    race_id = race["id"]
    today = today_dk()

    stages = _get("stages", f"race_id=eq.{race_id}"
                            f"&select=id,stage_number,date,stage_type,distance_km,"
                            f"start_location,finish_location,elevation_image_source,"
                            f"stage_recap,data_status&order=stage_number.asc")
    # To bevidste afgrænsninger, så et tjek kun råber op, når der er noget at
    # gøre ved det:
    #  - "< today", ikke "<= today": dagens etape er først i mål sidst på
    #    eftermiddagen, og et resultat kan ikke hentes før. Ellers ville
    #    dashboardet lyse rødt hver formiddag under et grand tour.
    #  - data_status: en aflyst etape får aldrig et resultat (Vuelta 2026 E3).
    raced = [s for s in stages
             if s.get("date") and s["date"] < today and not s.get("data_status")]
    todays = [s for s in stages if s.get("date") == today]
    cancelled = [s for s in stages if s.get("data_status")]
    stage_ids = [s["id"] for s in stages]

    startlist = _get("startlists", f"race_id=eq.{race_id}&select=rider_id,team_id,bib_number")
    rider_ids = [r["rider_id"] for r in startlist if r.get("rider_id")]
    riders = []
    # in.() med 150+ uuid'er bliver en meget lang URL — hent i bidder.
    for i in range(0, len(rider_ids), 100):
        chunk = ",".join(rider_ids[i:i + 100])
        riders += _get("riders", f"id=in.({chunk})&select=id,name,photo_url,weight_kg,height_cm")

    results = _get("results", f"race_id=eq.{race_id}&select=stage_id,position")
    classifications = _get("classifications",
                           f"race_id=eq.{race_id}&select=after_stage_number,classification_type")
    climbs = []
    for i in range(0, len(stage_ids), 100):
        chunk = ",".join(stage_ids[i:i + 100])
        climbs += _get("stage_climbs", f"stage_id=in.({chunk})&select=stage_id,profile_image_url")
    broadcasts = _get("broadcast_schedule", f"race_id=eq.{race_id}&select=id")

    checks = [
        _startlist_check(startlist),
        _stage_data_check(stages),
        _stage_profile_check(stages),
        _climbs_check(stages, climbs),
        _climb_profile_check(climbs),
        _rider_photo_check(riders),
        _rider_stats_check(riders),
        _results_check(raced, results),
        _classification_check(raced, classifications),
        _recap_check(raced),
        _tv_check(broadcasts, race),
    ]

    # Fuldstændighed regnes kun over det, der KAN skaffes. Et "ikke muligt"
    # trækker ikke ned — ellers ville et løb blive straffet for virkeligheden.
    actionable = [c for c in checks if c["status"] != IMPOSSIBLE]
    done = [c for c in actionable if c["status"] == OK]
    pct = round(100 * len(done) / len(actionable)) if actionable else 100

    return {
        "race": {
            "slug": race["slug"], "name": race["name"],
            "start_date": race["start_date"], "end_date": race["end_date"],
            "stage_count": len(stages), "raced_count": len(raced),
            "today_stage": todays[0]["stage_number"] if todays else None,
            "cancelled_stages": [s["stage_number"] for s in cancelled],
        },
        "completeness_pct": pct,
        "checks": checks,
    }


# ── De enkelte tjek ──────────────────────────────────────────────────────────

def _startlist_check(startlist):
    if not startlist:
        return _check("startliste", "Startliste", MISSING,
                      "Ingen ryttere hentet", ["startliste"])
    uden_hold = sum(1 for r in startlist if not r.get("team_id"))
    uden_nr   = sum(1 for r in startlist if r.get("bib_number") is None)
    if uden_hold or uden_nr:
        return _check("startliste", "Startliste", MISSING,
                      f"{len(startlist)} ryttere, men {uden_hold} uden hold og {uden_nr} uden startnummer",
                      ["startliste"])
    return _check("startliste", "Startliste", OK, f"{len(startlist)} ryttere med hold og startnummer")


def _stage_data_check(stages):
    if not stages:
        return _check("etapedata", "Etapedata", MISSING, "Ingen etaper oprettet", ["etapedata"])
    mangler = [_stage_label(s) for s in stages
               if not s.get("distance_km") or not s.get("start_location") or not s.get("finish_location")]
    if mangler:
        return _check("etapedata", "Etapedata", MISSING,
                      f"{len(mangler)} af {len(stages)} etaper mangler distance eller by",
                      ["etapedata"], mangler)
    return _check("etapedata", "Etapedata", OK, f"{len(stages)} etaper med distance, start og mål")


def _stage_profile_check(stages):
    if not stages:
        return _check("etapeprofiler", "Højdeprofiler", MISSING, "Ingen etaper endnu", ["etapedata"])
    # Kun egengenererede profiler må vises på sitet (LEG-001) — et PCS-billede
    # tæller derfor ikke som løst.
    mangler = [_stage_label(s) for s in stages if s.get("elevation_image_source") != "generated"]
    if mangler:
        return _check("etapeprofiler", "Højdeprofiler", MISSING,
                      f"{len(mangler)} af {len(stages)} etaper mangler vores egen profil",
                      ["etapeprofiler"], mangler)
    return _check("etapeprofiler", "Højdeprofiler", OK,
                  f"Alle {len(stages)} etaper har egengenereret profil")


def _climbs_check(stages, climbs):
    bjerg = [s for s in stages if s.get("stage_type") in ("mountain", "hilly")]
    if not bjerg:
        return _check("stigninger", "Stigninger", IMPOSSIBLE,
                      "Løbet har ingen bjerg- eller kuperede etaper")
    med_climbs = {c["stage_id"] for c in climbs}
    mangler = [_stage_label(s) for s in bjerg if s["id"] not in med_climbs]
    if mangler:
        return _check("stigninger", "Stigninger", MISSING,
                      f"{len(mangler)} af {len(bjerg)} bjerg-/kuperede etaper har ingen stigninger",
                      ["stigninger_opret"], mangler)
    return _check("stigninger", "Stigninger", OK,
                  f"Alle {len(bjerg)} bjerg-/kuperede etaper har stigninger")


def _climb_profile_check(climbs):
    if not climbs:
        return _check("stigningsprofiler", "Stigningsprofiler", IMPOSSIBLE,
                      "Ingen stigninger oprettet endnu")
    uden = [c for c in climbs if not c.get("profile_image_url")]
    if uden:
        return _check("stigningsprofiler", "Stigningsprofiler", MISSING,
                      f"{len(uden)} af {len(climbs)} stigninger mangler profil",
                      ["stigningsprofiler_cf", "stigningsprofiler_gpx"])
    return _check("stigningsprofiler", "Stigningsprofiler", OK,
                  f"Alle {len(climbs)} stigninger har profil")


def _rider_photo_check(riders):
    if not riders:
        return _check("rytterbilleder", "Rytterbilleder", MISSING,
                      "Ingen ryttere på startlisten endnu", ["startliste"])
    uden = [r["name"] for r in riders if not r.get("photo_url")]
    if uden:
        return _check("rytterbilleder", "Rytterbilleder", MISSING,
                      f"{len(uden)} af {len(riders)} ryttere mangler foto",
                      ["rytterbilleder"], uden)
    return _check("rytterbilleder", "Rytterbilleder", OK, f"Alle {len(riders)} ryttere har foto")


def _rider_stats_check(riders):
    if not riders:
        return _check("rytterstats", "Rytterstats", MISSING,
                      "Ingen ryttere på startlisten endnu", ["startliste"])
    uden = [r["name"] for r in riders if not r.get("weight_kg") or not r.get("height_cm")]
    # PCS har simpelthen ikke vægt/højde på alle ryttere. Under 10% manglende
    # er så godt, som kilden tillader — så råber vi ikke op om det.
    if len(uden) > max(3, 0.10 * len(riders)):
        return _check("rytterstats", "Rytterstats", MISSING,
                      f"{len(uden)} af {len(riders)} ryttere mangler vægt eller højde",
                      ["rytterstats"], uden)
    if uden:
        return _check("rytterstats", "Rytterstats", OK,
                      f"{len(riders) - len(uden)} af {len(riders)} har vægt og højde "
                      f"— resten findes ikke hos kilden")
    return _check("rytterstats", "Rytterstats", OK, f"Alle {len(riders)} ryttere har vægt og højde")


def _results_check(raced, results):
    if not raced:
        return _check("resultater", "Etaperesultater", IMPOSSIBLE, "Ingen etaper kørt endnu")
    per_stage: dict[str, int] = {}
    for r in results:
        per_stage[r["stage_id"]] = per_stage.get(r["stage_id"], 0) + 1
    mangler = [_stage_label(s) for s in raced if per_stage.get(s["id"], 0) < 10]
    if mangler:
        return _check("resultater", "Etaperesultater", MISSING,
                      f"{len(mangler)} af {len(raced)} kørte etaper har under 10 placeringer",
                      ["resultater_alle"], mangler)
    return _check("resultater", "Etaperesultater", OK,
                  f"Top 10 for alle {len(raced)} kørte etaper")


def _classification_check(raced, classifications):
    if not raced:
        return _check("klassementer", "Klassementer", IMPOSSIBLE, "Ingen etaper kørt endnu")
    have = {(c["after_stage_number"], c["classification_type"]) for c in classifications}
    # Kun det samlede klassement kræves for hver etape. Point-, bjerg- og
    # ungdomsklassement findes ikke i alle løb (og bjergklassementet først
    # efter første bjergspurt), så et krav om alle fire ville give falske
    # mangler, man lærer at ignorere.
    mangler = [_stage_label(s) for s in raced if (s["stage_number"], "gc") not in have]
    if mangler:
        return _check("klassementer", "Klassementer", MISSING,
                      f"{len(mangler)} af {len(raced)} kørte etaper mangler samlet klassement",
                      ["resultater_alle"], mangler)
    return _check("klassementer", "Klassementer", OK,
                  f"Samlet klassement efter alle {len(raced)} kørte etaper")


def _recap_check(raced):
    if not raced:
        return _check("referater", "Etapereferater", IMPOSSIBLE, "Ingen etaper kørt endnu")
    mangler = [_stage_label(s) for s in raced if not s.get("stage_recap")]
    if mangler:
        return _check("referater", "Etapereferater", MISSING,
                      f"{len(mangler)} af {len(raced)} kørte etaper mangler referat",
                      ["referater"], mangler)
    return _check("referater", "Etapereferater", OK,
                  f"Referat for alle {len(raced)} kørte etaper")


def _tv_check(broadcasts, race):
    if race.get("end_date") and race["end_date"] < today_dk():
        return _check("tv", "TV-tider", IMPOSSIBLE, "Løbet er afsluttet")
    if not broadcasts:
        return _check("tv", "TV-tider", MISSING, "Ingen sendetider fundet", ["tv_tider"])
    return _check("tv", "TV-tider", OK, f"{len(broadcasts)} sendetider")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Brug: python race_completeness.py <løbs-slug>")
        sys.exit(1)
    data = race_completeness(sys.argv[1])
    if not data:
        print("Løbet blev ikke fundet")
        sys.exit(1)
    print(f"{data['race']['name']} — {data['completeness_pct']}% fuldstændigt "
          f"({data['race']['raced_count']}/{data['race']['stage_count']} etaper kørt)\n")
    icon = {OK: "OK ", MISSING: "!  ", IMPOSSIBLE: "-  "}
    for c in data["checks"]:
        print(f"{icon[c['status']]}{c['label']:<22} {c['detail']}")
        if c["missing_items"]:
            print(f"     {', '.join(c['missing_items'])}")
