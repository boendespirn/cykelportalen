"""
local_favorite_agent.py
Krydser rytternes hjemregion/træningsregion med etapernes stigningsregioner.
Genererer en dansk "lokal favorit"-sætning og gemmer i stages.fun_facts.

Kør: python local_favorite_agent.py --race giro-d-italia-2026
     python local_favorite_agent.py --race giro-d-italia-2026 --stage 7
     python local_favorite_agent.py --race giro-d-italia-2026 --overwrite
"""

import ast
import os
import re
import sys
import io
import json
import argparse
import requests
import anthropic
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")

SB_AUTH = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}
SB_HEADERS = {
    **SB_AUTH,
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

LOCAL_FACT_MARKER = "🏠 Lokale favoritter:"

FACT_PROMPT = """Du er en dansk cykelkommentator. Skriv ÉN kort, præcis sætning på dansk om de ryttere nedenfor, der har en lokal tilknytning til dagens etape.

Etape: {stage_desc}
Nøglestigning: {climb}
Region: {region}

Lokale ryttere:
{riders_list}

Sætningen skal:
- Nævne rytternavnene direkte
- Forklare tilknytningen (opvokset i / træner i)
- Være på maks 2 linjer
- Starte med "{marker}"

Skriv KUN sætningen, ingen forklaring."""


def sb_get(table: str, query: str) -> list[dict]:
    res = requests.get(f"{SUPABASE_URL}/rest/v1/{table}{query}", headers=SB_AUTH)
    return res.json() if res.ok else []


def get_race_id(race_slug: str) -> str | None:
    rows = sb_get("races", f"?slug=eq.{race_slug}&select=id&limit=1")
    return rows[0]["id"] if rows else None


def get_stages(race_id: str, stage_number: int | None) -> list[dict]:
    q = (
        f"?race_id=eq.{race_id}"
        f"&select=id,stage_number,finish_location,stage_type,fun_facts"
        f"&stage_type=neq.flat&stage_type=neq.tt&stage_type=neq.itt"
        f"&order=stage_number.asc"
    )
    if stage_number:
        q += f"&stage_number=eq.{stage_number}"
    return sb_get("stages", q)


def get_stage_regions(stage_id: str) -> list[dict]:
    """Returnerer unikke (region, climb_name) for en etape."""
    rows = sb_get(
        "stage_climbs",
        f"?stage_id=eq.{stage_id}&select=name,region&region=not.is.null",
    )
    seen: set[str] = set()
    result = []
    for r in rows:
        reg = r.get("region")
        if reg and reg not in seen:
            seen.add(reg)
            result.append({"region": reg, "climb": r["name"]})
    return result


def get_riders_for_race(race_id: str) -> list[dict]:
    """Henter alle aktive ryttere i løbet med hjemregion og træningsregion."""
    rows = sb_get(
        "startlists",
        f"?race_id=eq.{race_id}&status=eq.active"
        f"&select=riders(id,name,hometown,hometown_region,training_region,speciality)"
        f"&limit=200",
    )
    riders = []
    for row in rows:
        r = row.get("riders") or {}
        if r.get("hometown_region") or r.get("training_region"):
            riders.append(r)
    return riders


def find_local_riders(riders: list[dict], region: str) -> list[dict]:
    """Find ryttere hvis hjemregion eller træningsregion matcher."""
    matches = []
    for r in riders:
        is_home = (r.get("hometown_region") or "").lower() == region.lower()
        is_train = (r.get("training_region") or "").lower() == region.lower()
        if is_home or is_train:
            matches.append({
                "name": r["name"],
                "hometown_region": r.get("hometown_region"),
                "training_region": r.get("training_region"),
                "speciality": r.get("speciality"),
                "connection": "home" if is_home else "training",
            })
    return matches


def generate_fact(stage: dict, region: str, climb: str, local_riders: list[dict]) -> str | None:
    if not ANTHROPIC_KEY or not local_riders:
        return None

    riders_list = "\n".join(
        f"- {r['name']} ({'opvokset i ' + region if r['connection'] == 'home' else 'træner i ' + region})"
        for r in local_riders
    )

    prompt = FACT_PROMPT.format(
        stage_desc=f"Etape {stage['stage_number']} til {stage['finish_location']}",
        climb=climb,
        region=region,
        riders_list=riders_list,
        marker=LOCAL_FACT_MARKER,
    )

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f"  [Claude fejl]: {e}")
        return None


def parse_existing_facts(raw) -> list[str]:
    """Normalize existing fun_facts to a list regardless of storage format."""
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(f) for f in raw]
    if not isinstance(raw, str):
        return []
    text = raw.strip()
    if text.startswith("["):
        depth, end = 0, -1
        for i, ch in enumerate(text):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end >= 0:
            try:
                facts = ast.literal_eval(text[: end + 1])
                if isinstance(facts, list):
                    result = [str(f) for f in facts]
                    rest = text[end + 1 :].strip()
                    if rest:
                        result.append(rest)
                    return result
            except Exception:
                pass
    return [text] if text else []


def update_fun_facts(stage_id: str, new_fact: str, existing_raw, overwrite: bool) -> None:
    facts = parse_existing_facts(existing_raw)

    if any(LOCAL_FACT_MARKER in f for f in facts):
        if not overwrite:
            return
        facts = [f for f in facts if LOCAL_FACT_MARKER not in f]

    facts.append(new_fact)

    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/stages?id=eq.{stage_id}",
        json={"fun_facts": facts},
        headers=SB_HEADERS,
    )
    if not res.ok:
        print(f"  [DB FEJL] {res.status_code}")


def run(race_slug: str, stage_number: int | None, overwrite: bool) -> None:
    if not ANTHROPIC_KEY:
        print("Fejl: ANTHROPIC_API_KEY mangler")
        return

    race_id = get_race_id(race_slug)
    if not race_id:
        print(f"Løb ikke fundet: {race_slug}")
        return

    stages = get_stages(race_id, stage_number)
    all_riders = get_riders_for_race(race_id)
    print(f"local_favorite_agent.py — {race_slug}")
    print(f"Fandt {len(stages)} etaper, {len(all_riders)} ryttere med regionsdata\n")

    if not all_riders:
        print("Ingen ryttere har hjemregion endnu — kør hometown_agent.py først.")
        return

    facts_written = 0

    for stage in stages:
        n = stage["stage_number"]
        finish = stage.get("finish_location", "")
        existing_facts = stage.get("fun_facts")

        facts_list = parse_existing_facts(existing_facts)
        if any(LOCAL_FACT_MARKER in f for f in facts_list) and not overwrite:
            print(f"[E{n}] {finish} — allerede har lokal-fakta, springer over")
            continue

        regions = get_stage_regions(stage["id"])
        if not regions:
            print(f"[E{n}] {finish} — ingen stigninger med region")
            continue

        print(f"[E{n}] {finish} — regioner: {[r['region'] for r in regions]}")

        for reg_info in regions:
            region = reg_info["region"]
            climb = reg_info["climb"]
            local_riders = find_local_riders(all_riders, region)

            if not local_riders:
                continue

            print(f"  {region}: {[r['name'] for r in local_riders]}")
            fact = generate_fact(stage, region, climb, local_riders)

            if fact:
                update_fun_facts(stage["id"], fact, existing_facts, overwrite)
                print(f"  -> Gemt: {fact[:80]}...")
                facts_written += 1
                break  # Ét lokal-fakta per etape er nok

    print(f"\nFærdig: {facts_written} etaper opdateret med lokal-favorit fakta")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--race", required=True)
    parser.add_argument("--stage", type=int)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    run(args.race, args.stage, args.overwrite)
