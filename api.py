from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import date
import ast
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
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def get_headers():
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }


def normalize_fun_facts(raw) -> list | None:
    """Convert fun_facts to a list regardless of how it was stored in the DB."""
    if raw is None:
        return None
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None
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
    return [text]


@app.get("/")
def root():
    return {"message": "API virker"}


@app.get("/races")
def get_races():
    url = f"{SUPABASE_URL}/rest/v1/races?select=id,name,slug,start_date,end_date,country_code,category&order=start_date.asc"
    races = requests.get(url, headers=get_headers()).json()
    if not races:
        return races
    race_ids = [r["id"] for r in races]
    id_list = ",".join(race_ids)
    stage_data = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages?race_id=in.({id_list})&select=race_id",
        headers=get_headers(),
    ).json()
    stage_counts: dict[str, int] = {}
    for row in stage_data:
        rid = row["race_id"]
        stage_counts[rid] = stage_counts.get(rid, 0) + 1
    return [
        {**{k: v for k, v in r.items() if k != "id"}, "stage_count": stage_counts.get(r["id"], 0)}
        for r in races
    ]


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
            f"&select=stage_number,date,stage_type,start_location,finish_location,distance_km,elevation_image_url,stage_start_time"
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
        f"&select=stage_number,name,date,distance_km,stage_type,start_location,finish_location,elevation_gain_m,profile_score,elevation_image_url,pcs_stage_url,stage_start_time"
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
        f"elevation_gain_m,profile_score,elevation_image_url,pcs_stage_url,"
        f"description,finish_type,fun_facts,stage_start_time,route_points"
    )
    stage_res = requests.get(stage_url, headers=get_headers())
    stage_data = stage_res.json()

    if not stage_data:
        return {"error": "Etape ikke fundet"}

    stage = stage_data[0]
    stage["fun_facts"] = normalize_fun_facts(stage.get("fun_facts"))
    return {"stage": stage, "race": race_data[0]}


@app.get("/races/{slug}/stages/{stage_number}/results")
def get_stage_results(slug: str, stage_number: int, limit: int = 10):
    """Top-N finishers på en enkelt etape (historiske + live løb)."""
    race_res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?select=id&slug=eq.{slug}&limit=1",
        headers=get_headers(),
    )
    race_data = race_res.json()
    if not race_data:
        return []
    race_id = race_data[0]["id"]

    stage_res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages?race_id=eq.{race_id}&stage_number=eq.{stage_number}&select=id&limit=1",
        headers=get_headers(),
    )
    stage_data = stage_res.json()
    if not stage_data:
        return []
    stage_id = stage_data[0]["id"]

    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/results"
        f"?stage_id=eq.{stage_id}"
        f"&select=position,time_seconds,time_gap_seconds,riders(name,slug,nationality,photo_url)"
        f"&order=position.asc&limit={limit}",
        headers=get_headers(),
    )
    return res.json() if res.ok and isinstance(res.json(), list) else []


@app.get("/races/{slug}/stages/{stage_number}/gc")
def get_gc_after_stage(slug: str, stage_number: int):
    """GC-klassement efter en bestemt etape."""
    race_res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?select=id&slug=eq.{slug}&limit=1",
        headers=get_headers(),
    )
    race_data = race_res.json()
    if not race_data:
        return []
    race_id = race_data[0]["id"]

    url = (
        f"{SUPABASE_URL}/rest/v1/classifications"
        f"?race_id=eq.{race_id}&classification_type=eq.gc&after_stage_number=eq.{stage_number}"
        f"&select=position,time_gap_seconds,riders(name,slug,nationality,photo_url,teams(name,slug))"
        f"&order=position.asc&limit=20"
    )
    data = requests.get(url, headers=get_headers()).json()
    if not isinstance(data, list) or not data:
        return []
    return {"after_stage": stage_number, "standings": data}


