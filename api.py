from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import date
import os
import requests
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)

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
    url = f"{SUPABASE_URL}/rest/v1/races?select=id,name,slug,start_date,end_date,country_code,category&start_date=gt.{today}&order=start_date.asc"
    races = requests.get(url, headers=get_headers()).json()

    # Hent startlist-count per løb
    if races:
        race_ids = [r["id"] for r in races]
        # Supabase understøtter ikke GROUP BY via REST — hent counts enkeltvis i batch
        id_list = ",".join(race_ids)
        sl_url = (
            f"{SUPABASE_URL}/rest/v1/startlists"
            f"?race_id=in.({id_list})&status=eq.active"
            f"&select=race_id"
        )
        sl_data = requests.get(sl_url, headers=get_headers()).json()
        counts: dict[str, int] = {}
        for row in sl_data:
            rid = row["race_id"]
            counts[rid] = counts.get(rid, 0) + 1

        stage_url = (
            f"{SUPABASE_URL}/rest/v1/stages"
            f"?race_id=in.({id_list})&select=race_id"
        )
        stage_data = requests.get(stage_url, headers=get_headers()).json()
        stage_counts: dict[str, int] = {}
        for row in stage_data:
            rid = row["race_id"]
            stage_counts[rid] = stage_counts.get(rid, 0) + 1

        result = []
        for r in races:
            rid = r["id"]
            result.append({
                **{k: v for k, v in r.items() if k != "id"},
                "startlist_count": counts.get(rid, 0),
                "stage_count": stage_counts.get(rid, 0),
            })
        return result

    return races


@app.get("/ongoing-races")
def get_ongoing_races():
    today = date.today().isoformat()
    race_url = (
        f"{SUPABASE_URL}/rest/v1/races"
        f"?select=id,name,slug,start_date,end_date,country_code,category"
        f"&start_date=lte.{today}&end_date=gte.{today}"
        f"&order=start_date.asc"
    )
    races = requests.get(race_url, headers=get_headers()).json()

    result = []
    for race in races:
        stages_url = (
            f"{SUPABASE_URL}/rest/v1/stages"
            f"?race_id=eq.{race['id']}"
            f"&select=stage_number,date,stage_type,start_location,finish_location,distance_km"
            f"&order=stage_number.asc"
        )
        stages = requests.get(stages_url, headers=get_headers()).json()
        completed = sum(1 for s in stages if s.get("date") and s["date"] < today)
        today_stage = next((s for s in stages if s.get("date") == today), None)
        result.append({
            **{k: v for k, v in race.items() if k != "id"},
            "total_stages": len(stages),
            "completed_stages": completed,
            "today_stage": today_stage,
        })
    return result


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
    race_url = f"{SUPABASE_URL}/rest/v1/races?select=id&slug=eq.{slug}&limit=1"
    race_res = requests.get(race_url, headers=get_headers())
    race_data = race_res.json()

    if not race_data:
        return []

    race_id = race_data[0]["id"]
    stages_url = (
        f"{SUPABASE_URL}/rest/v1/stages"
        f"?race_id=eq.{race_id}"
        f"&select=stage_number,name,date,distance_km,stage_type,start_location,finish_location,elevation_gain_m,profile_score,elevation_image_url,pcs_stage_url"
        f"&order=stage_number.asc"
    )
    stages_res = requests.get(stages_url, headers=get_headers())
    return stages_res.json()


@app.get("/races/{slug}/stages/{stage_number}")
def get_stage_detail(slug: str, stage_number: int):
    race_url = f"{SUPABASE_URL}/rest/v1/races?select=id,name,slug&slug=eq.{slug}&limit=1"
    race_res = requests.get(race_url, headers=get_headers())
    race_data = race_res.json()

    if not race_data:
        return {"error": "Løb ikke fundet"}

    race_id = race_data[0]["id"]
    stage_url = (
        f"{SUPABASE_URL}/rest/v1/stages"
        f"?race_id=eq.{race_id}&stage_number=eq.{stage_number}&limit=1"
        f"&select=stage_number,name,date,distance_km,stage_type,start_location,finish_location,"
        f"elevation_gain_m,profile_score,elevation_image_url,pcs_stage_url"
    )
    stage_res = requests.get(stage_url, headers=get_headers())
    stage_data = stage_res.json()

    if not stage_data:
        return {"error": "Etape ikke fundet"}

    return {"stage": stage_data[0], "race": race_data[0]}


