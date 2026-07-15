"""
build_tourtracker_id_map.py
Bygger en mapping mellem vores DB-slugs (races.slug, fx "tour-de-france-2024")
og TourTracker's interne tour-ID (fx 978), som bruges til at hente
etape-recaps/live-kommentering til historiske etapesiders narrativ
(se docs/superpowers/specs/2026-07-15-historiske-etapesider-letvaegt.md).

TourTracker (live.tourtrackerprocycling.com) er en SPA uden per-løb-URL'er,
men hele kalenderen (2013-2026, alle løb, med interne ID'er) kan hentes i ét
kald fra:
  https://secure.tourtrackerdata.com/apps/cyclingnews/2021/jsonp/tours.jsonp
("2021" i stien er en app-versionsidentifikator, ikke et årstalsfilter —
svaret indeholder alle år på én gang.)

Matcher på: samme år + start-dato inden for ±5 dage + navne-lighed
(normaliseret, accent-/suffiks-uafhængig), kun gender=men (TourTracker
blander herre-/dameløb, vores races-tabel er kun herreløb).

Kør: python build_tourtracker_id_map.py
Output: agents/tourtracker_id_map.json ({db_slug: tourtracker_id, ...})
        + konsol-rapport over umatchede DB-løb og lav-tillid-matches til manuelt tjek.
"""

import os
import re
import json
import unicodedata
from datetime import datetime, timedelta
from difflib import SequenceMatcher

import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

TOURS_URL = "https://secure.tourtrackerdata.com/apps/cyclingnews/2021/jsonp/tours.jsonp"


def normalize(name: str) -> str:
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = name.lower()
    # Fjern kendte suffikser/varianter der forstyrrer navne-sammenligning
    name = re.sub(r"\b(me|men|women|femmes|ladies|feminin[e]?|gree|cic|mapei|santos|adac|bemer|dssk)\b", "", name)
    name = re.sub(r"[^a-z0-9]+", " ", name).strip()
    return name


def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def fetch_our_races() -> list[dict]:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races",
        params={"select": "slug,name,start_date,category", "order": "start_date"},
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
    )
    res.raise_for_status()
    return res.json()


def fetch_tourtracker_tours() -> list[dict]:
    res = requests.get(TOURS_URL, headers={"User-Agent": "Mozilla/5.0"})
    res.raise_for_status()
    text = res.text
    json_str = text[text.index("(") + 1 : text.rindex(")")]
    data = json.loads(json_str)
    tours = data["tours"]["tour"]
    out = []
    for t in tours:
        if t.get("gender") != "men":
            continue
        try:
            start = datetime.utcfromtimestamp(int(t["startTime"]) / 1000)
        except (KeyError, ValueError):
            continue
        out.append({"id": t["id"], "name": t["name"], "start": start, "adminName": t.get("adminName", "")})
    return out


def main():
    our_races = fetch_our_races()
    tt_tours = fetch_tourtracker_tours()
    print(f"DB-løb: {len(our_races)} | TourTracker-løb (men): {len(tt_tours)}")

    mapping: dict[str, str] = {}
    unmatched: list[str] = []
    low_confidence: list[str] = []

    for race in our_races:
        race_start = datetime.strptime(race["start_date"], "%Y-%m-%d")
        candidates = [t for t in tt_tours if abs((t["start"] - race_start).days) <= 5]
        if not candidates:
            unmatched.append(f"{race['slug']} ({race['name']}, {race['start_date']}) — ingen TT-løb inden for ±5 dage")
            continue

        scored = sorted(
            ((name_similarity(race["name"], c["name"]), c) for c in candidates),
            key=lambda x: -x[0],
        )
        best_score, best = scored[0]

        if best_score < 0.5:
            unmatched.append(
                f"{race['slug']} ({race['name']}, {race['start_date']}) — bedste kandidat "
                f"'{best['name']}' (id {best['id']}) kun {best_score:.2f} lighed, sprunget over"
            )
            continue

        mapping[race["slug"]] = best["id"]
        if best_score < 0.75:
            low_confidence.append(
                f"{race['slug']} -> id {best['id']} ('{best['name']}'), lighed {best_score:.2f} — verificér manuelt"
            )

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tourtracker_id_map.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2, sort_keys=True, ensure_ascii=False)

    print(f"\nMatchet {len(mapping)}/{len(our_races)} løb -> {out_path}")

    if low_confidence:
        print(f"\n{len(low_confidence)} lav-tillid-matches (lighed < 0.75, verificér manuelt):")
        for line in low_confidence:
            print(f"  ? {line}")

    if unmatched:
        print(f"\n{len(unmatched)} umatchede DB-løb:")
        for line in unmatched:
            print(f"  x {line}")


if __name__ == "__main__":
    main()
