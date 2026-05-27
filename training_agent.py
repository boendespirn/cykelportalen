"""
training_agent.py
Bruger Claudes viden til at finde træningsregion for ryttere i et løb.
Gemmer i riders.training_region. Koster ~$0.05 for 157 Giro-ryttere.

Kør: python training_agent.py --race giro-d-italia-2026
"""

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

TRAINING_PROMPT = """You are given a list of professional cyclists. For each, return the city or region they are primarily known to train in (their regular training base or winter training area).

Rules:
- Only return confident answers based on well-known facts (e.g. published in cycling media).
- Return null if uncertain or unknown.
- For Italian regions use the standard region name (e.g. "Toscana", "Lombardia").
- For other countries return "City, Country" format.

Return ONLY a valid JSON array matching input order:
[{"name": "...", "training_region": "..." or null}, ...]

Cyclists:"""


def get_race_riders(race_slug: str) -> list[dict]:
    race_res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?slug=eq.{race_slug}&select=id&limit=1",
        headers=SB_AUTH,
    )
    if not race_res.ok or not race_res.json():
        return []
    race_id = race_res.json()[0]["id"]

    url = (
        f"{SUPABASE_URL}/rest/v1/startlists"
        f"?race_id=eq.{race_id}"
        f"&status=eq.active"
        f"&select=rider_id,riders(id,name,training_region)"
        f"&limit=200"
    )
    res = requests.get(url, headers=SB_AUTH)
    if not res.ok:
        return []

    riders = []
    for row in res.json():
        r = row.get("riders") or {}
        if not r.get("training_region"):
            riders.append({"id": r["id"], "name": r["name"]})
    return riders


def patch_rider(rider_id: str, training_region: str) -> None:
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/riders?id=eq.{rider_id}",
        json={"training_region": training_region},
        headers=SB_HEADERS,
    )
    if not res.ok:
        print(f"  [DB FEJL] {res.status_code} {res.text[:120]}")


def run(race_slug: str) -> None:
    if not ANTHROPIC_KEY:
        print("Fejl: ANTHROPIC_API_KEY mangler")
        return

    riders = get_race_riders(race_slug)
    total = len(riders)
    print(f"training_agent.py — {race_slug}")
    print(f"Fandt {total} ryttere uden training_region\n")

    if not riders:
        print("Ingen ryttere at opdatere.")
        return

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    batch_size = 20
    saved = 0

    for i in range(0, total, batch_size):
        batch = riders[i : i + batch_size]
        names = [r["name"] for r in batch]
        prompt = TRAINING_PROMPT + "\n" + json.dumps(names, ensure_ascii=False)

        print(f"Batch {i//batch_size + 1}: {names[0]} ... {names[-1]}")

        try:
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            parsed = json.loads(raw)

            for entry, rider in zip(parsed, batch):
                tr = entry.get("training_region")
                if tr:
                    patch_rider(rider["id"], tr)
                    print(f"  {rider['name']} -> {tr}")
                    saved += 1
                else:
                    print(f"  {rider['name']} -> ukendt")

        except Exception as e:
            print(f"  [Fejl]: {e}")

    print(f"\nFærdig: {saved} ryttere opdateret med træningsregion")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--race", required=True)
    args = parser.parse_args()
    run(args.race)
