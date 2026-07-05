import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

HEADERS = {
    "apikey": SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates"
}


def get_race_by_slug(slug):
    url = f"{SUPABASE_URL}/rest/v1/races?select=id,name&slug=eq.{slug}&limit=1"
    response = requests.get(url, headers=HEADERS)
    data = response.json()

    if not data:
        raise Exception(f"Kunne ikke finde løb med slug: {slug}")

    return data[0]


def save_stage(stage):
    url = f"{SUPABASE_URL}/rest/v1/stages?on_conflict=race_id,stage_number"
    response = requests.post(url, headers=HEADERS, json=stage)

    print("Gemmer etape:", stage["stage_number"], "-", stage["name"])
    print("Status:", response.status_code)

    if response.status_code not in [200, 201]:
        print("Fejl:", response.text)


race = get_race_by_slug("tour-de-france-2026")

stages = [
    {
        "race_id": race["id"],
        "stage_number": 1,
        "name": "Etape 1",
        "date": "2026-07-04",
        "distance_km": 185.0,
        "start_location": "Ukendt startby",
        "finish_location": "Ukendt målby",
        "elevation_gain_m": None,
        "stage_type": "road",
        "source": "manual_test",
        "source_url": "https://www.letour.fr",
    },
    {
        "race_id": race["id"],
        "stage_number": 2,
        "name": "Etape 2",
        "date": "2026-07-05",
        "distance_km": 170.0,
        "start_location": "Ukendt startby",
        "finish_location": "Ukendt målby",
        "elevation_gain_m": None,
        "stage_type": "road",
        "source": "manual_test",
        "source_url": "https://www.letour.fr",
    },
]

print("Fundet løb:", race["name"])

for stage in stages:
    save_stage(stage)

print("Færdig")