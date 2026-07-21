"""
aso_roadbook_agent.py
Henter officielle roadbook-FAKTA (stigningskategorier + mellemsprints) fra
ASO's loebssider (letour.fr / lavuelta.es — samme platform) og skriver dem til
Supabase, saa stage_profile_generator.py kan tegne kategori-badges og
sprint-markoerer paa hel-etape-hoejdeprofilerne.

Vi henter KUN fakta (navne, km, laengder, gradienter, kategorier) — aldrig
billeder (jf. LEG-001 / CLAUDE.md §7).

Pr. etape:
  - "Mountain passes & hill"-fanen  -> kategoriserede stigninger:
      navn, top-km, laengde, gns. gradient, kategori (HC/1/2/3/4)
  - "Time schedule"-fanen           -> mellemsprint(s): navn + km fra start
      (raekker markeret med sprint-ikon i vejskema-tabellen)

Matchning mod stage_climbs (accent-/case-normaliseret + fuzzy):
  - match           -> saet category; ret km/laengde/gradient hvis afvigelsen
                       er > 1,5 km (unik-constraint-kollision => kun category)
  - intet DB-match  -> indsaet ny raekke (source='roadbook'), saa badge kan
                       tegnes; frontenden viser den kun som fane hvis den
                       senere faar en visuel profil (hasVisualProfile-gate)

Sikkerhed: dry-run er default — intet skrives uden --write.

Koer:
    python agents/aso_roadbook_agent.py --race tour-de-france-2026 --stages 1-21
    python agents/aso_roadbook_agent.py --race tour-de-france-2026 --stages 20 --probe
    python agents/aso_roadbook_agent.py --race la-vuelta-ciclista-a-espana-2026 --stages 1-21 --write
"""

import io
import os
import re
import sys
import time
import argparse
import unicodedata
from difflib import SequenceMatcher

import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SB_AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
SB_HEADERS = {**SB_AUTH, "Content-Type": "application/json", "Prefer": "return=minimal"}

# race_slug (vores DB) -> officiel ASO-side
ASO_SITES = {
    "tour-de-france-2026": "https://www.letour.fr",
    "la-vuelta-ciclista-a-espana-2026": "https://www.lavuelta.es",
}

KM_CORRECTION_THRESHOLD = 1.5  # km — over dette rettes DB'ens km/laengde/gradient


# ── Parsning af ASO-siden ────────────────────────────────────────────────────

def _clean_climb_name(raw: str) -> str:
    """'Col de Sarenne (1 999 m) Souvenir Henri Desgrange' -> 'Col de Sarenne'."""
    name = re.sub(r"\s*\([^)]*\)\s*", " ", raw)
    name = re.sub(r"\s*Souvenir .*$", "", name, flags=re.I)
    return re.sub(r"\s+", " ", name).strip()


def parse_mountain_passes(html: str) -> list[dict]:
    """Finder klatre-kortene i 'Mountain passes & hill'-fanen (dedupe: karrusellen
    gentager samme kort flere gange)."""
    soup = BeautifulSoup(html, "html.parser")
    climbs, seen = [], set()
    for h3 in soup.find_all("h3"):
        title = h3.get_text(" ", strip=True)
        if not re.search(r"\(\s*[\d\s .,]+\s*m\s*\)", title):
            continue
        block = h3.parent.get_text(" | ", strip=True) if h3.parent else title
        m_km = re.search(r"Km\s*([\d.,]+)\s*-\s*(\d+)\s*m", block)
        m_len = re.search(r"([\d.,]+)\s*kilometre-long climb at\s*([\d.,]+)\s*%", block)
        m_cat = re.search(r"Category\s*(HC|\d)", block)
        if not (m_km and m_len and m_cat):
            continue
        name = _clean_climb_name(title)
        key = (name.lower(), m_km.group(1))
        if key in seen:
            continue
        seen.add(key)
        climbs.append({
            "name": name,
            "summit_km": float(m_km.group(1).replace(",", ".")),
            "summit_alt_m": int(m_km.group(2)),
            "length_km": float(m_len.group(1).replace(",", ".")),
            "avg_gradient": float(m_len.group(2).replace(",", ".")),
            "category": m_cat.group(1),
        })
    climbs.sort(key=lambda c: c["summit_km"])
    return climbs


