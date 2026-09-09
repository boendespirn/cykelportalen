from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import ast
import os
import requests
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

DK_TZ = ZoneInfo("Europe/Copenhagen")


def today_dk() -> date:
    """Dagens dato i dansk lokal tid — brug ALTID denne, ikke date.today(),
    da serveren kører i UTC og ellers viser gårsdagens etape som "i dag"
    mellem midnat og kl. 02 dansk tid (sommertid)."""
    return datetime.now(DK_TZ).date()

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
        f"{SUPABASE_URL}/rest/v1/stages?race_id=in.({id_list})&select=race_id,stage_number,elevation_image_url"
        f"&order=race_id.asc,stage_number.asc",
        headers=get_headers(),
    ).json()
    stage_counts: dict[str, int] = {}
    # ready_through_stage: højeste SAMMENHÆNGENDE etapenummer fra 1, hvor
    # elevation_image_url er sat — bruges af sitemap.ts til at afgøre hvilke
    # historiske etapesider reelt er backfillet (ikke stadig skeleton-data),
    # så vi ikke genindfører 404'er i sitemappet (jf. SEO-019/SEO-022/SEO-023).
    stages_by_race: dict[str, list[dict]] = {}
    for row in stage_data:
        rid = row["race_id"]
        stage_counts[rid] = stage_counts.get(rid, 0) + 1
        stages_by_race.setdefault(rid, []).append(row)

    ready_through: dict[str, int] = {}
    for rid, rows in stages_by_race.items():
        rows_sorted = sorted(rows, key=lambda r: r["stage_number"] or 0)
        ready = 0
        for i, row in enumerate(rows_sorted, start=1):
            if row["stage_number"] != i or not row.get("elevation_image_url"):
                break
            ready = i
        ready_through[rid] = ready

    return [
        {
            **{k: v for k, v in r.items() if k != "id"},
            "stage_count": stage_counts.get(r["id"], 0),
            "ready_through_stage": ready_through.get(r["id"], 0),
        }
        for r in races
    ]


@app.get("/upcoming-races")
def get_upcoming_races():
    today = today_dk().isoformat()
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
    today = today_dk().isoformat()
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
            f"&select=stage_number,date,stage_type,start_location,finish_location,distance_km,elevation_image_url,elevation_image_source,stage_start_time"
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
        f"&select=stage_number,name,date,distance_km,stage_type,start_location,finish_location,elevation_gain_m,profile_score,elevation_image_url,elevation_image_source,pcs_stage_url,stage_start_time,historic_recap"
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
        f"elevation_gain_m,profile_score,elevation_image_url,elevation_image_source,sprints,"
        f"pcs_stage_url,description,finish_type,fun_facts,stage_start_time,route_points,historic_recap,"
        f"stage_recap"
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


@app.get("/races/{slug}/stages/{stage_number}/classifications/{classif_type}")
def get_classification_after_stage(slug: str, stage_number: int, classif_type: str):
    """Et klassement (gc/points/mountains/youth) som det så ud efter en bestemt etape."""
    if classif_type not in ("gc", "points", "mountains", "youth"):
        return {"error": "Ukendt klassement"}

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
        f"?race_id=eq.{race_id}&classification_type=eq.{classif_type}&after_stage_number=eq.{stage_number}"
        f"&select=position,time_gap_seconds,points,riders(name,slug,nationality,photo_url,teams(name,slug))"
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
        f"&select=id,name,km_from_start,length_km,elevation_m,avg_gradient,max_gradient,category,gradient_sections,profile_image_url,veloviewer_segment_id,region,source"
        # Kronologisk rækkefølge langs ruten (OPT-005). sort_order er 0 for
        # samtlige rækker i DB og bærer derfor ingen information — den kan ikke
        # bruges som primær nøgle uden at rækkefølgen bliver vilkårlig igen.
        f"&order=km_from_start.asc.nullslast,id.asc"
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
        f"&select=stages(stage_number,finish_location,date,elevation_image_url,races(name,slug))"
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

    # Kun AFSLUTTEDE løb tæller som palmares — et igangværende etapeløbs
    # mellemstilling er ikke en sejr/placering endnu (jf. CLAUDE.md §4/§6).
    today = today_dk().isoformat()

    # Dedupliker: behold kun den post med højest after_stage_number per løb
    best_per_race: dict = {}
    for entry in raw_gc:
        race = entry.get("races") or {}
        slug = race.get("slug")
        end_date = race.get("end_date")
        if not slug or not end_date or end_date >= today:
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
        f"&select=stages(stage_number,date,finish_location,elevation_image_url,races(name,slug,start_date))"
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

