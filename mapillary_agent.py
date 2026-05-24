"""
mapillary_agent.py
Henter street-level billeder af etapemål via Mapillary API (100% gratis)
og lader Claude Vision analysere vejforhold for danske fans.

Output tilføjes til stages.fun_facts og stages.description.

Krav: MAPILLARY_ACCESS_TOKEN i .env (opret gratis konto på mapillary.com)
      ANTHROPIC_API_KEY i .env

Kør: python mapillary_agent.py --race giro-d-italia-2026
     python mapillary_agent.py --race giro-d-italia-2026 --stage 15
"""

import os
import sys
import io
import time
import base64
import argparse
import requests
from dotenv import load_dotenv

try:
    from anthropic import Anthropic
except ImportError:
    print("FEJL: anthropic ikke installeret. Kør: pip install anthropic")
    sys.exit(1)

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL    = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY    = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY")
MAPILLARY_TOKEN = os.getenv("MAPILLARY_ACCESS_TOKEN")

AUTH_HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
DB_HEADERS   = {**AUTH_HEADERS, "Content-Type": "application/json", "Prefer": "return=minimal"}

MAPILLARY_API = "https://graph.mapillary.com"
MODEL         = "claude-haiku-4-5-20251001"
DELAY         = 1.5


# ── Supabase helpers ──────────────────────────────────────────────────────────

def get_race_id(race_slug: str) -> str | None:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?slug=eq.{race_slug}&select=id&limit=1",
        headers=AUTH_HEADERS,
    )
    data = res.json()
    return data[0]["id"] if res.ok and data else None


def get_stages(race_slug: str, stage_number: int | None) -> list[dict]:
    race_id = get_race_id(race_slug)
    if not race_id:
        print(f"Løb '{race_slug}' ikke fundet")
        return []

    url = (
        f"{SUPABASE_URL}/rest/v1/stages"
        f"?race_id=eq.{race_id}"
        f"&select=id,stage_number,finish_location,fun_facts,description"
        f"&order=stage_number.asc"
    )
    if stage_number:
        url += f"&stage_number=eq.{stage_number}"
    res = requests.get(url, headers=AUTH_HEADERS)
    return res.json() if res.ok else []


def update_stage(stage_id: str, fun_facts: list[str], description_append: str) -> bool:
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
    """Nominatim geocoding."""
    res = requests.get(
        f"https://nominatim.openstreetmap.org/search"
        f"?q={requests.utils.quote(location)}&format=json&limit=1",
        headers={"User-Agent": "Klassementet/1.0 (jonasb408@gmail.com)"},
        timeout=10,
    )
    if res.ok and res.json():
        d = res.json()[0]
        return float(d["lat"]), float(d["lon"])
    return None


# ── Mapillary ─────────────────────────────────────────────────────────────────

def get_mapillary_images(lat: float, lng: float, radius_m: int = 200) -> list[dict]:
    if not MAPILLARY_TOKEN:
        return []

    bbox_offset = radius_m / 111_000
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
    return res.json().get("data", []) if res.ok else []


def download_image_b64(url: str) -> str | None:
    try:
        res = requests.get(url, timeout=10)
        if res.ok:
            return base64.b64encode(res.content).decode("utf-8")
    except Exception:
        pass
    return None


# ── Claude Vision analyse ─────────────────────────────────────────────────────

VISION_SYSTEM = """Du er ekspert i professionel cykling og analyserer fotos af cykelruter for danske fans.
Beskriv vejforhold kortfattet og præcist. Fokus på faktorer der påvirker et cykelløb:
brosten, vejbredde, sving, stigninger, tekniske elementer, vejbelæg, vindeksponering.
Svar på DANSK i 2-3 korte sætninger. Vær konkret."""

VISION_PROMPT = (
    "Beskriv dette vejbillede set fra en cykelrytters perspektiv. "
    "Hvad ser du der er relevant for et professionelt cykelløb — vejtype, bredde, belæg, "
    "sving, stigning, tekniske elementer? Nævn kun hvad du faktisk kan se på billedet."
)


def analyse_finish(client: Anthropic, images: list[dict]) -> str | None:
    """Sender Mapillary-billeder til Claude Vision og returnerer analyse."""
    content = []

    for img in images[:3]:
        thumb_url = img.get("thumb_1024_url")
        if not thumb_url:
            continue
        b64 = download_image_b64(thumb_url)
        if b64:
            content.append({
                "type": "image",
                "source": {
                    "type":       "base64",
                    "media_type": "image/jpeg",
                    "data":       b64,
                },
            })

    if not content:
        return None

    content.append({"type": "text", "text": VISION_PROMPT})

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=200,
            system=VISION_SYSTEM,
            messages=[{"role": "user", "content": content}],
            temperature=0.5,
        )
        return resp.content[0].text.strip()
    except Exception as e:
        print(f"  [Vision fejl: {e}]")
        return None


# ── Main pipeline ─────────────────────────────────────────────────────────────

def process_race(race_slug: str, stage_number: int | None) -> None:
    if not MAPILLARY_TOKEN:
        print("FEJL: MAPILLARY_ACCESS_TOKEN mangler i .env")
        print("Opret gratis konto på mapillary.com og generer access token.")
        return

    if not ANTHROPIC_KEY:
        print("FEJL: ANTHROPIC_API_KEY mangler i .env")
        return

    client = Anthropic(api_key=ANTHROPIC_KEY)
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

        coords = geocode(finish)
        if not coords:
            print(f"  -> Geocoding fejlede for '{finish}'")
            time.sleep(1)
            continue

        lat, lng = coords
        print(f"  Koordinater: {lat:.4f}, {lng:.4f}")

        images = get_mapillary_images(lat, lng)
        if not images:
            print("  -> Ingen Mapillary-billeder fundet")
            time.sleep(DELAY)
            continue

        print(f"  Fandt {len(images)} Mapillary-billeder")

        analysis = analyse_finish(client, images)
        if not analysis:
            print("  -> Vision-analyse fejlede")
            time.sleep(DELAY)
            continue

        print(f"  Analyse: {analysis[:80]}...")

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
    parser.add_argument("--race",  required=True, help="Løb-slug, fx giro-d-italia-2026")
    parser.add_argument("--stage", type=int,      help="Specifik etape (default: alle)")
    args = parser.parse_args()

    process_race(args.race, args.stage)