@app.get("/races/{slug}/history")
def get_race_history(slug: str):
    """
    Tidligere udgaver af samme løb — GC-vinder (pos=1) per år.
    Matcher på løbsnavn (case-insensitive) på tværs af alle år.
    Bruger én bulk-forespørgsel til alle vindere i stedet for N+1.
    """
    race_res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?select=id,name&slug=eq.{slug}&limit=1",
        headers=get_headers(),
    )
    race_data = race_res.json()
    if not race_data:
        return []
    race_name = race_data[0]["name"]

    editions_res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races"
        f"?name=eq.{requests.utils.quote(race_name)}"
        f"&select=id,slug,start_date"
        f"&order=start_date.desc&limit=20",
        headers=get_headers(),
    )
    editions = editions_res.json()
    if not isinstance(editions, list):
        return []

    other_editions = [ed for ed in editions if ed["slug"] != slug]
    if not other_editions:
        return []

    # Én bulk-forespørgsel til alle GC-vindere på tværs af udgaver
    edition_ids = ",".join(ed["id"] for ed in other_editions)
    gc_res = requests.get(
        f"{SUPABASE_URL}/rest/v1/classifications"
        f"?race_id=in.({edition_ids})&classification_type=eq.gc&position=eq.1"
        f"&select=race_id,position,time_gap_seconds,after_stage_number,"
        f"riders(name,slug,nationality,photo_url)"
        f"&order=after_stage_number.desc",
        headers=get_headers(),
    )
    _gc_body = gc_res.json() if gc_res.ok else []
    gc_rows = _gc_body if isinstance(_gc_body, list) else []

    # Behold kun den seneste entry per race_id (første match = højeste after_stage_number)
    winners_by_race: dict = {}
    for row in gc_rows:
        rid = row.get("race_id")
        if rid and rid not in winners_by_race:
            winners_by_race[rid] = row

    history = []
    for ed in other_editions:
        history.append({
            "year":       int(ed["start_date"][:4]),
            "slug":       ed["slug"],
            "start_date": ed["start_date"],
            "winner":     winners_by_race.get(ed["id"]),
        })
    return history


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
        f"&select=name,slug,nationality,speciality,uci_ranking,photo_url"
        f"&order=name.asc"
    )
    res = requests.get(riders_url, headers=get_headers())
    return res.json()


# --- Riders ---