# --- Admin: pipeline-dashboard -----------------------------------------------
# Knapperne her udfører intet selv. De lægger en række i agent_runs, som
# runner.py på ejerens PC henter og kører. Agenterne kræver Playwright,
# ClimbFinder-login og lokale GPX-kilder — det miljø findes ikke på Railway.

import agent_catalog
from race_completeness import race_completeness

RUNS_TABLE = f"{SUPABASE_URL}/rest/v1/agent_runs"

# Hvor gammelt et hjerteslag må være, før runneren regnes som nede. Den slår
# hvert 15. sekund, så 90 sekunder rummer et par tabte kald uden falsk alarm.
RUNNER_STALE_SECONDS = 90

# Fortryd-vinduet: runneren må ikke tage jobbet før så mange sekunder efter
# klikket. Uden det ville et klik, der tilfældigvis ramte lige før runnerens
# poll, være i gang med at skrive i databasen, inden man nåede at fortryde —
# og hele pointen med Afbryd er at nå det, FØR noget ændres på sitet.
CANCEL_WINDOW_SECONDS = 30


def _runs_for(race_slug: str | None, limit: int = 200) -> list:
    """Seneste kørsler, nyeste først. Uden race_slug: alle."""
    race_filter = f"&race_slug=eq.{race_slug}" if race_slug else ""
    res = requests.get(
        f"{RUNS_TABLE}?select=id,job_key,race_slug,stage_number,status,trigger,"
        f"queued_at,not_before,started_at,finished_at,exit_code,cancel_requested,"
        f"validation_verdict,validation_note"
        f"{race_filter}&order=queued_at.desc&limit={limit}",
        headers=get_headers(),
    )
    return res.json() if res.ok and isinstance(res.json(), list) else []


def _last_run_by_job(runs: list) -> dict:
    """Nyeste koersel pr. job_key. Listen kommer sorteret nyest foerst, saa den
    foerste forekomst af et job_key er den seneste."""
    latest = {}
    for run in runs:
        latest.setdefault(run["job_key"], run)
    return latest


@app.get("/admin/pipelines/jobs")
def admin_pipeline_jobs(request: Request):
    """Kataloget over, hvad der kan koeres — kilden til knapperne i dashboardet."""
    _require_admin(request)
    return {
        "jobs": agent_catalog.list_jobs(),
        "phase_labels": agent_catalog.PHASE_LABELS,
        "cancel_window_seconds": CANCEL_WINDOW_SECONDS,
    }


def _runner_health() -> dict:
    """Er runneren i live? Bruges baade af status-endpointet og af Afbryd.

    Ligger i en delt funktion, fordi Afbryd traeffer en beslutning paa den:
    svarer runneren ikke, er der ingen til at draebe processen, og koerslen skal
    kunne frigives fra dashboardet i stedet for at staa som "Stopper ..." for
    evigt.
    """
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/runner_status?select=host,last_seen"
        f"&order=last_seen.desc&limit=1",
        headers=get_headers(),
    )
    rows = res.json() if res.ok and isinstance(res.json(), list) else []
    if not rows:
        return {"online": False, "host": None, "last_seen": None, "seconds_since": None,
                "message": "Runneren har aldrig meldt sig. Start den med: python runner.py"}

    row = rows[0]
    seen = datetime.fromisoformat(row["last_seen"].replace("Z", "+00:00"))
    age = (datetime.now(seen.tzinfo) - seen).total_seconds()
    online = age < RUNNER_STALE_SECONDS
    return {
        "online": online,
        "host": row["host"],
        "last_seen": row["last_seen"],
        "seconds_since": int(age),
        "message": None if online else
                   "Runneren svarer ikke. Job lægges i kø og køres, når du starter: python runner.py",
    }


@app.get("/admin/pipelines/runner")
def admin_pipeline_runner(request: Request):
    """Er runneren i live? Uden den bliver et klik liggende i koeen."""
    _require_admin(request)
    return _runner_health()


