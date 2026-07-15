"""
historic_recap_agent.py
Genererer en original, dansk historisk fortælling ("historic_recap") for
afsluttede (historiske) etaper via Anthropic API (Claude) — se
docs/superpowers/specs/2026-07-15-historiske-etapesider-letvaegt.md og
state/backfill-fremdrift.md.

Kildegrundlag (i prioriteret rækkefølge):
  1. TourTracker (secure.tourtrackerdata.com) — kort redaktionel recap
     ("reports") + blow-by-blow-kommentering ("plays"), slået op via
     agents/tourtracker_id_map.json (races.slug -> TourTracker tour-ID).
     Bruges KUN som faktuel funderingskilde — teksten omskrives altid til
     original, egen tekst (CLAUDE.md §7, copyright).
  2. Vores egen DB (stages + results) — altid tilgængelig, altid verificeret.
     Bruges alene, hvis der ikke findes en TourTracker-mapping for løbet,
     eller hvis TourTracker ikke har en rapport for netop denne etape.

"Kendt/nyhedsværdig etape"-kriterium (spec-afsnit "Åbent spørgsmål", afklaret
via heuristik i denne fil): TourTracker-rapporten skal være til stede OG have
en vis længde/informationstæthed (>= 250 tegn), før vi skriver en fuld
fortælling. Ellers en kort, ærlig faktuel opsummering — aldrig opdigtet.

Krav:
  - ANTHROPIC_API_KEY i .env

Kør:
  python historic_recap_agent.py --race tour-de-france-2025 --stage 10   (én etape)
  python historic_recap_agent.py --race tour-de-france-2025 --all-stages  (hele løbet)
  python historic_recap_agent.py --race tour-de-france-2025 --all-stages --force  (regenerér)

Re-run er sikkert: henter som standard kun etaper med historic_recap = NULL.
"""

import os
import sys
import io
import re
import json
import time
import random
import argparse
import requests
from anthropic import Anthropic
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL  = os.getenv("SUPABASE_URL")
SUPABASE_KEY  = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")

DB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}
READ_HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

MODEL = "claude-haiku-4-5-20251001"  # billig og hurtig; skift til claude-sonnet-5 for højere kvalitet

TT_MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tourtracker_id_map.json")
TT_HEADERS = {"User-Agent": "Mozilla/5.0"}
REPORT_URL = "https://secure.tourtrackerdata.com/tours/{tour_id}/jsonp/reports/stage{n}reports.jsonp"
PLAYS_URL  = "https://secure.tourtrackerdata.com/tours/{tour_id}/jsonp/plays/stage{n}plays.jsonp"

FULL_THRESHOLD = 250  # tegn — under denne længde regnes TourTracker-rapporten ikke som "har noget at fortælle"

DELAY = 0.5  # sekunder mellem Claude-kald

# Vinkler til at variere fortællingens indgang på tværs af etaper (SEO: undgå
# duplicate content; brand: undgå skabelonfølelse, jf. spec-krav om variation).
ANGLES = [
    "start med det afgørende angreb eller opgør i finalen",
    "start med den overordnede stemning og situationen i feltet ved start",
    "start med hvordan ruten/terrænet satte scenen for etapen",
    "start med en enkelt rytters perspektiv eller nøglemoment",
    "start med det dramatiske vendepunkt midt i etapen",
    "start med resultatet og gå derefter tilbage til hvordan det skete",
]


# ── TourTracker-mapping ─────────────────────────────────────────────────────

def load_tt_map() -> dict:
    if not os.path.exists(TT_MAP_PATH):
        return {}
    with open(TT_MAP_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_jsonp(text: str) -> dict | None:
    try:
        return json.loads(text[text.index("(") + 1 : text.rindex(")")])
    except (ValueError, json.JSONDecodeError):
        return None


def fetch_tt_report(tour_id: str, stage_number: int) -> str | None:
    try:
        r = requests.get(REPORT_URL.format(tour_id=tour_id, n=stage_number), headers=TT_HEADERS, timeout=15)
        if not r.ok:
            return None
        data = parse_jsonp(r.text)
        text = data.get("reports", {}).get("report", {}).get("text") if data else None
        return text.strip() if text else None
    except requests.RequestException:
        return None


def fetch_tt_plays_excerpt(tour_id: str, stage_number: int, max_chars: int = 3000) -> str | None:
    """Trimmet uddrag: åbningskommentar + de sidste ~12 kommentarer (typisk finalen)."""
    try:
        r = requests.get(PLAYS_URL.format(tour_id=tour_id, n=stage_number), headers=TT_HEADERS, timeout=15)
        if not r.ok:
            return None
        data = parse_jsonp(r.text)
        plays = data.get("plays", {}).get("play") if data else None
        if not plays:
            return None
        comments = [p.get("comment", "").strip() for p in plays if p.get("comment")]
        comments = [c for c in comments if c]
        if not comments:
            return None
        excerpt = comments[:1] + comments[-12:]
        joined = "\n".join(excerpt)
        return joined[:max_chars]
    except requests.RequestException:
        return None


# ── Database ──────────────────────────────────────────────────────────────────

def get_race(db_slug: str) -> dict | None:
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?slug=eq.{db_slug}&select=id,name,slug&limit=1",
        headers=READ_HEADERS,
    )
    data = r.json()
    return data[0] if data else None


