"""
results_agent.py
Scraper etaperesultater og GC-klassement fra PCS for igangvaerende loeb.
Gemmer i startlists-tabellen (status, dnf_stage_number) og opdaterer
gc_position / gc_time_gap i en separat klassementer-tabel hvis den eksisterer.

Korer: python results_agent.py
       python results_agent.py --race giro-d-italia-2026
       python results_agent.py --race giro-d-italia-2026 --stage 15
"""

import os
import re
import sys
import io
import time
import argparse
import requests
from datetime import date
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
DB   = {**AUTH, "Content-Type": "application/json", "Prefer": "return=minimal"}

DELAY = 1.5


# ── Supabase helpers ──────────────────────────────────────────────────────────

def get_ongoing_races() -> list[dict]:
    today = date.today().isoformat()
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races"
        f"?start_date=lte.{today}&end_date=gte.{today}"
        f"&select=id,name,slug,pcs_url"
        f"&order=start_date.desc&limit=5",
        headers=AUTH,
    )
    return res.json() if res.ok else []


def get_race(slug: str) -> dict | None:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?slug=eq.{slug}&select=id,name,slug,pcs_url&limit=1",
        headers=AUTH,
    )
    data = res.json()
    return data[0] if res.ok and data else None


def get_latest_finished_stage(race_id: str) -> dict | None:
    today = date.today().isoformat()
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages"
        f"?race_id=eq.{race_id}&date=lte.{today}"
        f"&select=id,stage_number,pcs_stage_url,date"
        f"&order=stage_number.desc&limit=1",
        headers=AUTH,
    )
    data = res.json()
    return data[0] if res.ok and data else None


def get_rider_id_by_name(name: str) -> str | None:
    # Søg via startlists-navn — normalisér store bogstaver
    clean = name.strip().upper()
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/riders?name=ilike.{requests.utils.quote(clean)}&select=id&limit=1",
        headers=AUTH,
    )
    data = res.json()
    return data[0]["id"] if res.ok and data else None


def mark_dnf(race_id: str, rider_name: str, stage_number: int) -> None:
    rid = get_rider_id_by_name(rider_name)
    if not rid:
        return
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/startlists?race_id=eq.{race_id}&rider_id=eq.{rid}",
        json={"status": "DNF", "dnf_stage_number": stage_number},
        headers=DB,
    )


def upsert_gc(race_id: str, standings: list[dict]) -> None:
    """Gemmer GC-klassement i startlists (gc_position, gc_time_gap_seconds)."""
    for entry in standings:
        rid = get_rider_id_by_name(entry["name"])
        if not rid:
            continue
        requests.patch(
            f"{SUPABASE_URL}/rest/v1/startlists?race_id=eq.{race_id}&rider_id=eq.{rid}",
            json={
                "gc_position":          entry.get("position"),
                "gc_time_gap_seconds":  entry.get("time_gap_seconds"),
            },
            headers=DB,
        )


# ── PCS scraping ──────────────────────────────────────────────────────────────

def parse_time_to_seconds(s: str) -> int | None:
    """'1:23:45' eller '+0:45' → sekunder."""
    s = s.strip().lstrip("+")
    parts = s.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        pass
    return None


