"""
cross_course_agent.py — finder det officielle rutekort (parcoursplan) for et
crossløb og gemmer ADRESSEN på arrangørens side i `races.course_map_page`.

VI VISER ALDRIG BILLEDET. Parcoursplanen er arrangørens grafik og dermed deres
ophavsret (CLAUDE.md §7). Landingssiden linker til arrangørens side, hvor
kortet står ("Se rutekortet hos arrangøren"). Ejer-godkendt 2026-11-08 som
trin 1 i docs/plan-cross-rutekort-og-stillinger.md; tilladelse til at vise
billederne er en separat menneskeopgave.

DÆKNING (kontrolleret råt 2026-11-08):
  * X2O Trofee — hvert løbs eget site har planen under /praktische-info/ som
    "…parcoursplan…jpg" (Beringen, Hofstade, Koppenberg). Sitet findes med
    cross_startlist_agent.x2o_site().
  * Superprestige, HG Cross, World Cup — ingen plan fundet på løbssiderne.

AKTUALITET. Siderne genbruges år efter år, og Hofstades side viste
2026-11-08 stadig SIDSTE sæsons plan (uploadet 2025/12). Uploadstien
(/uploads/sites/N/ÅÅÅÅ/MM/) skal derfor ligge i løbets egen sæson (fra 1. juli
før løbet) — ellers linker vi ikke. Et forældet rutekort er værre end intet.

Koer:
    py agents/cross_course_agent.py --alle --dry-run
    py agents/cross_course_agent.py --race x2o-trofee-beringen-2026
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
from datetime import date

import requests
from dotenv import load_dotenv

if (getattr(sys.stdout, "encoding", "") or "").lower().replace("-", "") != "utf8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cross_startlist_agent import hent, x2o_site  # noqa: E402

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
WRITE = {**AUTH, "Content-Type": "application/json", "Prefer": "return=minimal"}

PLAN = re.compile(r'(?:src|href)="([^"]*/uploads/sites/\d+/(\d{4})/(\d{2})/[^"]*parcoursplan[^"]*)"', re.I)


def saesonstart(race_dato: str) -> date:
    d = date.fromisoformat(race_dato)
    return date(d.year if d.month >= 7 else d.year - 1, 7, 1)


def find_plan(race: dict) -> tuple[str | None, str]:
    """(side-url, besked)."""
    if race.get("category") != "X2O Trofee":
        return None, f"serien '{race.get('category')}' udgiver ingen rutekort, vi kender"
    site, besked = x2o_site(race)
    if not site:
        return None, besked
    side = site + "/praktische-info/"
    r = hent(side)
    if r is None or not r.ok:
        return None, f"{side} svarede {r.status_code if r is not None else 'ikke'}"
    fund = PLAN.findall(r.text)
    if not fund:
        return None, f"ingen parcoursplan på {side} endnu"
    _url, aar, md = max(fund, key=lambda f: (f[1], f[2]))
    uploadet = date(int(aar), int(md), 1)
    if uploadet < saesonstart(race["start_date"]):
        return None, (f"planen på {side} er uploadet {aar}-{md} — fra en tidligere sæson, "
                      "linker ikke")
    return side, f"parcoursplan uploadet {aar}-{md}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--race")
    ap.add_argument("--alle", action="store_true")
    ap.add_argument("--dry-run", action="store_true", dest="toer")
    args = ap.parse_args()
    if not SUPABASE_URL or not SUPABASE_KEY:
        sys.exit("SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY mangler")

    flt = (f"&slug=eq.{args.race}" if args.race
           else f"&start_date=gte.{date.today().isoformat()}" if args.alle else None)
    if flt is None:
        ap.error("vaelg --race <slug> eller --alle")
    loeb = requests.get(f"{SUPABASE_URL}/rest/v1/races?select=id,slug,name,category,"
                        f"start_date,course_map_page&race_type=eq.cyclocross{flt}"
                        "&order=start_date", headers=AUTH, timeout=45).json()
    if not loeb:
        # IKKE en fejl: trinnet staar i den faelles forberedelse.
        print(f"{args.race or 'ingen'} er ikke et kommende cykelcross-loeb — springer over")
        return
    for race in loeb:
        side, besked = find_plan(race)
        print(f"[{race['slug']}]  {besked}")
        if side and side != race.get("course_map_page") and not args.toer:
            requests.patch(f"{SUPABASE_URL}/rest/v1/races?id=eq.{race['id']}",
                           json={"course_map_page": side}, headers=WRITE, timeout=45)
            print(f"    ✓ gemt: {side}")


if __name__ == "__main__":
    main()