def parse_sprints(html: str) -> list[dict]:
    """Finder mellemsprint-raekker i 'Time schedule'-vejskemaet. ASO markerer
    dem med raekke-klassen 'itinerary__checkpoint--n' (bjergpassager har '--h');
    samme picto-klasser gaar igen i pointtabellen, som filtreres fra via
    km-kolonnen (den indeholder 'pts', ikke et tal)."""
    soup = BeautifulSoup(html, "html.parser")
    sprints, seen = [], set()
    for tr in soup.select("tr.itinerary__checkpoint--n"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        name = tds[1].get_text(" ", strip=True)
        # kolonne 2 = km til maal, kolonne 3 = km fra start
        m = re.fullmatch(r"[\d.,]+", tds[3].get_text(strip=True) or "")
        if not name or not m:
            continue
        km = float(tds[3].get_text(strip=True).replace(",", "."))
        # Vejnavne-praefiks som "D1006 ...", "C-245 ..." eller "VC ..." -> fjern.
        name = re.sub(r"^(?:[A-Z]{1,3}-?\d+\S*|VC|RD|RN)\s+", "", name)
        key = (name.lower(), round(km, 1))
        if key in seen:
            continue
        seen.add(key)
        sprints.append({"name": name.title() if name.isupper() else name, "km": km})
    return sprints


def fetch_stage(base_url: str, stage_number: int, probe: bool = False) -> tuple[list[dict], list[dict]]:
    """Aabner ASO-etapesiden, klikker fanerne og returnerer (climbs, sprints)."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(f"{base_url}/en/stage-{stage_number}", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2500)
            # Cookiebanner (OneTrust m.fl.) — luk hvis den findes, ellers videre
            for sel in ("#onetrust-accept-btn-handler", "button:has-text('Accept')"):
                try:
                    page.locator(sel).first.click(timeout=2000)
                    break
                except Exception:
                    pass

            climbs, sprints = [], []
            try:
                page.get_by_role("button", name=re.compile("Mountain passes", re.I)).first.click(timeout=8000)
                page.wait_for_timeout(1200)
                climbs = parse_mountain_passes(page.content())
            except Exception as e:
                print(f"    [ingen 'Mountain passes'-fane: {type(e).__name__}]")

            try:
                page.get_by_role("button", name=re.compile("Time schedule", re.I)).first.click(timeout=8000)
                page.wait_for_timeout(1200)
                html = page.content()
                if probe:
                    soup = BeautifulSoup(html, "html.parser")
                    for tr in soup.find_all("tr"):
                        if "sprint" in str(tr).lower():
                            print("    PROBE sprint-raekke:", str(tr)[:600])
                sprints = parse_sprints(html)
            except Exception as e:
                print(f"    [ingen 'Time schedule'-fane: {type(e).__name__}]")

            return climbs, sprints
        finally:
            browser.close()


# ── DB-matchning ─────────────────────────────────────────────────────────────

def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def names_match(a: str, b: str) -> bool:
    na, nb = norm_name(a), norm_name(b)
    if na == nb or na in nb or nb in na:
        return True
    # Hoej taerskel: 0.78 lod "Col du Haag" matche "Col du Page" (0.82) pga.
    # det faelles "Col du "-praefiks — 0.85 kraever reel navnelighed.
    return SequenceMatcher(None, na, nb).ratio() >= 0.85


def get_race_id(race_slug: str) -> str | None:
    res = requests.get(f"{SUPABASE_URL}/rest/v1/races?slug=eq.{race_slug}&select=id&limit=1", headers=SB_AUTH)
    data = res.json()
    return data[0]["id"] if res.ok and data else None


def get_stage(race_id: str, n: int) -> dict | None:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages?race_id=eq.{race_id}&stage_number=eq.{n}"
        f"&select=id,stage_number,distance_km,sprints&limit=1", headers=SB_AUTH)
    data = res.json()
    return data[0] if res.ok and data else None


def get_climbs(stage_id: str) -> list[dict]:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stage_climbs?stage_id=eq.{stage_id}"
        f"&select=id,name,km_from_start,length_km,avg_gradient,category&order=km_from_start.asc",
        headers=SB_AUTH)
    return res.json() if res.ok else []


def patch_climb(climb_id: str, payload: dict) -> bool:
    res = requests.patch(f"{SUPABASE_URL}/rest/v1/stage_climbs?id=eq.{climb_id}",
                         json=payload, headers=SB_HEADERS)
    return res.ok


def insert_climb(payload: dict) -> bool:
    res = requests.post(f"{SUPABASE_URL}/rest/v1/stage_climbs", json=payload, headers=SB_HEADERS)
    return res.ok


def patch_stage_sprints(stage_id: str, sprints: list[dict]) -> bool:
    res = requests.patch(f"{SUPABASE_URL}/rest/v1/stages?id=eq.{stage_id}",
                         json={"sprints": sprints}, headers=SB_HEADERS)
    return res.ok


# ── Pipeline pr. etape ───────────────────────────────────────────────────────

def process_stage(race_slug: str, race_id: str, base_url: str, n: int,
                  write: bool, probe: bool) -> None:
    stage = get_stage(race_id, n)
    if not stage:
        print(f"  Etape {n}: ikke i DB — springer over")
        return

    climbs_aso, sprints = fetch_stage(base_url, n, probe=probe)
    print(f"  Etape {n}: roadbook har {len(climbs_aso)} kategoriserede stigninger, {len(sprints)} sprint")

    db_climbs = get_climbs(stage["id"])
    distance = float(stage.get("distance_km") or 0)
    used_db_ids: set = set()  # samme DB-raekke maa aldrig matches to gange

    for ac in climbs_aso:
        if distance and ac["summit_km"] > distance + 1:
            print(f"    ! {ac['name']}: top-km {ac['summit_km']} > etapelaengde {distance} — springer over")
            continue
        match = next((dc for dc in db_climbs
                      if dc["id"] not in used_db_ids and names_match(ac["name"], dc["name"])), None)
        if match:
            used_db_ids.add(match["id"])
        new_km_from_start = round(ac["summit_km"] - ac["length_km"], 1)
        if match:
            db_summit = float(match["km_from_start"] or 0) + float(match["length_km"] or 0)
            payload = {"category": ac["category"]}
            if abs(db_summit - ac["summit_km"]) > KM_CORRECTION_THRESHOLD and new_km_from_start >= 0:
                payload.update({
                    "km_from_start": new_km_from_start,
                    "length_km": ac["length_km"],
                    "avg_gradient": ac["avg_gradient"],
                })
            action = "kategori" + ("+km-korrektion" if len(payload) > 1 else "")
            print(f"    = {ac['name']} -> {match['name']}: {action} ({ac['category']})")
            if write:
                ok = patch_climb(match["id"], payload)
                if not ok and len(payload) > 1:
                    # unik-constraint (stage_id, km_from_start) — fald tilbage til kun kategori
                    ok = patch_climb(match["id"], {"category": ac["category"]})
                    print("      (km-korrektion kollision — kun kategori sat)")
                if not ok:
                    print("      ✗ PATCH fejlede")
        else:
            print(f"    + {ac['name']}: NY raekke ({ac['category']}, top km {ac['summit_km']}, "
                  f"{ac['length_km']} km @ {ac['avg_gradient']}%)")
            if write and new_km_from_start >= 0:
                ok = insert_climb({
                    "stage_id": stage["id"],
                    "name": ac["name"],
                    "km_from_start": new_km_from_start,
                    "length_km": ac["length_km"],
                    "avg_gradient": ac["avg_gradient"],
                    "category": ac["category"],
                    "source": "roadbook",
                })
                if not ok:
                    print("      ✗ INSERT fejlede (evt. km-kollision) — sprunget over")

    if sprints:
        for s in sprints:
            print(f"    S {s['name']} @ km {s['km']}")
        if write:
            if not patch_stage_sprints(stage["id"], sprints):
                print("      ✗ sprints-PATCH fejlede")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--race", required=True, help="DB race-slug, fx tour-de-france-2026")
    parser.add_argument("--stages", default="1-21", help="Etaper, fx '5' eller '1-21'")
    parser.add_argument("--write", action="store_true", help="Skriv til DB (default: dry-run)")
    parser.add_argument("--probe", action="store_true", help="Dump sprint-raekkers HTML til inspektion")
    args = parser.parse_args()

    base_url = ASO_SITES.get(args.race)
    if not base_url:
        print(f"Intet ASO-site konfigureret for '{args.race}' (se ASO_SITES)")
        return
    race_id = get_race_id(args.race)
    if not race_id:
        print(f"Loeb ikke fundet i DB: {args.race}")
        return

    if "-" in args.stages:
        lo, hi = args.stages.split("-")
        stage_numbers = range(int(lo), int(hi) + 1)
    else:
        stage_numbers = [int(args.stages)]

    mode = "WRITE" if args.write else "DRY-RUN"
    print(f"aso_roadbook_agent.py — {args.race} ({base_url}), etaper {args.stages} [{mode}]")
    for n in stage_numbers:
        try:
            process_stage(args.race, race_id, base_url, n, args.write, args.probe)
        except Exception as e:
            print(f"  Etape {n}: FEJL {type(e).__name__}: {e}")
        time.sleep(1.0)


if __name__ == "__main__":
    main()
