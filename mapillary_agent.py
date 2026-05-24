"""
mapillary_agent.py
Henter street-level billeder af etapemål via Mapillary API (100% gratis)
og lader Claude Vision analysere vejforhold for danske fans.

Output tilføjes til stages.fun_facts og stages.description.

Krav: MAPILLARY_ACCESS_TOKEN i .env (opret gratis konto på mapillary.com)
      OPENAI_API_KEY i .env

Kør: python mapillary_agent.py --race giro-ditalia-2026
     python mapillary_agent.py --race giro-ditalia-2026 --stage 15
"""

import os
import re
import sys
import io
import json
import time
import base64
import argparse
import requests
from dotenv import load_dotenv

try:
    from openai import OpenAI
except ImportError:
    print("FEJL: openai ikke installeret. Kør: pip install openai")
    sys.exit(1)

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL      = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY      = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
OPENAI_KEY        = os.getenv("OPENAI_API_KEY")
MAPILLARY_TOKEN   = os.getenv("MAPILLARY_ACCESS_TOKEN")

AUTH_HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
DB_HEADERS   = {**AUTH_HEADERS, "Content-Type": "application/json", "Prefer": "return=minimal"}

MAPILLARY_API = "https://graph.mapillary.com"
DELAY         = 1.5


# ── Supabase helpers ──────────────────────────────────────────────────────────

def get_stages(race_slug: str, stage_number: int | None) -> list[dict]:
    url = (
        f"{SUPABASE_URL}/rest/v1/stages"
        f"?select=id,stage_number,finish_location,fun_facts,description,"
        f"races!inner(slug)"
        f"&races.slug=eq.{race_slug}"
        f"&order=stage_number.asc"
    )
    if stage_number:
        url += f"&stage_number=eq.{stage_number}"
    res = requests.get(url, headers=AUTH_HEADERS)
    return res.json() if res.ok else []


def update_stage(stage_id: str, fun_facts: list[str], description_append: str) -> bool:
    # Hent nuværende fun_facts
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages?id=eq.{stage_id}&select=fun_facts,description",
        headers=AUTH_HEADERS,
    )
    if not res.ok or not res.json():
        return False

    current = res.json()[0]
    existing_facts = current.get("fun_facts") or []
    existing_desc  = current.get("description") or ""

    merged_facts = existing_facts + [f for f in fun_facts if f not in existing_facts]
    new_desc     = f"{existing_desc}\n\n{description_append}".strip() if description_append else existing_desc

    patch_res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/stages?id=eq.{stage_id}",
        json={"fun_facts": merged_facts, "description": new_desc},
        headers=DB_HEADERS,
    )
    return patch_res.ok


# ── Geocoding ─────────────────────────────────────────────────────────────────

def geocode(location: str) -> tuple[float, float] | None:
    """Nominatim geocoding — samme som i øvrige agenter."""
    query = location.replace(r"\(.*\)", "").strip()
    res   = requests.get(
        f"https://nominatim.openstreetmap.org/search"
        f"?q={requests.utils.quote(query)}&format=json&limit=1",
        headers={"User-Agent": "Klassementet/1.0 (jonasb408@gmail.com)"},
        timeout=10,
    )
    if res.ok and res.json():
        d = res.json()[0]
        return float(d["lat"]), float(d["lon"])
    return None


# ── Mapillary ─────────────────────────────────────────────────────────────────

def get_mapillary_images(lat: float, lng: float, radius_m: int = 200) -> list[dict]:
    """
    Finder Mapillary-billeder inden for radius_m meter fra koordinatet.
    Returnerer op til 5 billeder med thumbnail-URL.
    """
    if not MAPILLARY_TOKEN:
        return []

    bbox_offset = radius_m / 111_000  # ca. konvertering meter → grader
    bbox = f"{lng - bbox_offset},{lat - bbox_offset},{lng + bbox_offset},{lat + bbox_offset}"

    res = requests.get(
        f"{MAPILLARY_API}/images",
        params={
            "bbox":         bbox,
            "access_token": MAPILLARY_TOKEN,
            "fields":       "id,thumb_1024_url,captured_at",
            "limit":        5,
        },
        timeout=10,
    )
    if res.ok:
        return res.json().get("data", [])
    return []