def get_stages(race_id: str, force_all: bool, stage_number: int | None) -> list[dict]:
    recap_filter = "" if (force_all or stage_number) else "&historic_recap=is.null"
    stage_filter = f"&stage_number=eq.{stage_number}" if stage_number else ""
    url = (
        f"{SUPABASE_URL}/rest/v1/stages"
        f"?race_id=eq.{race_id}"
        f"&select=id,stage_number,name,date,distance_km,stage_type,start_location,finish_location,"
        f"elevation_gain_m{recap_filter}{stage_filter}"
        f"&order=stage_number.asc&limit=100"
    )
    r = requests.get(url, headers=READ_HEADERS)
    r.raise_for_status()
    return r.json()


def get_stage_top3(stage_id: str) -> list[dict]:
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/results"
        f"?stage_id=eq.{stage_id}&select=position,time_gap_seconds,riders(name,nationality)"
        f"&order=position.asc&limit=3",
        headers=READ_HEADERS,
    )
    return r.json() if r.ok and isinstance(r.json(), list) else []


def patch_stage(stage_id: str, recap: str) -> None:
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/stages?id=eq.{stage_id}",
        json={"historic_recap": recap},
        headers=DB_HEADERS,
    )
    if not r.ok:
        print(f"  [DB FEJL] {r.status_code}: {r.text[:200]}")


# ── Claude API ────────────────────────────────────────────────────────────────

SYSTEM = (
    "Du er cykelhistoriker og skriver til klassementet.dk, en dansk cykelportal. "
    "Du skriver tilbageskuende (historisk kommentator-sprog, datid) om etaper, der allerede er kørt "
    "for flere år siden — IKKE forudsigende som en pre-race-tekst. "
    "Du fundere dig UDELUKKENDE i de fakta, du får oplyst — opfind eller gæt aldrig navne, tal eller "
    "hændelser, der ikke fremgår af kilderne. Er du i tvivl om en detalje, udelad den. "
    "Kilderne (TourTracker) er andres redaktionelle tekst — omskriv altid til din egen, originale "
    "formulering, kopiér aldrig sætninger direkte. "
    "Du svarer KUN med ren JSON — ingen markdown-blokke."
)


def build_prompt(race_name: str, stage: dict, top3: list[dict], report: str | None, plays: str | None, mode: str) -> str:
    top3_lines = []
    for r in top3:
        rider = r.get("riders") or {}
        gap = r.get("time_gap_seconds")
        gap_txt = "vinder" if not gap else f"+{gap} sek"
        top3_lines.append(f"  {r.get('position')}. {rider.get('name', '?')} ({gap_txt})")
    top3_block = "\n".join(top3_lines) if top3_lines else "  (ikke tilgængeligt)"

    angle = random.choice(ANGLES)

    source_block = ""
    if report:
        source_block += f"\nTourTracker-rapport (kilde til fakta — omskriv, kopiér ikke):\n{report}\n"
    if plays:
        source_block += f"\nUddrag af løbende kommentering (ekstra kontekst, brug sparsomt):\n{plays}\n"
    if not source_block:
        source_block = "\n(Ingen ekstern kilde tilgængelig — brug KUN etapedata og topplaceringer ovenfor.)\n"

    length_instruction = (
        "Skriv 3-4 afsnit (en fyldig, engagerende fortælling) — kilden har reelt noget at fortælle."
        if mode == "full"
        else "Skriv ÉT kort afsnit (2-4 sætninger) — en ærlig, faktuel opsummering. Digt IKKE drama op, der ikke er belæg for."
    )

    return f"""Skriv en historisk fortælling om denne cykel-etape, der blev kørt for flere år siden.

Løb: {race_name}
Etape {stage.get('stage_number')}: {stage.get('start_location', '?')} → {stage.get('finish_location', '?')}
Dato: {stage.get('date', '?')} | Distance: {stage.get('distance_km', '?')} km | Type: {stage.get('stage_type', '?')}

Top 3 (vores egen verificerede database — brug PRÆCIS disse navne/placeringer, opfind ikke andre):
{top3_block}
{source_block}
{length_instruction}

Vinkel (brug den, hvis den passer med de faktiske fakta ovenfor — ellers vælg en naturlig indgang): {angle}

Returner præcis dette JSON-objekt:
{{
  "recap": "teksten på dansk, datid, historisk kommentator-sprog"
}}"""


def extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Claude sætter nogle gange en ugyldig backslash-escape ind (typisk om
        # en apostrof i et navn, fx "O\'Connor" — \' findes ikke i JSON-
        # spec'en, men optræder ikke-deterministisk afhængig af genereringen).
        # Fjerner enhver backslash der ikke starter en GYLDIG JSON-escape,
        # i stedet for kun at fejle hele etapen for en kosmetisk fejl.
        fixed = re.sub(r'\\(?!["\\/bfnrtu])', "", text)
        return json.loads(fixed)


def call_claude(client: Anthropic, race_name: str, stage: dict, top3: list[dict],
                 report: str | None, plays: str | None, mode: str) -> str | None:
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=700,
            system=SYSTEM,
            messages=[{"role": "user", "content": build_prompt(race_name, stage, top3, report, plays, mode)}],
            temperature=0.8,
        )
        result = extract_json(resp.content[0].text)
        return result.get("recap")
    except Exception as e:
        print(f"  [API FEJL] {e}")
        return None


# ── Hoved ─────────────────────────────────────────────────────────────────────

def run(db_slug: str, force_all: bool, stage_number: int | None) -> None:
    if not ANTHROPIC_KEY:
        print("FEJL: ANTHROPIC_API_KEY mangler i .env filen")
        sys.exit(1)

    race = get_race(db_slug)
    if not race:
        print(f"FEJL: løb '{db_slug}' ikke fundet i databasen")
        sys.exit(1)

    tt_map = load_tt_map()
    tour_id = tt_map.get(db_slug)
    if tour_id:
        print(f"TourTracker-kilde: tour-ID {tour_id}")
    else:
        print(f"Ingen TourTracker-mapping for '{db_slug}' — bruger kun egen DB-data (kort faktuel opsummering)")

    stages = get_stages(race["id"], force_all, stage_number)
    total = len(stages)
    print(f"Fandt {total} etape(r) at behandle\n")
    if not total:
        print("Alle etaper har allerede en historic_recap!")
        return

    client = Anthropic(api_key=ANTHROPIC_KEY)
    ok = fail = 0

    for i, stage in enumerate(stages, 1):
        n = stage["stage_number"]
        print(f"[{i}/{total}] Etape {n}: {stage.get('start_location')} → {stage.get('finish_location')}")

        top3 = get_stage_top3(stage["id"])

        report = plays = None
        mode = "short"
        if tour_id:
            report = fetch_tt_report(tour_id, n)
            if report and len(report) >= FULL_THRESHOLD:
                mode = "full"
                plays = fetch_tt_plays_excerpt(tour_id, n)
            elif report:
                mode = "short"
            else:
                print("  (ingen TourTracker-rapport for denne etape — falder tilbage til DB-data)")

        if not top3 and not report:
            print("  -> SPRINGER OVER (hverken resultater eller kilde-tekst tilgængelig)")
            continue

        recap = call_claude(client, race["name"], stage, top3, report, plays, mode)
        if not recap:
            print("  -> FEJL")
            fail += 1
            continue

        patch_stage(stage["id"], recap)
        print(f"  -> OK ({mode}, {len(recap)} tegn)")
        ok += 1
        time.sleep(DELAY)

    print(f"\nFærdig: {ok} skrevet, {fail} fejl")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--race", required=True, help="DB-slug, fx tour-de-france-2025")
    parser.add_argument("--stage", type=int, default=None, help="Kun denne etape")
    parser.add_argument("--all-stages", dest="all_stages", action="store_true", help="Alle etaper i løbet")
    parser.add_argument("--force", action="store_true", help="Regenerér selv hvis historic_recap allerede findes")
    args = parser.parse_args()

    if not args.stage and not args.all_stages:
        print("FEJL: angiv enten --stage N eller --all-stages")
        sys.exit(1)

    run(args.race, args.force, args.stage)