@app.get("/riders")
def get_riders():
    url = (
        f"{SUPABASE_URL}/rest/v1/riders"
        f"?select=name,slug,nationality,speciality,uci_ranking,photo_url,teams(name,slug)"
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
        f"riders(name,slug,nationality,speciality,date_of_birth,uci_ranking,photo_url,hometown_region,training_region),"
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
        f"&select=position,time_gap_seconds,riders(name,slug,nationality,speciality,photo_url,teams(name,slug))"
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
        f"&select=position,time_gap_seconds,points,riders(name,slug,nationality,photo_url,teams(name,slug))"
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



@app.get("/races/{slug}/broadcast")
def get_broadcast(slug: str):
    race_url = f"{SUPABASE_URL}/rest/v1/races?select=id&slug=eq.{slug}&limit=1"
    race_data = requests.get(race_url, headers=get_headers()).json()
    if not race_data:
        return []
    race_id = race_data[0]["id"]
    url = (
        f"{SUPABASE_URL}/rest/v1/broadcast_schedule"
        f"?race_id=eq.{race_id}"
        f"&select=stage_number,broadcast_date,start_time,end_time,broadcaster,stream_url,is_live,notes"
        f"&order=broadcast_date.asc,start_time.asc"
    )
    return requests.get(url, headers=get_headers()).json()


@app.get("/races/{slug}/stages/{stage_number}/climbs")
def get_stage_climbs(slug: str, stage_number: int):
    race_url = f"{SUPABASE_URL}/rest/v1/races?select=id&slug=eq.{slug}&limit=1"
    race_data = requests.get(race_url, headers=get_headers()).json()
    if not race_data:
        return []
    race_id = race_data[0]["id"]
    stage_url = f"{SUPABASE_URL}/rest/v1/stages?race_id=eq.{race_id}&stage_number=eq.{stage_number}&select=id&limit=1"
    stage_data = requests.get(stage_url, headers=get_headers()).json()
    if not stage_data:
        return []
    stage_id = stage_data[0]["id"]
    url = (
        f"{SUPABASE_URL}/rest/v1/stage_climbs"
        f"?stage_id=eq.{stage_id}"
        f"&select=id,name,km_from_start,length_km,elevation_m,avg_gradient,max_gradient,gradient_sections,profile_image_url,region"
        f"&order=sort_order.asc"
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


@app.get("/riders/{slug}/stage-wins")
def get_rider_stage_wins(slug: str):
    rider_url = f"{SUPABASE_URL}/rest/v1/riders?select=id&slug=eq.{slug}&limit=1"
    rider_data = requests.get(rider_url, headers=get_headers()).json()
    if not rider_data:
        return []
    rider_id = rider_data[0]["id"]
    url = (
        f"{SUPABASE_URL}/rest/v1/results"
        f"?rider_id=eq.{rider_id}&position=eq.1&stage_id=not.is.null"
        f"&select=stages(stage_number,finish_location,date,races(name,slug))"
    )
    data = requests.get(url, headers=get_headers()).json()
    if not isinstance(data, list):
        return []
    data.sort(key=lambda x: (x.get("stages") or {}).get("date") or "", reverse=True)
    return data


@app.get("/riders/{slug}/palmares")
def get_rider_palmares(slug: str):
    """
    Rytterens karriereresultater: GC top-10 finishes + etapesejre på tværs af alle år.
    Sorteret med nyeste først.
    """
    rider_res = requests.get(
        f"{SUPABASE_URL}/rest/v1/riders?select=id&slug=eq.{slug}&limit=1",
        headers=get_headers(),
    )
    rider_data = rider_res.json()
    if not rider_data:
        return {"gc_results": [], "stage_wins": []}
    rider_id = rider_data[0]["id"]

    # GC-klassementer top 10 — hent alle og beholder kun seneste per løb
    gc_res = requests.get(
        f"{SUPABASE_URL}/rest/v1/classifications"
        f"?rider_id=eq.{rider_id}&classification_type=eq.gc&position=lte.10"
        f"&select=position,time_gap_seconds,after_stage_number,"
        f"races(name,slug,start_date,end_date,race_type)"
        f"&order=after_stage_number.desc&limit=500",
        headers=get_headers(),
    )
    raw_gc = gc_res.json() if gc_res.ok and isinstance(gc_res.json(), list) else []

    # Dedupliker: behold kun den post med højest after_stage_number per løb
    best_per_race: dict = {}
    for entry in raw_gc:
        race = entry.get("races") or {}
        slug = race.get("slug")
        if not slug:
            continue
        if slug not in best_per_race:
            best_per_race[slug] = entry
    gc_results = sorted(
        best_per_race.values(),
        key=lambda e: (e.get("races") or {}).get("start_date", ""),
        reverse=True,
    )

    # Etapesejre (position=1 med stage_id)
    wins_res = requests.get(
        f"{SUPABASE_URL}/rest/v1/results"
        f"?rider_id=eq.{rider_id}&position=eq.1&stage_id=not.is.null"
        f"&select=stages(stage_number,date,finish_location,races(name,slug,start_date))"
        f"&order=stages(date).desc&limit=100",
        headers=get_headers(),
    )
    stage_wins = wins_res.json() if wins_res.ok and isinstance(wins_res.json(), list) else []

    return {"gc_results": gc_results, "stage_wins": stage_wins}


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
def get_news(advertorial: bool = False, limit: int = 20, offset: int = 0, race_slug: str = None):
    filters = (
        f"?is_advertorial=eq.{str(advertorial).lower()}"
        f"&status=eq.published"
    )
    if race_slug:
        # Join through races to filter by slug
        filters += f"&races.slug=eq.{race_slug}"
    url = (
        f"{SUPABASE_URL}/rest/v1/news_articles"
        + filters
        + f"&select=id,slug,title,excerpt,category,author,image_url,published_at,race_id,races!inner(name,slug)"
        + f"&order=published_at.desc"
        + f"&limit={limit}&offset={offset}"
    ) if race_slug else (
        f"{SUPABASE_URL}/rest/v1/news_articles"
        + filters
        + f"&select=id,slug,title,excerpt,category,author,image_url,published_at,race_id,races(name,slug)"
        + f"&order=published_at.desc"
        + f"&limit={limit}&offset={offset}"
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


# --- Admin ---

ADMIN_KEY = os.getenv("ADMIN_KEY", "")


def _require_admin(request: Request) -> None:
    if not ADMIN_KEY or request.headers.get("x-admin-key") != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


ISSUES_MD_PATH = os.path.join(os.path.dirname(__file__), "state", "issues.md")


def _parse_issues_md() -> list[dict]:
    """Parser status/opgave-tabellen i state/issues.md til JSON til opgave-dashboardet."""
    if not os.path.exists(ISSUES_MD_PATH):
        return []
    issues = []
    with open(ISSUES_MD_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 5:
                continue
            if cells[0] == "ID" or cells[0].strip("-") == "":
                continue
            issues.append({
                "id": cells[0],
                "priority": cells[1],
                "status": cells[2],
                "owner": cells[3],
                "description": " | ".join(cells[4:]),
            })
    return issues


@app.get("/admin/issues")
def admin_get_issues(request: Request):
    _require_admin(request)
    return _parse_issues_md()


@app.get("/admin/articles")
def admin_get_articles(request: Request, status: str = "draft", limit: int = 50):
    _require_admin(request)
    url = (
        f"{SUPABASE_URL}/rest/v1/news_articles"
        f"?status=eq.{status}"
        f"&select=id,slug,title,excerpt,category,author,image_url,published_at,created_at,source_url"
        f"&order=created_at.desc"
        f"&limit={limit}"
    )
    return requests.get(url, headers=get_headers()).json()


def _get_article_for_fb(article_id: str) -> dict | None:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/news_articles"
        f"?id=eq.{article_id}&select=slug,title,category,excerpt,image_url&limit=1",
        headers=get_headers(),
    )
    data = res.json()
    return data[0] if res.ok and data else None


def _fb_task(article_id: str) -> None:
    from fb_article_image import generate_and_post
    art = _get_article_for_fb(article_id)
    if not art:
        return
    generate_and_post(
        article_id=article_id,
        slug=art["slug"],
        title=art["title"],
        category=art.get("category", "generelt"),
        excerpt=art.get("excerpt"),
        sb_url=SUPABASE_URL,
        sb_key=SUPABASE_SERVICE_ROLE_KEY,
        meta_token=os.getenv("META_PAGE_ACCESS_TOKEN", ""),
        page_id=os.getenv("META_PAGE_ID", ""),
    )


INDEXNOW_KEY = "1a5a3688cfd86781c40cef01ce453403"
INDEXNOW_HOST = "klassementet.dk"


def submit_indexnow(urls: list[str]) -> None:
    """Melder nye/opdaterede URL'er til IndexNow (Bing/Yandex) for hurtigere crawl. Jf. SEO-007."""
    if not urls:
        return
    try:
        requests.post(
            "https://api.indexnow.org/indexnow",
            json={
                "host": INDEXNOW_HOST,
                "key": INDEXNOW_KEY,
                "keyLocation": f"https://{INDEXNOW_HOST}/{INDEXNOW_KEY}.txt",
                "urlList": urls,
            },
            timeout=10,
        )
    except requests.RequestException:
        pass


def _indexnow_task(article_id: str) -> None:
    art = _get_article_for_fb(article_id)
    if not art:
        return
    submit_indexnow([f"https://{INDEXNOW_HOST}/nyheder/{art['slug']}"])


def _ig_task(article_id: str) -> None:
    ig_user_id = os.getenv("META_INSTAGRAM_USER_ID", "")
    if not ig_user_id:
        return
    try:
        from instagram_image import generate_and_post_ig
        art = _get_article_for_fb(article_id)
        if not art:
            return
        generate_and_post_ig(
            article_id=article_id,
            slug=art["slug"],
            title=art["title"],
            category=art.get("category", "generelt"),
            excerpt=art.get("excerpt"),
            existing_image_url=art.get("image_url"),
            sb_url=SUPABASE_URL,
            sb_key=SUPABASE_SERVICE_ROLE_KEY,
            meta_token=os.getenv("META_PAGE_ACCESS_TOKEN", ""),
            ig_user_id=ig_user_id,
        )
    except Exception:
        pass


@app.patch("/admin/articles/{article_id}/approve")
def admin_approve_article(article_id: str, request: Request, background_tasks: BackgroundTasks):
    _require_admin(request)
    from datetime import datetime, timezone
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/news_articles?id=eq.{article_id}",
        json={"status": "published", "published_at": datetime.now(timezone.utc).isoformat()},
        headers={**get_headers(), "Content-Type": "application/json", "Prefer": "return=minimal"},
    )
    if res.ok:
        background_tasks.add_task(_fb_task, article_id)
        background_tasks.add_task(_indexnow_task, article_id)
    return {"ok": res.ok}


@app.patch("/admin/articles/{article_id}/reject")
def admin_reject_article(article_id: str, request: Request):
    _require_admin(request)
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/news_articles?id=eq.{article_id}",
        json={"status": "rejected"},
        headers={**get_headers(), "Content-Type": "application/json", "Prefer": "return=minimal"},
    )
    return {"ok": res.ok}


@app.delete("/admin/articles/{article_id}")
def admin_delete_article(article_id: str, request: Request):
    _require_admin(request)
    res = requests.delete(
        f"{SUPABASE_URL}/rest/v1/news_articles?id=eq.{article_id}",
        headers={**get_headers(), "Prefer": "return=minimal"},
    )
    return {"ok": res.ok}


class EditFeedbackRequest(BaseModel):
    feedback: str


@app.patch("/admin/articles/{article_id}/edit")
async def admin_edit_article(article_id: str, body: EditFeedbackRequest, request: Request, background_tasks: BackgroundTasks):
    _require_admin(request)
    import json
    import re
    from datetime import datetime, timezone
    from anthropic import AsyncAnthropic, APITimeoutError, AuthenticationError, APIError

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY ikke sat i Railway — tilføj den under Variables")

    # Hent eksisterende artikel
    fetch = requests.get(
        f"{SUPABASE_URL}/rest/v1/news_articles?id=eq.{article_id}&select=title,content,category",
        headers=get_headers(),
    )
    if not fetch.ok or not fetch.json():
        raise HTTPException(status_code=404, detail="Article not found")
    article = fetch.json()[0]

    prompt = (
        f"Ret følgende artikel baseret på denne feedback fra redaktøren:\n\n"
        f"FEEDBACK: {body.feedback}\n\n"
        f"ARTIKEL TITEL: {article['title']}\n\n"
        f"ARTIKEL INDHOLD:\n{article['content']}\n\n"
        "Returner KUN dette JSON (ingen markdown-blokke):\n"
        '{"title": "...", "content": "..."}'
    )

    try:
        client = AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
            timeout=25.0,
        )
    except APITimeoutError:
        raise HTTPException(status_code=504, detail="Claude API timeout (>25s) — prøv igen")
    except AuthenticationError:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY er ugyldig")
    except APIError as e:
        raise HTTPException(status_code=503, detail=f"Claude API fejl: {e.message[:120]}")

    text = resp.content[0].text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        result = json.loads(text)
    except Exception:
        raise HTTPException(status_code=500, detail="Claude returnerede ugyldig JSON")

    # Gem og publicer
    patch = requests.patch(
        f"{SUPABASE_URL}/rest/v1/news_articles?id=eq.{article_id}",
        json={
            "title": result.get("title", article["title"]),
            "content": result.get("content", article["content"]),
            "status": "published",
            "published_at": datetime.now(timezone.utc).isoformat(),
        },
        headers={**get_headers(), "Content-Type": "application/json", "Prefer": "return=minimal"},
    )
    if patch.ok:
        background_tasks.add_task(_fb_task, article_id)
    return {"ok": patch.ok}


