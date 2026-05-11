from fastapi import FastAPI
from datetime import date
import os
import requests
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def get_headers():
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }


@app.get("/")
def root():
    return {"message": "API virker"}


@app.get("/races")
def get_races():
    url = f"{SUPABASE_URL}/rest/v1/races?select=name,slug,start_date,end_date,country_code,category&order=start_date.asc"
    response = requests.get(url, headers=get_headers())
    return response.json()


@app.get("/upcoming-races")
def get_upcoming_races():
    today = date.today().isoformat()
    url = f"{SUPABASE_URL}/rest/v1/races?select=name,slug,start_date,end_date,country_code,category&start_date=gte.{today}&order=start_date.asc"
    response = requests.get(url, headers=get_headers())
    return response.json()


@app.get("/races/{slug}")
def get_race_by_slug(slug: str):
    url = f"{SUPABASE_URL}/rest/v1/races?select=*&slug=eq.{slug}&limit=1"
    response = requests.get(url, headers=get_headers())
    data = response.json()

    if len(data) == 0:
        return {"error": "Løb ikke fundet"}

    return data[0]


@app.get("/races/{slug}/stages")
def get_stages_for_race(slug: str):
    # find race id først
    race_url = f"{SUPABASE_URL}/rest/v1/races?select=id&slug=eq.{slug}&limit=1"
    race_res = requests.get(race_url, headers=get_headers())
    race_data = race_res.json()

    if not race_data:
        return []

    race_id = race_data[0]["id"]

    stages_url = f"{SUPABASE_URL}/rest/v1/stages?race_id=eq.{race_id}&order=stage_number.asc"
    stages_res = requests.get(stages_url, headers=get_headers())

    return stages_res.json()