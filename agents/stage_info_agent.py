"""
stage_info_agent.py
Genererer AI-beskrivelser og fun facts for etaper via Anthropic API (Claude).

Krav:
  - ANTHROPIC_API_KEY i .env filen (hent på console.anthropic.com)

Kør: python stage_info_agent.py
     python stage_info_agent.py --race giro-d-italia-2026   (kun ét løb)
     python stage_info_agent.py --all                        (overskriv eksisterende)

Re-run er sikkert: henter som standard kun etaper med description = NULL.
"""

import os
import sys
import io
import re
import json
import time
import argparse
import requests
from anthropic import Anthropic
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
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

# Hævet fra claude-haiku-4-5 2026-10-10. Teksten er brugervendt og står på
# løbets landingsside, og Haikus danske prosa holdt ikke: Il Lombardia fik
# "besiges" for bestiges, "pillestedsted" for pilgrimssted og "cykelsporten
# helgeninde" uden ejefald. Agenten kører kun på etaper, hvor description er
# NULL, så det er ikke en løbende udgift — men skift den tilbage, hvis en
# bulk-kørsel over en hel Grand Tour bliver for dyr.
MODEL = "claude-opus-5"

STAGE_TYPE_LABELS = {
    "flat":     "Flad (sprinteretape)",
    "hilly":    "Kuperet (puncheur-etape)",
    "mountain": "Bjerg (klatreretape)",
    "tt":       "Enkeltstart",
    "itt":      "Enkeltstart (hold)",
}

DELAY = 0.5  # sekunder mellem kald


# ── Database ──────────────────────────────────────────────────────────────────

def get_stages(race_slug: str | None, force_all: bool, stage_number: int | None = None) -> list[dict]:
    race_filter = ""
    if race_slug:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/races?slug=eq.{race_slug}&select=id&limit=1",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
        )
        data = r.json()
        if not data:
            print(f"Løb '{race_slug}' ikke fundet")
            return []
        race_filter = f"&race_id=eq.{data[0]['id']}"

    # --stage kræver implicit --all-semantik (vi vil regenerere netop DENNE
    # etape uanset om den allerede har en beskrivelse) — se STG-012.
    desc_filter = "" if (force_all or stage_number) else "&description=is.null"
    stage_filter = f"&stage_number=eq.{stage_number}" if stage_number else ""
    url = (
        f"{SUPABASE_URL}/rest/v1/stages"
        f"?select=id,race_id,stage_number,name,date,distance_km,stage_type,"
        f"start_location,finish_location,elevation_gain_m,profile_score"
        f"{desc_filter}{race_filter}{stage_filter}"
        f"&order=race_id.asc,stage_number.asc&limit=500"
    )
    r = requests.get(url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
    r.raise_for_status()
    return r.json()


def get_climbs(stage_id: str) -> list[dict]:
    """Etapens stigninger, som de står verificeret i vores egen database.

    Uden dem skrev agenten ud fra modellens egen hukommelse om regionen, og så
    kan en tekst om Il Lombardia nævne bjerge, ruten slet ikke kører over —
    eller tie om Ghisallo, Civiglio og den dobbelte San Fermo, som er hele
    historien. Vi HAR tallene, GPX-verificerede; så skal de i prompten frem for
    at blive gættet (CLAUDE.md §6).
    """
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/stage_climbs?stage_id=eq.{stage_id}"
        f"&select=name,km_from_start,length_km,avg_gradient,max_gradient,elevation_m"
        f"&order=km_from_start.asc.nullslast",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
    )
    return r.json() if r.ok and isinstance(r.json(), list) else []


def get_race_name(race_id: str, cache: dict) -> str:
    if race_id not in cache:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/races?id=eq.{race_id}&select=name&limit=1",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
        )
        cache[race_id] = r.json()[0]["name"] if r.json() else "Ukendt løb"
    return cache[race_id]