@app.get("/races/{slug}/results")
def get_results_for_race(slug: str):
    race_url = f"{SUPABASE_URL}/rest/v1/races?select=id&slug=eq.{slug}&limit=1"
    race_res = requests.get(race_url, headers=get_headers())
    race_data = race_res.json()

    if not race_data:
        return {"error": "Løb ikke fundet"}

    race_id = race_data[0]["id"]
    # Samlet resultat (stage_id er NULL) med rytternavn
    results_url = (
        f"{SUPABASE_URL}/rest/v1/results"
        f"?race_id=eq.{race_id}&stage_id=is.null"
        f"&select=position,time_seconds,time_gap_seconds,dnf,dns,dsq,riders(name,slug,nationality)"
        f"&order=position.asc"
    )
    res = requests.get(results_url, headers=get_headers())
    return res.json()


# --- Teams ---

@app.get("/teams")
def get_teams():
    url = f"{SUPABASE_URL}/rest/v1/teams?select=name,slug,country_code,category,uci_team_code&order=name.asc"
    response = requests.get(url, headers=get_headers())
    return response.json()


@app.get("/teams/{slug}")
def get_team_by_slug(slug: str):
    url = f"{SUPABASE_URL}/rest/v1/teams?select=*&slug=eq.{slug}&limit=1"
    response = requests.get(url, headers=get_headers())
    data = response.json()

    if not data:
        return {"error": "Hold ikke fundet"}

    return data[0]


@app.get("/teams/{slug}/riders")
def get_riders_for_team(slug: str):
    team_url = f"{SUPABASE_URL}/rest/v1/teams?select=id&slug=eq.{slug}&limit=1"
    team_res = requests.get(team_url, headers=get_headers())
    team_data = team_res.json()

    if not team_data:
        return []

    team_id = team_data[0]["id"]
    riders_url = (
        f"{SUPABASE_URL}/rest/v1/riders"
        f"?team_id=eq.{team_id}"
        f"&select=name,slug,nationality,speciality,uci_ranking"
        f"&order=name.asc"
    )
    res = requests.get(riders_url, headers=get_headers())
    return res.json()


# --- Riders ---

@app.get("/riders")
def get_riders():
    url = (
        f"{SUPABASE_URL}/rest/v1/riders"
        f"?select=name,slug,nationality,speciality,uci_ranking,teams(name,slug)"
        f"&order=uci_ranking.asc.nullslast"
    )
    response = requests.get(url, headers=get_headers())
    return response.json()


@app.get("/races/{slug}/startlist")
def get_startlist_for_race(slug: str):
    race_url = f"{SUPABASE_URL}/rest/v1/races?select=id&slug=eq.{slug}&limit=1"
    race_res = requests.get(race_url, headers=get_headers())
    race_data = race_res.json()

    if not race_data:
        return []

    race_id = race_data[0]["id"]
    url = (
        f"{SUPABASE_URL}/rest/v1/startlists"
        f"?race_id=eq.{race_id}"
        f"&select=bib_number,is_gc_captain,is_sprint_captain,status,role,"
        f"riders(name,slug,nationality,speciality,date_of_birth),"
        f"teams(name,slug,country_code)"
        f"&status=eq.active"
        f"&order=bib_number.asc.nullslast"
    )
    res = requests.get(url, headers=get_headers())
    return res.json()


@app.get("/races/{slug}/gc")
def get_gc_for_race(slug: str):
    race_url = f"{SUPABASE_URL}/rest/v1/races?select=id&slug=eq.{slug}&limit=1"
    race_data = requests.get(race_url, headers=get_headers()).json()
    if not race_data:
        return []
    race_id = race_data[0]["id"]

    # Seneste etape med GC-data
    latest_url = (
        f"{SUPABASE_URL}/rest/v1/classifications"
        f"?race_id=eq.{race_id}&classification_type=eq.gc"
        f"&select=after_stage_number&order=after_stage_number.desc&limit=1"
    )
    latest = requests.get(latest_url, headers=get_headers()).json()
    if not latest:
        return []
    after_stage = latest[0]["after_stage_number"]

    gc_url = (
        f"{SUPABASE_URL}/rest/v1/classifications"
        f"?race_id=eq.{race_id}&classification_type=eq.gc&after_stage_number=eq.{after_stage}"
        f"&select=position,time_gap_seconds,riders(name,slug,nationality,speciality,teams(name,slug))"
        f"&order=position.asc&limit=20"
    )
    data = requests.get(gc_url, headers=get_headers()).json()
    return {"after_stage": after_stage, "standings": data}


