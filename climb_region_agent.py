"""
climb_region_agent.py
Klassificerer stage_climbs.region for et løb via ét Claude-kald.
Koster ~$0.01 for alle Giro-stigninger.

Kør: python climb_region_agent.py --race giro-d-italia-2026
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

REGION_PROMPT = """You are given a list of cycling stage climbs and their stage finish locations from a professional race.
For each climb, return the region/area it is located in using these rules:

Italy: use the Italian administrative region name (Lombardia, Veneto, Toscana, Sicilia, Abruzzo, Piemonte,
Campania, Emilia-Romagna, Lazio, Sardegna, Puglia, Calabria, Liguria, Friuli-Venezia Giulia,
Trentino-Alto Adige, Valle d'Aosta, Umbria, Marche, Molise, Basilicata).

France: use the French administrative region name (Auvergne-Rhône-Alpes, Provence-Alpes-Côte d'Azur,
Occitanie, Nouvelle-Aquitaine, Bretagne, Normandie, Île-de-France, Grand Est, Bourgogne-Franche-Comté,
Hauts-de-France, Pays de la Loire, Centre-Val de Loire, Corse).

Switzerland: use the canton name in English (Valais, Graubünden, Bern, Vaud, Ticino, Zurich, etc.)
or "Switzerland" if uncertain.

Other countries: return the country name in English (Spain, Belgium, Netherlands, Colombia, etc.).
If uncertain, return null.

Return ONLY a valid JSON array matching input order:
[{"climb": "...", "region": "..." or null}, ...]

Climbs:"""


def get_climbs(race_slug: str) -> list[dict]:
    race_res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?slug=eq.{race_slug}&select=id&limit=1",
        headers=SB_AUTH,
    )
    if not race_res.ok or not race_res.json():
        return []
    race_id = race_res.json()[0]["id"]

    url = (
        f"{SUPABASE_URL}/rest/v1/stage_climbs"
        f"?select=id,name,region,stages(stage_number,finish_location,race_id)"
        f"&stages.race_id=eq.{race_id}"
        f"&region=is.null"
        f"&limit=200"
    )
    res = requests.get(url, headers=SB_AUTH)
    if not res.ok:
        return []

    return [
        {
            "id": row["id"],
            "name": row["name"],
            "finish": (row.get("stages") or {}).get("finish_location", ""),
        }
        for row in res.json()
        if (row.get("stages") or {}).get("race_id") == race_id
    ]


def patch_climb(climb_id: str, region: str) -> None:
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/stage_climbs?id=eq.{climb_id}",
        json={"region": region},
        headers=SB_HEADERS,
    )
    if not res.ok:
        print(f"  [DB FEJL] {res.status_code}")


def run(race_slug: str) -> None:
    if not ANTHROPIC_KEY:
        print("Fejl: ANTHROPIC_API_KEY mangler")
        return

    climbs = get_climbs(race_slug)
    print(f"climb_region_agent.py — {race_slug}")
    print(f"Fandt {len(climbs)} stigninger uden region\n")

    if not climbs:
        print("Alle stigninger har allerede en region.")
        return

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    saved = 0
    batch_size = 30

    for batch_start in range(0, len(climbs), batch_size):
        batch = climbs[batch_start : batch_start + batch_size]
        items = [{"climb": c["name"], "finish_location": c["finish"]} for c in batch]
        prompt = REGION_PROMPT + "\n" + json.dumps(items, ensure_ascii=False)

        try:
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            parsed = json.loads(raw)
        except Exception as e:
            print(f"Claude fejl (batch {batch_start//batch_size + 1}): {e}")
            continue

        for entry, climb in zip(parsed, batch):
            region = entry.get("region")
            if region:
                patch_climb(climb["id"], region)
                print(f"  {climb['name']} -> {region}")
                saved += 1
            else:
                print(f"  {climb['name']} -> ukendt region")

    print(f"\nFærdig: {saved}/{len(climbs)} stigninger opdateret")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--race", required=True)
    args = parser.parse_args()
    run(args.race)
