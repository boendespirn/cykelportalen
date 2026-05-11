import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL:
    raise Exception("Mangler SUPABASE_URL i .env")

if not SUPABASE_SERVICE_ROLE_KEY:
    raise Exception("Mangler SUPABASE_SERVICE_ROLE_KEY i .env")


url = f"{SUPABASE_URL}/rest/v1/races?select=name,start_date,country_code,category&order=start_date.asc"

headers = {
    "apikey": SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
}

response = requests.get(url, headers=headers)

print("Status:", response.status_code)

races = response.json()

for race in races:
    print(
        race["start_date"],
        "-",
        race["name"],
        "-",
        race["country_code"],
        "-",
        race["category"]
    )