@app.get("/admin/pipelines/races")
def admin_pipeline_races(request: Request, window_days: int = 120):
    """Loeb der er relevante at arbejde med lige nu: i gang, lige afsluttet
    eller paa vej. Fuldstaendigheden beregnes IKKE her — den kraever et snes
    forespoergsler pr. loeb og hentes derfor pr. loeb, naar du klikker ind."""
    _require_admin(request)
    today = today_dk()
    frm = (today - timedelta(days=window_days)).isoformat()
    til = (today + timedelta(days=window_days)).isoformat()

    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?select=name,slug,start_date,end_date,category"
        f"&end_date=gte.{frm}&start_date=lte.{til}&order=start_date.asc",
        headers=get_headers(),
    )
    races = res.json() if res.ok and isinstance(res.json(), list) else []

    runs = _runs_for(None, limit=500)
    by_race: dict = {}
    for run in runs:
        by_race.setdefault(run.get("race_slug"), []).append(run)

    today_iso = today.isoformat()
    out = []
    for race in races:
        race_runs = by_race.get(race["slug"], [])
        failed = [r for r in race_runs if r["status"] == "failed"]
        active = [r for r in race_runs if r["status"] in ("queued", "running")]
        end_date = race.get("end_date") or race["start_date"]
        if race["start_date"] <= today_iso <= end_date:
            phase = "i_gang"
        elif race["start_date"] > today_iso:
            phase = "kommende"
        else:
            phase = "afsluttet"
        out.append({
            **race,
            "phase": phase,
            "last_run": race_runs[0] if race_runs else None,
            "run_count": len(race_runs),
            "failed_count": len(failed),
            "active_count": len(active),
        })
    return {"races": out, "today": today_iso}


@app.get("/admin/pipelines/races/{race_slug}")
def admin_pipeline_race_detail(request: Request, race_slug: str):
    """Alt om eet loeb: hvor fuldstaendigt data er, og hvornaar hvert job sidst koerte."""
    _require_admin(request)
    data = race_completeness(race_slug)
    if not data:
        raise HTTPException(status_code=404, detail="Løb ikke fundet")

    runs = _runs_for(race_slug)
    latest = _last_run_by_job(runs)

    # Hvert tjek peger paa de job, der kan udbedre det (check["fixed_by"]).
    # Her vender vi det om, saa hvert job ved, hvilke mangler det ville lukke —
    # det er dét, der goer en knap forstaaelig frem for bare en etiket.
    missing_by_job: dict = {}
    for check in data["checks"]:
        if check["status"] != "mangler":
            continue
        for job_key in check["fixed_by"]:
            missing_by_job.setdefault(job_key, []).append(check["label"])

    jobs = []
    for job in agent_catalog.list_jobs():
        if not job["needs_race"]:
            continue
        jobs.append({
            **job,
            "last_run": latest.get(job["key"]),
            "would_fix": missing_by_job.get(job["key"], []),
        })

    return {
        **data,
        "jobs": jobs,
        "stages": _stages_for_picker(race_slug),
        "recent_runs": runs[:20],
        "phase_labels": agent_catalog.PHASE_LABELS,
        "cancel_window_seconds": CANCEL_WINDOW_SECONDS,
    }


def _stages_for_picker(race_slug: str) -> list[dict]:
    """Etaperne som dropdownen "hele loebet / etape N" skal vise.

    Navnet hentes fra databasen og ikke fra et taelleloeb, saa listen altid
    passer til det, der faktisk ligger der — et loeb med 21 etaper, hvor E3 er
    aflyst, skal stadig kunne vaelges paa E3, fordi man kan have brug for at
    genkoere netop den.
    """
    race = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?slug=eq.{race_slug}&select=id&limit=1",
        headers=get_headers(),
    )
    rows = race.json() if race.ok and isinstance(race.json(), list) else []
    if not rows:
        return []
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages?race_id=eq.{rows[0]['id']}"
        f"&select=stage_number,start_location,finish_location,date,data_status"
        f"&order=stage_number.asc",
        headers=get_headers(),
    )
    stages = res.json() if res.ok and isinstance(res.json(), list) else []
    out = []
    for st in stages:
        if st.get("stage_number") is None:
            continue
        rute = " - ".join(x for x in (st.get("start_location"), st.get("finish_location")) if x)
        out.append({
            "stage_number": st["stage_number"],
            "label": f"Etape {st['stage_number']}" + (f": {rute}" if rute else ""),
            "date": st.get("date"),
            "cancelled": bool(st.get("data_status")),
        })
    return out


class PipelineRunRequest(BaseModel):
    job_key: str
    race_slug: str | None = None
    # None = hele løbet. Et tal = netop den etape. Kataloget afviser selv et
    # nummer uden for området og et job, der ikke kan afgrænses til én etape.
    stage_number: int | None = None