def patch_stage(stage_id: str, description: str, fun_facts: list, finish_type: str, start_time: str | None) -> None:
    data: dict = {"description": description, "fun_facts": fun_facts, "finish_type": finish_type}
    if start_time:
        data["stage_start_time"] = start_time
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/stages?id=eq.{stage_id}",
        json=data,
        headers=DB_HEADERS,
    )
    if not r.ok:
        print(f"  [DB FEJL] {r.status_code}: {r.text[:200]}")


# ── Claude API ────────────────────────────────────────────────────────────────

SYSTEM = (
    "Du er ekspert i professionel cykling og skriver kort, engagerende indhold på dansk "
    "til UCI WorldTour-fans på klassementet.dk. Du svarer KUN med ren JSON — ingen markdown-blokke."
)


def build_prompt(race_name: str, stage: dict, climbs: list[dict] | None = None) -> str:
    type_label = STAGE_TYPE_LABELS.get(stage.get("stage_type", ""), "Ukendt")
    elev = stage.get("elevation_gain_m")
    score = stage.get("profile_score")

    if climbs:
        dist = stage.get("distance_km")
        linjer = []
        for c in climbs:
            km = c.get("km_from_start")
            laengde = c.get("length_km")
            # Afstanden til mål REGNES her og gives til modellen. Uden den
            # regnede den selv — og tog fejl: San Fermos anden opstigning
            # topper 5 km fra mål, men blev beskrevet som "næstsidste
            # kilometer" (2026-10-10). Et forkert tal i en finale-beskrivelse
            # er præcis den slags, der koster tillid (CLAUDE.md §4).
            til_maal = ""
            if km is not None and dist:
                top_km = km + (laengde or 0)
                til_maal = (f", toppen {float(dist) - top_km:.1f} km fra mål"
                            if top_km <= float(dist) else "")
            linjer.append(
                f"- {c['name']}"
                + (f", fod ved km {km:g}" if km is not None else "")
                + (f", {laengde:g} km" if laengde else "")
                + (f" @ {c['avg_gradient']:g} %" if c.get("avg_gradient") else "")
                + (f" (max {c['max_gradient']:g} %)" if c.get("max_gradient") else "")
                + (f", +{c['elevation_m']} højdemeter" if c.get("elevation_m") else "")
                + til_maal
            )
        klatre_blok = ("\n\nStigninger på ruten (VERIFICERET mod GPX-sporet — brug disse "
                       "navne og tal, og nævn ingen andre stigninger). Afstanden til mål "
                       "står på hver linje: regn den ALDRIG selv, og skriv aldrig at en "
                       "stigning ligger tættere på mål, end der står her:\n"
                       + "\n".join(linjer))
    else:
        klatre_blok = ("\n\nVi har ingen verificerede stigningsdata for denne etape. "
                       "Nævn derfor INGEN stigninger ved navn.")

    return f"""Beskriv denne cykling-etape for danske fans.

Løb: {race_name}
Etape {stage.get('stage_number')}: {stage.get('start_location', '?')} → {stage.get('finish_location', '?')}
Dato: {stage.get('date', '?')} | Distance: {stage.get('distance_km', '?')} km
Højdemeter: {f'+{elev} m' if elev else '?'} | Type: {type_label} | Profil-score: {score or '?'}{klatre_blok}

Returner præcis dette JSON-objekt:
{{
  "description": "2-3 afsnit på dansk. Beskriv terrænet, hvad der gør finish interessant, og hvad fans skal holde øje med. Hold dig til facts du kender om regionen og etapetypen.",
  "fun_facts": ["kort fact 1", "kort fact 2", "kort fact 3"],
  "finish_type": "sprint|uphill|cobblestone|tt|gravel|circuit",
  "stage_start_time": "HH:MM eller null"
}}

SKRIV TAL PÅ DANSK i teksten: komma som decimaltegn og punktum som tusindtalsskilletegn
— altså "239,0 km", "4.662 højdemeter", "10,5 km @ 5,6 %". Tallene ovenfor står med
engelsk punktum; oversæt dem, men lav dem ikke om.

fun_facts: 3-4 konkrete bullets om etapen (geografi, historik, vejbeskaffenhed, vigtige stigninger).
finish_type: sprint=massespurt, uphill=bjergfinish, cobblestone=brosten, tt=enkeltstart.
stage_start_time: null hvis usikker.

VIGTIGT (tal-konsistens, se STG-012): distance og højdemeter står allerede i felterne ovenfor
({stage.get('distance_km', '?')} km, {f'+{elev} m' if elev else 'ukendt'} højdemeter). Hvis du nævner
disse tal i description eller fun_facts, SKAL du bruge PRÆCIS disse værdier — afrund ikke, og opfind
IKKE et andet tal for distance, højdemeter eller profil-score. Er du i tvivl, undlad hellere at nævne
det konkrete tal end at gætte forkert."""


