"""
edgecycling_agent.py — officiel loebs- og etapedata fra arrangoerens eget API.

Tour of Guangxi koeres af Wanda Sports, og deres site (tourofguangxi.com.cn) er
en React-app, der henter alt fra `cycling.edgecycling.cn`. Det er den eneste
kilde til loebet: cyclingstage har ingen GPX (DATA-003), og arrangoerens eget
`gpxUrl`-felt er TOMT for baade 2025 og 2026 — kun 2024 har filer. Knappen
"GPX" paa /route renderes alligevel ubetinget, saa den ser ud til at virke,
men har intet href. Verificeret 2026-10-14 paa alle seks etaper, baade paa
`queryAll4Web` og `queryById4Web`, og i live-DOM.

Til gengaeld udstiller API'et to billeder pr. etape, som er mere vaerd:

  * `elevationChart` — hel-etape-profil med markoerer og km-akse. Digitaliseres
    af `profile_image_digitizer.py` (stil "edgecycling") og tegnes i VORES eget
    design af `stage_profile_generator.py`.
  * `slopeMap` — én stigningsprofil pr. KOM med kategori, km, laengde og
    gennemsnitshaeldning. Tallene er aflaest én gang og ligger i
    `profile_image_anchors.json`, saa de er sporbare (CLAUDE.md §6).

Vi udtraekker FAKTA og viser aldrig kildebilledet (CLAUDE.md §7) — samme
skelnen som `aso_roadbook_agent.py` og `profile_image_digitizer.py`.

Brug:
    py agents/edgecycling_agent.py --race tour-of-guangxi-2026 [--write-db]

Uden --write-db skrives intet; agenten viser kun, hvad den ville gemme.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SB_AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

API = "https://cycling.edgecycling.cn"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129 Safari/537.36")
HEADERS = {"User-Agent": UA, "Referer": "https://www.tourofguangxi.com.cn/",
           "X-Requested-With": "XMLHttpRequest"}

ANCHOR_FILE = Path(__file__).with_name("profile_image_anchors.json")

# Loeb paa denne platform -> arrangoerens serie-id. Serien rummer alle aargange,
# saa agenten finder selv naeste aars raceId uden en kodeaendring.
SERIES = {"tour-of-guangxi": "1802953069501599746"}

# Arrangoerens stageType -> vores stage_type.
STAGE_TYPE = {0: "flat", 1: "mountain", 2: "hilly", 3: "itt", 4: "ttt"}


def _get(path: str):
    res = requests.get(f"{API}{path}", headers=HEADERS, timeout=60)
    res.raise_for_status()
    body = res.json()
    if not body.get("success"):
        raise RuntimeError(f"API-fejl paa {path}: {body.get('message')}")
    return body["result"]


def resolve_race_id(series_key: str, year: int) -> str | None:
    """Aargangen findes paa startdatoens aar, ikke paa navnet — arrangoeren
    staver loebsnavnet forskelligt fra aar til aar (2024-raekken hedder 'ceshi'
    paa engelsk), saa et navnematch ville vaere skroebeligt."""
    for race in _get(f"/pro/proRaces/queryBySeriesId?seriesId={SERIES[series_key]}"):
        if (race.get("startDate") or "").startswith(str(year)):
            return race["id"]
    return None


def fetch_stages(race_id: str) -> list[dict]:
    out = []
    for s in _get(f"/pro/proStages/queryAll4Web?raceId={race_id}"):
        out.append(_get(f"/pro/proStages/queryById4Web?id={s['id']}"))
    return sorted(out, key=lambda s: s["serialNum"])


# ── Supabase ─────────────────────────────────────────────────────────────────

def _sb(method: str, path: str, **kw):
    res = requests.request(method, f"{SUPABASE_URL}/rest/v1/{path}",
                           headers={**SB_AUTH, "Content-Type": "application/json",
                                    "Prefer": "return=representation"},
                           timeout=60, **kw)
    res.raise_for_status()
    return res.json() if res.text else []


def get_race(slug: str) -> dict | None:
    rows = _sb("GET", f"races?slug=eq.{slug}&select=id,slug,start_date&limit=1")
    return rows[0] if rows else None


def get_db_stages(race_id: str) -> dict[int, dict]:
    rows = _sb("GET", f"stages?race_id=eq.{race_id}&select=id,stage_number&order=stage_number")
    return {r["stage_number"]: r for r in rows}


def _place(name: str) -> str:
    """str.title() skriver stort efter apostrof ("Tian'e" -> "Tian'E"), saa
    byen Tian'e blev stavet forkert paa etape 4. Vi skriver kun stort efter
    mellemrum og bindestreg."""
    out, cap = [], True
    for ch in (name or "").lower():
        out.append(ch.upper() if cap and ch.isalpha() else ch)
        cap = ch in " -"
    return "".join(out)


def climb_name(cat: str, summit_km: float, total_km: float, finish: str) -> str:
    """Arrangoeren udgiver INGEN navne paa stigningerne — kun kategori og km.
    Et opfundet navn ville vaere praecis den slags fejl, §6 forbyder, saa vi
    bruger den officielle betegnelse. Maalstigningen faar dog maalbyens navn,
    som er en faktisk, officiel oplysning."""
    if finish and abs(total_km - summit_km) <= 2.0:
        return finish
    km = f"{summit_km:.1f}".replace(".", ",")
    return f"KOM {cat}. kat. (km {km})"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--race", required=True, help="vores DB-slug, fx tour-of-guangxi-2026")
    ap.add_argument("--write-db", action="store_true")
    args = ap.parse_args()

    slug = args.race
    series_key, _, year = slug.rpartition("-")
    if series_key not in SERIES:
        sys.exit(f"✗ {series_key} er ikke konfigureret i SERIES")

    race = get_race(slug)
    if not race:
        sys.exit(f"✗ loebet {slug} findes ikke i databasen")
    db_stages = get_db_stages(race["id"])
    if not db_stages:
        sys.exit(f"✗ {slug} har ingen etaperaekker i databasen")

    race_id = resolve_race_id(series_key, int(year))
    if not race_id:
        sys.exit(f"✗ ingen {year}-aargang hos arrangoeren")
    print(f"arrangoerens raceId for {year}: {race_id}")

    anchors = json.loads(ANCHOR_FILE.read_text(encoding="utf-8")).get(slug, {})
    cfg_stages = anchors.get("stages", {})

    stages = fetch_stages(race_id)
    print(f"hentede {len(stages)} etaper\n")

    for s in stages:
        n = s["serialNum"]
        row = db_stages.get(n)
        if not row:
            print(f"✗ etape {n} findes ikke i databasen — springer over")
            continue
        total_km = round(s["routeMeter"] / 1000, 1)
        payload = {
            "date": (s.get("raceDay") or "")[:10] or None,
            "start_location": _place(s.get("startPointEn")) or None,
            "finish_location": _place(s.get("endPointEn")) or None,
            "distance_km": total_km,
            "elevation_gain_m": s.get("routeClimb"),
            "stage_type": STAGE_TYPE.get(s.get("stageType")),
            "stage_start_time": (s.get("startTime") or "")[11:19] or None,
            "source": "edgecycling",
            "source_url": "https://www.tourofguangxi.com.cn/route",
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        print(f"etape {n}: {payload.get('start_location')} -> {payload.get('finish_location')}  "
              f"{total_km} km  D+{payload.get('elevation_gain_m')}  "
              f"{payload.get('stage_type')}  start {payload.get('stage_start_time')}")

        climbs = cfg_stages.get(str(n), {}).get("climbs", [])
        rows = []
        for i, c in enumerate(sorted(climbs, key=lambda c: c["summit_km"])):
            summit = float(c["summit_km"])
            length = float(c["length_km"])
            grad = float(c["avg_gradient"])
            rows.append({
                "stage_id": row["id"],
                # km_from_start er stigningens FOD; arrangoeren angiver toppen.
                "km_from_start": round(summit - length, 1),
                "length_km": length,
                "avg_gradient": grad,
                "elevation_m": round(length * grad * 10),   # hoejdegevinst
                "category": c["category"],
                "name": climb_name(c["category"], summit, total_km,
                                   payload.get("finish_location", "")),
                "sort_order": i,
                "source": "edgecycling",
            })
        for r in rows:
            print(f"    {r['name']}: fod km {r['km_from_start']}, "
                  f"{r['length_km']} km @ {r['avg_gradient']}% = {r['elevation_m']} m "
                  f"(kat. {r['category']})")

        if args.write_db:
            _sb("PATCH", f"stages?id=eq.{row['id']}", json=payload)
            # Stigningerne erstattes samlet: kilden er autoritativ for hele
            # etapen, og en delvis opdatering ville efterlade gamle raekker.
            _sb("DELETE", f"stage_climbs?stage_id=eq.{row['id']}&source=eq.edgecycling")
            if rows:
                _sb("POST", "stage_climbs", json=rows)
            print("    -> gemt")
        print()

    if not args.write_db:
        print("(intet gemt — koer med --write-db)")


if __name__ == "__main__":
    main()