@app.get("/races/{slug}/classifications/{classif_type}")
def get_classification(slug: str, classif_type: str):
    if classif_type not in ("gc", "points", "mountains", "youth"):
        return {"error": "Ukendt klassement"}
    race_url = f"{SUPABASE_URL}/rest/v1/races?select=id&slug=eq.{slug}&limit=1"
    race_data = requests.get(race_url, headers=get_headers()).json()
    if not race_data:
        return []
    race_id = race_data[0]["id"]

    latest_url = (
        f"{SUPABASE_URL}/rest/v1/classifications"
        f"?race_id=eq.{race_id}&classification_type=eq.{classif_type}"
        f"&select=after_stage_number&order=after_stage_number.desc&limit=1"
    )
    latest = requests.get(latest_url, headers=get_headers()).json()
    if not latest:
        return []
    after_stage = latest[0]["after_stage_number"]

    url = (
        f"{SUPABASE_URL}/rest/v1/classifications"
        f"?race_id=eq.{race_id}&classification_type=eq.{classif_type}&after_stage_number=eq.{after_stage}"
        f"&select=position,time_gap_seconds,points,riders(name,slug,nationality)"
        f"&order=position.asc&limit=20"
    )
    data = requests.get(url, headers=get_headers()).json()
    return {"after_stage": after_stage, "standings": data}


@app.get("/races/{slug}/dnfs")
def get_dnfs_for_race(slug: str):
    race_url = f"{SUPABASE_URL}/rest/v1/races?select=id&slug=eq.{slug}&limit=1"
    race_data = requests.get(race_url, headers=get_headers()).json()
    if not race_data:
        return []
    race_id = race_data[0]["id"]

    url = (
        f"{SUPABASE_URL}/rest/v1/startlists"
        f"?race_id=eq.{race_id}&status=neq.active"
        f"&select=status,dnf_stage_number,bib_number,riders(name,slug,nationality),teams(name,slug)"
        f"&order=dnf_stage_number.asc.nullslast"
    )
    return requests.get(url, headers=get_headers()).json()



@app.get("/riders/{slug}/races")
def get_rider_races(slug: str):
    rider_url = f"{SUPABASE_URL}/rest/v1/riders?select=id&slug=eq.{slug}&limit=1"
    rider_data = requests.get(rider_url, headers=get_headers()).json()
    if not rider_data:
        return []
    rider_id = rider_data[0]["id"]
    url = (
        f"{SUPABASE_URL}/rest/v1/startlists"
        f"?rider_id=eq.{rider_id}&status=eq.active"
        f"&select=bib_number,is_gc_captain,is_sprint_captain,"
        f"races(name,slug,start_date,end_date,country_code,category,race_type)"
    )
    data = requests.get(url, headers=get_headers()).json()
    data.sort(key=lambda x: (x.get("races") or {}).get("start_date") or "")
    return data


@app.get("/riders/{slug}")
def get_rider_by_slug(slug: str):
    url = (
        f"{SUPABASE_URL}/rest/v1/riders"
        f"?slug=eq.{slug}&limit=1"
        f"&select=*,teams(name,slug,country_code)"
    )
    response = requests.get(url, headers=get_headers())
    data = response.json()

    if not data:
        return {"error": "Rytter ikke fundet"}

    return data[0]


# --- News ---

@app.get("/news")
def get_news(advertorial: bool = False, limit: int = 20, offset: int = 0):
    url = (
        f"{SUPABASE_URL}/rest/v1/news_articles"
        f"?is_advertorial=eq.{str(advertorial).lower()}"
        f"&select=id,slug,title,excerpt,category,author,image_url,published_at,race_id,races(name,slug)"
        f"&order=published_at.desc"
        f"&limit={limit}&offset={offset}"
    )
    return requests.get(url, headers=get_headers()).json()


@app.get("/news/{slug}")
def get_news_article(slug: str):
    url = (
        f"{SUPABASE_URL}/rest/v1/news_articles"
        f"?slug=eq.{slug}&limit=1"
        f"&select=*,races(name,slug)"
    )
    data = requests.get(url, headers=get_headers()).json()
    if not data:
        return {"error": "Artikel ikke fundet"}
    return data[0]