@app.post("/admin/pipelines/run")
def admin_pipeline_run(request: Request, body: PipelineRunRequest):
    """Laegger et job i koe. Koerer ikke noget her — det goer runner.py.

    Kun job_key, loeb og etape kommer udefra; kommandoerne bygges af
    agent_catalog paa ejerens maskine. build_commands() kaldes allerede her for
    at afvise et ugyldigt job, slug eller etapenummer med det samme i stedet
    for at lade en doed raekke ligge i koeen.

    Raekken faar `not_before` sat CANCEL_WINDOW_SECONDS ude i fremtiden. Det er
    fortryd-vinduet: runneren roerer den ikke foer da, saa Afbryd naar altid at
    virke, uanset hvornaar runneren sidst pollede.
    """
    _require_admin(request)
    try:
        agent_catalog.build_commands(body.job_key, body.race_slug, body.stage_number)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Samme job for samme loeb OG samme omfang maa ikke staa i koe to gange —
    # et dobbeltklik ville ellers sende to tunge Playwright-koersler mod PCS
    # samtidig. To FORSKELLIGE etaper af samme job er derimod i orden.
    race_filter  = f"&race_slug=eq.{body.race_slug}" if body.race_slug else "&race_slug=is.null"
    stage_filter = (f"&stage_number=eq.{body.stage_number}"
                    if body.stage_number is not None else "&stage_number=is.null")
    dupes = requests.get(
        f"{RUNS_TABLE}?select=id,status&job_key=eq.{body.job_key}{race_filter}{stage_filter}"
        f"&status=in.(queued,running)&limit=1",
        headers=get_headers(),
    )
    if dupes.ok and dupes.json():
        existing = dupes.json()[0]
        return {"queued": False, "run_id": existing["id"], "status": existing["status"],
                "cancel_window_seconds": CANCEL_WINDOW_SECONDS,
                "message": "Jobbet ligger allerede i køen"}

    not_before = (datetime.now(timezone.utc)
                  + timedelta(seconds=CANCEL_WINDOW_SECONDS)).isoformat()
    res = requests.post(
        RUNS_TABLE,
        json={"job_key": body.job_key, "race_slug": body.race_slug,
              "stage_number": body.stage_number, "not_before": not_before,
              "trigger": "button"},
        headers={**get_headers(), "Content-Type": "application/json",
                 "Prefer": "return=representation"},
    )
    if not res.ok:
        raise HTTPException(status_code=500, detail=f"Kunne ikke lægge i kø: {res.text[:200]}")
    return {"queued": True, "run_id": res.json()[0]["id"], "status": "queued",
            "not_before": not_before,
            "cancel_window_seconds": CANCEL_WINDOW_SECONDS,
            "message": None}


# En koersel kan ikke vare laengere end runnerens egen timeout (JOB_TIMEOUT_S
# i runner.py). Staar den stadig som 'running' bagefter, er processen vaek.
MAX_RUN_HOURS = 3


def _forced_cancel_reason(run: dict) -> dict | None:
    """Tor vi markere en 'running'-koersel som afbrudt uden at have hoert fra
    runneren? Kun naar der beviseligt ikke er nogen til at goere det:

      * runneren har ikke sendt hjerteslag i RUNNER_STALE_SECONDS, eller
      * koerslen har staaet som 'running' laengere end runnerens egen timeout.

    Ellers svarer vi None: en travl runner er i gang med at draebe processen og
    melder tilbage inden for faa sekunder, og en raekke, vi lukkede for tidligt,
    ville paastaa at noget var stoppet, mens det stadig skrev i databasen.
    """
    health = _runner_health()
    if not health["online"]:
        siden = health.get("seconds_since")
        hvor_laenge = f" (sidste livstegn for {siden // 60} min siden)" if siden else ""
        return {
            "besked": f"Runneren svarer ikke{hvor_laenge} — kørslen er frigivet og "
                      "markeret som afbrudt. Tjek at processen faktisk er stoppet på PC'en.",
            "log": "Afbrudt fra dashboardet. Runneren svarede ikke, så kørslen blev "
                   "frigivet uden bekræftelse på, at processen nåede at stoppe.",
        }

    started = run.get("started_at")
    if started:
        alder = (datetime.now(timezone.utc)
                 - datetime.fromisoformat(started.replace("Z", "+00:00"))).total_seconds()
        if alder > MAX_RUN_HOURS * 3600:
            return {
                "besked": f"Kørslen har stået som i gang i over {MAX_RUN_HOURS} timer — "
                          "længere end runneren selv tillader. Den er frigivet.",
                "log": f"Afbrudt fra dashboardet efter mere end {MAX_RUN_HOURS} timer "
                       "som 'running'. Runnerens egen timeout burde have lukket den.",
            }
    return None