def scrape_stage_result(pcs_stage_url: str) -> dict:
    """
    Scraper etaperesultat fra PCS.
    Returnerer: {top10: [{pos, name, time}], dnf: [name, ...], gc: [{pos, name, gap}]}
    """
    result = {"top10": [], "dnf": [], "gc": []}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            page.goto(pcs_stage_url, wait_until="networkidle", timeout=25_000)
            time.sleep(2)
            html = page.content()
            browser.close()

        # Etaperesultat-tabel — PCS viser "Result" tabel oevet
        # Rækker: position | rytternavn | hold | tid
        result_rows = re.findall(
            r'<tr[^>]*>.*?<td[^>]*>(\d+)</td>'          # position
            r'.*?rider/([a-z0-9\-]+)"[^>]*>([^<]+)</a>'  # slug + navn
            r'.*?<td[^>]*>([\d:+]+)</td>',               # tid
            html, re.DOTALL
        )

        for pos_str, slug, name, time_str in result_rows[:10]:
            result["top10"].append({
                "position": int(pos_str),
                "name":     name.strip().upper(),
                "time":     time_str.strip(),
            })

        # DNF-liste
        dnf_section = re.search(r'DNF.*?</table>', html, re.DOTALL | re.IGNORECASE)
        if dnf_section:
            dnf_names = re.findall(r'rider/[a-z0-9\-]+"[^>]*>([^<]+)</a>', dnf_section.group(0))
            result["dnf"] = [n.strip().upper() for n in dnf_names]

        # GC-klassement
        gc_rows = re.findall(
            r'<tr[^>]*>.*?<td[^>]*>(\d+)</td>'
            r'.*?rider/([a-z0-9\-]+)"[^>]*>([^<]+)</a>'
            r'.*?<td[^>]*>([\d:+]+)</td>',
            html, re.DOTALL
        )
        # GC er typisk den anden tabel — hent kun hvis vi allerede har etaperesultat
        if result["top10"] and gc_rows:
            for pos_str, slug, name, gap_str in gc_rows[:20]:
                result["gc"].append({
                    "position":         int(pos_str),
                    "name":             name.strip().upper(),
                    "time_gap_seconds": parse_time_to_seconds(gap_str) if gap_str != "0:00:00" else 0,
                })

    except Exception as e:
        print(f"  [Scrape fejl: {e}]")

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def process(race_slug: str | None, stage_number: int | None) -> None:
    if race_slug:
        races = [get_race(race_slug)]
        races = [r for r in races if r]
    else:
        races = get_ongoing_races()

    print(f"results_agent.py — {date.today().isoformat()}")
    print(f"Behandler {len(races)} loeb\n")

    for race in races:
        print(f"[{race['name']}]")
        race_id  = race["id"]
        pcs_base = race.get("pcs_url", "")

        if stage_number:
            # Hent specifik etapes URL fra DB
            res = requests.get(
                f"{SUPABASE_URL}/rest/v1/stages"
                f"?race_id=eq.{race_id}&stage_number=eq.{stage_number}"
                f"&select=id,stage_number,pcs_stage_url,date&limit=1",
                headers=AUTH,
            )
            stages = res.json() if res.ok else []
        else:
            stage = get_latest_finished_stage(race_id)
            stages = [stage] if stage else []

        if not stages:
            print("  Ingen etaper at opdatere")
            continue

        for stage in stages:
            sn       = stage["stage_number"]
            pcs_url  = stage.get("pcs_stage_url")

            if not pcs_url:
                # Byg URL fra race-URL
                if pcs_base:
                    pcs_url = f"{pcs_base.rstrip('/')}/stage-{sn}/result"
                else:
                    print(f"  E{sn}: Ingen PCS-URL")
                    continue

            # Tilfoej /result hvis ikke allerede der
            if not pcs_url.endswith("/result"):
                pcs_url = pcs_url.rstrip("/") + "/result"

            print(f"  E{sn}: Scraper {pcs_url}")
            data = scrape_stage_result(pcs_url)

            if data["top10"]:
                print(f"  -> Top 3: " + " | ".join(
                    f"{r['position']}. {r['name'].split()[-1]}" for r in data["top10"][:3]
                ))
            else:
                print("  -> Ingen etaperesultat fundet (muligvis ikke koert endnu)")

            if data["dnf"]:
                print(f"  -> DNF: {', '.join(data['dnf'][:5])}")
                for name in data["dnf"]:
                    mark_dnf(race_id, name, sn)

            if data["gc"]:
                print(f"  -> GC top3: " + " | ".join(
                    f"{r['position']}. {r['name'].split()[-1]}" for r in data["gc"][:3]
                ))
                upsert_gc(race_id, data["gc"])

            time.sleep(DELAY)

    print("\nFaerdig.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--race",  help="Loeb-slug (default: alle igangvaerende)", default=None)
    parser.add_argument("--stage", type=int, help="Specifik etape (default: seneste afsluttede)", default=None)
    args = parser.parse_args()
    process(args.race, args.stage)