def download_image_b64(url: str) -> str | None:
    """Downloader billede og returnerer base64-encoded string til OpenAI Vision."""
    try:
        res = requests.get(url, timeout=10)
        if res.ok:
            return base64.b64encode(res.content).decode("utf-8")
    except Exception:
        pass
    return None


# ── OpenAI Vision analyse ─────────────────────────────────────────────────────

VISION_SYSTEM = """Du er ekspert i professionel cykling og analyserer fotos af cykelruter for danske fans.
Beskriv vejforhold kortfattet og præcist. Fokus på faktorer der påvirker et cykelloøb:
brosten, vejbredde, sving, stigninger, tekniske elementer, vejbelæg, vindeksponering.
Svar på DANSK i 2-3 korte sætninger. Vær konkret."""

VISION_PROMPT = (
    "Beskriv dette vejbillede set fra en cykelrytters perspektiv. "
    "Hvad ser du der er relevant for et professionelt cykelløb — vejtype, bredde, belæg, "
    "sving, stigning, tekniske elementer? Nævn kun hvad du faktisk kan se på billedet."
)


def analyse_finish(client: OpenAI, images: list[dict], finish_location: str) -> str | None:
    """Sender Mapillary-billeder til GPT-4 Vision og returnerer analyse."""
    if not images:
        return None

    messages_content = [{"type": "text", "text": VISION_PROMPT}]

    for img in images[:3]:  # Max 3 billeder
        thumb_url = img.get("thumb_1024_url")
        if not thumb_url:
            continue
        b64 = download_image_b64(thumb_url)
        if b64:
            messages_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64}",
                    "detail": "low",
                },
            })

    if len(messages_content) <= 1:
        return None  # Ingen billeder lykkedes

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": VISION_SYSTEM},
                {"role": "user",   "content": messages_content},
            ],
            max_tokens=200,
            temperature=0.5,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"  [Vision fejl: {e}]")
        return None


# ── Main pipeline ─────────────────────────────────────────────────────────────

def process_race(race_slug: str, stage_number: int | None) -> None:
    if not MAPILLARY_TOKEN:
        print("FEJL: MAPILLARY_ACCESS_TOKEN mangler i .env")
        print("Opret gratis konto på mapillary.com og generer access token.")
        return

    if not OPENAI_KEY:
        print("FEJL: OPENAI_API_KEY mangler i .env")
        return

    client = OpenAI(api_key=OPENAI_KEY)
    stages = get_stages(race_slug, stage_number)

    print(f"mapillary_agent.py — {race_slug}")
    print(f"Fandt {len(stages)} etaper\n")

    for stage in stages:
        n        = stage["stage_number"]
        finish   = stage.get("finish_location")
        stage_id = stage["id"]

        print(f"[E{n}] Mål: {finish}")

        if not finish:
            print("  -> Ingen finish-lokation")
            continue

        # 1. Geocode finish
        coords = geocode(finish)
        if not coords:
            print(f"  -> Geocoding fejlede for '{finish}'")
            time.sleep(1)
            continue

        lat, lng = coords
        print(f"  Koordinater: {lat:.4f}, {lng:.4f}")

        # 2. Hent Mapillary-billeder
        images = get_mapillary_images(lat, lng)
        if not images:
            print("  -> Ingen Mapillary-billeder fundet")
            time.sleep(DELAY)
            continue

        print(f"  Fandt {len(images)} Mapillary-billeder")

        # 3. GPT-4 Vision analyse
        analysis = analyse_finish(client, images, finish)
        if not analysis:
            print("  -> Vision-analyse fejlede")
            time.sleep(DELAY)
            continue

        print(f"  Analyse: {analysis[:80]}...")

        # 4. Gem til DB
        fun_fact = f"Målstregen ved {finish}: {analysis}"
        desc_note = f"\n**Målstregen ved {finish}:** {analysis}"

        if update_stage(stage_id, [fun_fact], desc_note):
            print("  -> Gemt til fun_facts og description")
        else:
            print("  -> DB-opdatering fejlede")

        time.sleep(DELAY)

    print("\nFærdig.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--race",  required=True, help="Løb-slug, fx giro-ditalia-2026")
    parser.add_argument("--stage", type=int,      help="Specifik etape (default: alle)")
    args = parser.parse_args()

    process_race(args.race, args.stage)