@app.post("/admin/pipelines/runs/{run_id}/cancel")
def admin_pipeline_cancel(request: Request, run_id: str):
    """Afbryder en koersel.

    To tilfaelde, og forskellen er vaesentlig:
      i koe    — jobbet er aldrig startet, saa intet er aendret. Vi saetter
                 status='cancelled' med det samme, og runneren ser den aldrig.
      koerer   — processen er i gang. Vi kan ikke fortryde det, den allerede
                 har skrevet, saa vi saetter kun cancel_requested. Runneren
                 laeser flaget hvert femte sekund og draeber processen med hele
                 dens traeaf barneprocesser.

    Statusskiftet i koe-tilfaeldet filtreres paa `status=eq.queued`, saa vi ikke
    kan komme til at overskrive en raekke, runneren tog i samme sekund — rammer
    PATCH'en nul raekker, faldt vi igennem til koerer-tilfaeldet nedenfor.
    """
    _require_admin(request)
    res = requests.get(
        f"{RUNS_TABLE}?id=eq.{run_id}&select=id,job_key,status,started_at,"
        f"cancel_requested&limit=1",
        headers=get_headers(),
    )
    rows = res.json() if res.ok and isinstance(res.json(), list) else []
    if not rows:
        raise HTTPException(status_code=404, detail="Kørsel ikke fundet")
    run = rows[0]

    if run["status"] == "queued":
        patched = requests.patch(
            f"{RUNS_TABLE}?id=eq.{run_id}&status=eq.queued",
            json={
                "status": "cancelled",
                "cancel_requested": True,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "log_tail": "Afbrudt fra dashboardet, før kørslen gik i gang. "
                            "Intet blev ændret.",
                "validation_verdict": "skipped",
                "validation_note": "Afbrudt før start — ingen data blev rørt.",
            },
            headers={**get_headers(), "Content-Type": "application/json",
                     "Prefer": "return=representation"},
        )
        if patched.ok and patched.json():
            return {"cancelled": True, "status": "cancelled",
                    "message": "Afbrudt — intet blev ændret"}
        # Nul raekker: runneren naaede at tage jobbet imellem laesningen og
        # PATCH'en. Behandl det som en igangvaerende koersel.
        run["status"] = "running"

    if run["status"] == "running":
        requests.patch(
            f"{RUNS_TABLE}?id=eq.{run_id}",
            json={"cancel_requested": True},
            headers={**get_headers(), "Content-Type": "application/json",
                     "Prefer": "return=minimal"},
        )

        # Flaget alene er nok, saa laenge der ER en runner til at laese det. Er
        # der ikke, ville raekken staa som "Stopper ..." for evigt — det skete
        # 2026-09-09, da runneren blev lukket midt i en koersel. Derfor:
        # svarer runneren ikke, frigiver vi raekken her i stedet.
        grund = _forced_cancel_reason(run)
        if grund:
            requests.patch(
                f"{RUNS_TABLE}?id=eq.{run_id}&status=eq.running",
                json={
                    "status": "cancelled",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "log_tail": grund["log"],
                    "validation_verdict": "skipped",
                    "validation_note": "Afbrudt — kørslen kunne ikke bekræftes stoppet.",
                },
                headers={**get_headers(), "Content-Type": "application/json",
                         "Prefer": "return=minimal"},
            )
            return {"cancelled": True, "status": "cancelled", "message": grund["besked"]}

        return {"cancelled": False, "status": "running",
                "message": "Kørslen er i gang — stopper den nu. "
                           "Det, den allerede har nået at gemme, bliver stående."}

    return {"cancelled": False, "status": run["status"],
            "message": f"Kørslen er allerede afsluttet ({run['status']}) og kan ikke afbrydes"}


@app.get("/admin/pipelines/runs")
def admin_pipeline_runs(request: Request, race: str | None = None, limit: int = 50):
    _require_admin(request)
    return {"runs": _runs_for(race, limit=limit)}


@app.get("/admin/pipelines/runs/{run_id}")
def admin_pipeline_run_detail(request: Request, run_id: str):
    """Een koersel med hele den gemte log — det er her, du laeser fejlen."""
    _require_admin(request)
    res = requests.get(f"{RUNS_TABLE}?id=eq.{run_id}&select=*&limit=1", headers=get_headers())
    rows = res.json() if res.ok and isinstance(res.json(), list) else []
    if not rows:
        raise HTTPException(status_code=404, detail="Kørsel ikke fundet")
    run = rows[0]
    # label_for() kender ogsaa de job, der er taget ud af kataloget siden — uden
    # det ville historikken vise et raat job_key uden forklaring.
    run["job_label"] = agent_catalog.label_for(run["job_key"])
    run["scope_label"] = agent_catalog.scope_label(run.get("stage_number"))
    return run