def extract_json(text: str) -> dict:
    """Udtræk JSON fra svar der evt. indeholder markdown-kodeblokke."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def call_claude(client: Anthropic, race_name: str, stage: dict,
                climbs: list[dict] | None = None) -> dict | None:
    try:
        resp = client.messages.create(
            model=MODEL,
            # Rummeligt, fordi adaptiv taenkning ogsaa taeller med i
            # max_tokens: ved 900 blev JSON'en afkortet midt i en streng.
            max_tokens=8000,
            system=SYSTEM,
            messages=[{"role": "user",
                       "content": build_prompt(race_name, stage, climbs)}],
            # Ingen temperature: den er fjernet på Opus 5 og giver 400.
            thinking={"type": "adaptive"},
        )
        # Med adaptiv tænkning er content[0] et ThinkingBlock, ikke svaret.
        svar = next((b.text for b in resp.content if b.type == "text"), None)
        if not svar:
            print("  [API FEJL] intet tekstsvar i svaret")
            return None
        return extract_json(svar)
    except Exception as e:
        print(f"  [API FEJL] {e}")
        return None


# ── Hoved ─────────────────────────────────────────────────────────────────────

def run(race_slug: str | None, force_all: bool, stage_number: int | None = None) -> None:
    if not ANTHROPIC_KEY:
        print("FEJL: ANTHROPIC_API_KEY mangler i .env filen")
        print("Hent nøgle på: https://console.anthropic.com/settings/keys")
        sys.exit(1)

    client = Anthropic(api_key=ANTHROPIC_KEY)
    stages = get_stages(race_slug, force_all, stage_number)
    total  = len(stages)
    print(f"Fandt {total} etaper\n")
    if not total:
        print("Alle etaper har allerede en beskrivelse!")
        return

    race_cache: dict = {}
    ok = fail = 0

    for i, stage in enumerate(stages, 1):
        race_name = get_race_name(stage["race_id"], race_cache)
        print(f"[{i}/{total}] {race_name} E{stage['stage_number']}: "
              f"{stage.get('start_location')} → {stage.get('finish_location')}")

        climbs = get_climbs(stage["id"])
        if climbs:
            print(f"  {len(climbs)} verificeret(e) stigning(er) med i prompten")

        result = call_claude(client, race_name, stage, climbs)
        if not result or not result.get("description"):
            print("  -> FEJL")
            fail += 1
            continue

        patch_stage(
            stage["id"],
            result["description"],
            result.get("fun_facts", []),
            result.get("finish_type", "sprint"),
            result.get("stage_start_time") or None,
        )
        print(f"  -> OK ({result.get('finish_type')}, {len(result.get('fun_facts', []))} facts)")
        ok += 1
        time.sleep(DELAY)

    print(f"\nFærdig: {ok} beskrevet, {fail} fejl")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--race",    help="Løbets slug (fx giro-d-italia-2026)", default=None)
    parser.add_argument("--all",     dest="force_all", action="store_true")
    parser.add_argument("--stage",   type=int, default=None, help="Regenerer kun denne etape (kræver --race)")
    args = parser.parse_args()
    run(args.race, args.force_all, args.stage)