def _today_start_iso() -> str:
    from datetime import datetime, timezone
    dt = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@app.get("/admin/instagram/today-articles")
def admin_today_articles(request: Request):
    """Returnerer alle artikler publiceret i dag — bruges til artikel-selektion i admin-panel."""
    _require_admin(request)
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/news_articles"
        f"?status=eq.published"
        f"&published_at=gte.{_today_start_iso()}"
        f"&select=id,slug,title,category"
        f"&order=published_at.asc"
        f"&limit=50",
        headers=get_headers(),
    )
    if not res.ok:
        raise HTTPException(status_code=500, detail="Kunne ikke hente artikler fra Supabase")
    data = res.json()
    return data if isinstance(data, list) else []


@app.post("/admin/instagram/post-dagens-nyheder")
async def admin_post_dagens_nyheder(request: Request):
    """Henter artikler publiceret i dag og poster dem som Instagram-karrusel.
    Accepterer optional JSON body: {"article_ids": ["uuid1", "uuid2", ...]}
    Hvis article_ids er angivet, bruges kun de valgte artikler.
    Kører synkront og returnerer det faktiske resultat (inkl. fejlbesked).
    """
    _require_admin(request)

    # Læs optional body
    article_ids: list[str] | None = None
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            body = await request.json()
            article_ids = body.get("article_ids") or None
        except Exception:
            pass

    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/news_articles"
        f"?status=eq.published"
        f"&published_at=gte.{_today_start_iso()}"
        f"&select=id,slug,title,category,excerpt,image_url"
        f"&order=published_at.asc"
        f"&limit=50",
        headers=get_headers(),
    )
    if not res.ok:
        raise HTTPException(status_code=500, detail="Kunne ikke hente artikler fra Supabase")

    articles = res.json()
    if not isinstance(articles, list) or len(articles) == 0:
        return {
            "ok": False, "slides": 0, "ig_post_id": None,
            "saved_path": "", "error": "Ingen artikler publiceret i dag",
            "article_count": 0,
        }

    # Filtrer til valgte artikler hvis angivet
    if article_ids:
        id_set = set(article_ids)
        articles = [a for a in articles if a["id"] in id_set]
        if not articles:
            return {
                "ok": False, "slides": 0, "ig_post_id": None,
                "saved_path": "", "error": "Ingen af de valgte artikler findes blandt dagens publicerede",
                "article_count": 0,
            }

    # Kør synkront i thread pool så vi returnerer det faktiske resultat og fejlbeskeder
    import asyncio
    from instagram_carousel import post_dagens_nyheder

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: post_dagens_nyheder(
            articles=articles,
            sb_url=SUPABASE_URL,
            sb_key=SUPABASE_SERVICE_ROLE_KEY,
            meta_token=os.getenv("META_PAGE_ACCESS_TOKEN", ""),
            ig_user_id=os.getenv("META_INSTAGRAM_USER_ID", ""),
        ),
    )

    if result.get("ok"):
        result["message"] = f"Karrusel med {result.get('slides', 0)} slides postet"
    result["article_count"] = len(articles)
    print(f"[Carousel] Resultat: {result}")
    return result


# --- Search ---

@app.get("/search")
def search(q: str = ""):
    if not q or len(q.strip()) < 2:
        return {"riders": [], "races": [], "teams": [], "climbs": []}

    term = q.strip()
    h = get_headers()

    def sb_ilike(table: str, select: str, field: str = "name", limit: int = 5) -> list:
        try:
            res = requests.get(
                f"{SUPABASE_URL}/rest/v1/{table}",
                params={"select": select, field: f"ilike.%{term}%", "limit": limit},
                headers=h,
            )
            data = res.json()
            return data if isinstance(data, list) else []
        except Exception:
            return []

    return {
        "riders": sb_ilike("riders", "name,slug,nationality,speciality"),
        "races":  sb_ilike("races",  "name,slug,start_date,category"),
        "teams":  sb_ilike("teams",  "name,slug,country_code"),
        "climbs": sb_ilike(
            "stage_climbs",
            "name,stage_id,stages(stage_number,race_id,races(name,slug))",
        ),
    }