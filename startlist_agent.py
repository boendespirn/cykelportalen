"""
startlist_agent.py
Scraper startlister fra ProCyclingStats for UCI WorldTour-løb.
Bruger Playwright fordi PCS har Cloudflare-beskyttelse.

Krav: pip install playwright && playwright install chromium

Kør: python startlist_agent.py
Eller for ét løb: python startlist_agent.py tour-de-france-2026
"""

import os
import re
import sys
import asyncio
import requests
from slugify import slugify
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
BASE_URL = "https://www.procyclingstats.com"
YEAR = 2026

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}

# PCS race-slug → vores DB-slug mapping
# PCS bruger fx "tour-de-france" → vi bruger "tour-de-france-2026"
PCS_RACE_SLUGS = [
    "tour-de-france",
    "giro-d-italia",
    "vuelta-a-espana",
    "paris-roubaix",
    "liege-bastogne-liege",
    "il-lombardia",
    "milan-san-remo",
    "tour-of-flanders",
    "strade-bianche",
    "tirreno-adriatico",
    "paris-nice",
    "volta-a-catalunya",
    "tour-de-romandie",
    "criterium-du-dauphine",
    "tour-de-suisse",
    "la-fleche-wallonne",
    "amstel-gold-race",
    "e3-saxo-bank-classic",
    "gent-wevelgem",
    "dwars-door-vlaanderen",
    "tour-de-france-femmes",
    "eschborn-frankfurt",
    "tour-de-hongrie",
    "tour-de-pologne",
    "bretagne-classic",
    "grand-prix-de-quebec",
    "grand-prix-de-montreal",
]


# ── Supabase helpers ─────────────────────────────────────────────────────────

def sb_get(table: str, params: str) -> list:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}?{params}",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
    )
    return res.json() if res.ok else []


def sb_upsert(table: str, records: list, conflict: str = "id") -> bool:
    if not records:
        return True
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={conflict}",
        json=records,
        headers=SUPABASE_HEADERS,
    )
    if not res.ok:
        print(f"  [DB FEJL] {table}: {res.status_code} — {res.text[:300]}")
    return res.ok


def sb_patch(table: str, record_id: str, data: dict) -> bool:
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/{table}?id=eq.{record_id}",
        json=data,
        headers=SUPABASE_HEADERS,
    )
    return res.ok


def get_race(our_slug: str) -> dict | None:
    rows = sb_get("races", f"slug=eq.{our_slug}&select=id,slug,pcs_url&limit=1")
    return rows[0] if rows else None


# PCS-slug → vores DB-slug (når de afviger fra hinanden)
PCS_TO_DB_SLUG: dict[str, str] = {
    "vuelta-a-espana":      "la-vuelta-ciclista-a-espana",
    "paris-roubaix":        "paris-roubaix-hauts-de-france",
    "gent-wevelgem":        "in-flanders-fields-from-middelkerke-to-wevelgem",
}


def get_or_create_race(pcs_slug: str) -> dict | None:
    """Finder løbet i DB ud fra PCS-slug. Opretter det hvis det ikke findes."""
    db_base = PCS_TO_DB_SLUG.get(pcs_slug, pcs_slug)
    our_slug = f"{db_base}-{YEAR}"
    race = get_race(our_slug)
    if race:
        return race

    # Opret løbet med minimal data — startlist_agent fylder resten
    record = {
        "name": pcs_slug.replace("-", " ").title(),
        "slug": our_slug,
        "category": "UCI WorldTour",
        "start_date": f"{YEAR}-01-01",  # Opdateres af race_agent
        "pcs_url": f"{BASE_URL}/race/{pcs_slug}/{YEAR}",
        "source": "pcs",
    }
    sb_upsert("races", [record], conflict="slug")
    return get_race(our_slug)


def lookup_team(name: str) -> str | None:
    slug = slugify(name)
    rows = sb_get("teams", f"slug=eq.{slug}&select=id&limit=1")
    if rows:
        return rows[0]["id"]
    # Prøv med delvis match
    rows = sb_get("teams", f"name=ilike.*{name[:15]}*&select=id&limit=1")
    return rows[0]["id"] if rows else None


def lookup_rider(name: str, pcs_rider_slug: str = "") -> str | None:
    # 1. Match på PCS-slug direkte mod source_url
    if pcs_rider_slug:
        rows = sb_get("riders", f"source_url=ilike.*{pcs_rider_slug}*&select=id&limit=1")
        if rows:
            return rows[0]["id"]

    # 2. Match på vores egen slug (Fornavn Efternavn)
    slug = slugify(name)
    rows = sb_get("riders", f"slug=eq.{slug}&select=id&limit=1")
    if rows:
        return rows[0]["id"]

    # 3. PCS bruger "EFTERNAVN Fornavn" — prøv omvendt rækkefølge
    parts = name.strip().split()
    if len(parts) >= 2:
        reversed_slug = slugify(f"{' '.join(parts[1:])} {parts[0]}")
        rows = sb_get("riders", f"slug=eq.{reversed_slug}&select=id&limit=1")
        if rows:
            return rows[0]["id"]

    return None


# ── PCS startliste parser ────────────────────────────────────────────────────

def parse_flag_code(flag_el) -> str | None:
    """Udtrækker landekode fra PCS flag-span (fx class='flag au' → 'AU')."""
    return None  # bruges ikke i async context — se async version nedenfor


async def scrape_startlist(pcs_slug: str) -> list[dict]:
    """
    Henter startliste fra PCS via Playwright.
    PCS HTML-struktur (verificeret):
      .startlist_v4 > li (hold)
        .ridersCont > div > a.team  ← holdnavn
        .ridersCont > ul > li       ← ryttere
          span.bib                  ← startnummer
          span.flag.{landekode}     ← nationalitet
          a[href^=rider/]           ← navn + PCS-slug
          (klasse "dropout")        ← DNF/DNS
    """
    from playwright.async_api import async_playwright

    url = f"{BASE_URL}/race/{pcs_slug}/{YEAR}/startlist"
    print(f"  Henter: {url}")

    entries = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0"
        )
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        # Fjern cookie-popup så indholdet er tilgængeligt
        await page.evaluate(
            "document.querySelectorAll('[id*=cmp],[class*=cmpbox]').forEach(e=>e.remove())"
        )

        title = await page.title()
        if "not found" in title.lower() or "404" in title:
            print(f"  Startliste ikke fundet for {pcs_slug}")
            await browser.close()
            return []

        # Hent alle hold-blokke fra .startlist_v4
        team_blocks = await page.query_selector_all(".startlist_v4 > li")
        if not team_blocks:
            # Fallback: prøv ul indeholdende .ridersCont
            team_blocks = await page.query_selector_all("li:has(.ridersCont)")

        for block in team_blocks:
            # Holdnavn fra a.team
            team_el = await block.query_selector("a.team")
            if not team_el:
                continue
            team_name_raw = (await team_el.inner_text()).strip()
            # Fjern kategori-suffix som "(WT)" eller "(PRT)"
            team_name = team_name_raw.split("(")[0].strip()

            rider_els = await block.query_selector_all(".ridersCont ul > li")
            for rider_el in rider_els:
                # Startnummer
                bib_el = await rider_el.query_selector(".bib")
                bib = None
                if bib_el:
                    bib_text = (await bib_el.inner_text()).strip()
                    bib = int(bib_text) if bib_text.isdigit() else None

                # Nationalitet fra flag-klasse (fx "flag au" → "AU")
                flag_el = await rider_el.query_selector("[class*='flag']")
                nationality = None
                if flag_el:
                    flag_class = await flag_el.get_attribute("class") or ""
                    for part in flag_class.split():
                        if part != "flag" and len(part) == 2:
                            nationality = part.upper()
                            break

                # Rytternavn og PCS-slug fra link
                rider_link = await rider_el.query_selector("a[href]")
                if not rider_link:
                    continue
                rider_name = (await rider_link.inner_text()).strip().rstrip("*").strip()
                rider_href = await rider_link.get_attribute("href") or ""
                pcs_rider_slug = rider_href.split("rider/")[-1] if "rider/" in rider_href else ""

                # Status: DNF/DNS fra klasse og tekst
                li_class = await rider_el.get_attribute("class") or ""
                rider_text = await rider_el.inner_text()
                status = "active"
                if "dropout" in li_class:
                    if "DNF" in rider_text:
                        status = "dnf"
                    elif "DNS" in rider_text:
                        status = "dns"
                    elif "DSQ" in rider_text:
                        status = "dsq"
                    else:
                        status = "dnf"

                entries.append({
                    "team_name": team_name,
                    "rider_name": rider_name,
                    "pcs_rider_slug": pcs_rider_slug,
                    "nationality": nationality,
                    "bib": bib,
                    "status": status,
                    "is_gc_captain": False,   # inféreres bagefter
                    "is_sprint_captain": False,
                    "source_url": url,
                })

        await browser.close()

    print(f"  Fandt {len(entries)} ryttere ({sum(1 for e in entries if e['status']=='active')} aktive)")
    return entries


# ── Kaptajn-inferens ─────────────────────────────────────────────────────────

def infer_captains(entries: list[dict]) -> list[dict]:
    """
    Hvis PCS ikke markerer kaptajner eksplicit, udleder vi dem fra
    specialitet og UCI-ranking for den bedste rytter per hold.
    """
    # Hent alle relevante ryttere fra DB med ranking og specialitet
    slugs = [slugify(e["rider_name"]) for e in entries]
    # Batch lookup — max 50 ad gangen
    riders_by_slug = {}
    for i in range(0, len(slugs), 50):
        batch = slugs[i:i+50]
        slug_list = ",".join(f'"{s}"' for s in batch)
        rows = sb_get(
            "riders",
            f"slug=in.({slug_list})&select=id,slug,speciality,uci_ranking"
        )
        for r in rows:
            riders_by_slug[r["slug"]] = r

    # Find bedste GC-rytter og sprinter per hold
    teams: dict[str, list] = {}
    for entry in entries:
        if entry["team_name"] not in teams:
            teams[entry["team_name"]] = []
        rider_slug = slugify(entry["rider_name"])
        rider_data = riders_by_slug.get(rider_slug, {})
        teams[entry["team_name"]].append((entry, rider_data))

    gc_specialities = {"Climber", "GC", "All-rounder", "Time trialist"}
    sprint_specialities = {"Sprinter", "Puncheur"}

    for team_entries in teams.values():
        has_gc = any(e["is_gc_captain"] for e, _ in team_entries)
        has_sprint = any(e["is_sprint_captain"] for e, _ in team_entries)

        if not has_gc:
            # Vælg bedst rangerede GC-specialist
            gc_candidates = [
                (e, r) for e, r in team_entries
                if r.get("speciality") in gc_specialities
            ]
            if gc_candidates:
                best = min(
                    gc_candidates,
                    key=lambda x: x[1].get("uci_ranking") or 9999
                )
                best[0]["is_gc_captain"] = True
            elif team_entries:
                # Fallback: bedst rangerede rytter på holdet
                best = min(
                    team_entries,
                    key=lambda x: x[1].get("uci_ranking") or 9999
                )
                best[0]["is_gc_captain"] = True

        if not has_sprint:
            sprint_candidates = [
                (e, r) for e, r in team_entries
                if r.get("speciality") in sprint_specialities
            ]
            if sprint_candidates:
                best = min(
                    sprint_candidates,
                    key=lambda x: x[1].get("uci_ranking") or 9999
                )
                best[0]["is_sprint_captain"] = True

    return entries


# ── Gem til DB ───────────────────────────────────────────────────────────────

def save_startlist(race_id: str, pcs_slug: str, entries: list[dict]) -> None:
    if not entries:
        return

    entries = infer_captains(entries)
    records = []

    for entry in entries:
        team_id = lookup_team(entry["team_name"])
        rider_id = lookup_rider(entry["rider_name"], entry.get("pcs_rider_slug", ""))

        if not rider_id:
            print(f"    Rytter ikke fundet: {entry['rider_name']}")

        records.append({
            "race_id": race_id,
            "team_id": team_id,
            "rider_id": rider_id,
            "bib_number": entry.get("bib"),
            "is_gc_captain": entry.get("is_gc_captain", False),
            "is_sprint_captain": entry.get("is_sprint_captain", False),
            "status": entry.get("status", "active"),
            "source_url": entry.get("source_url"),
        })

    # Gem i batches af 50
    for i in range(0, len(records), 50):
        batch = records[i:i+50]
        sb_upsert("startlists", batch, conflict="race_id,rider_id")

    # Gem PCS URL på løbet
    sb_patch("races", race_id, {"pcs_url": f"{BASE_URL}/race/{pcs_slug}/{YEAR}"})

    captains_gc = sum(1 for e in entries if e.get("is_gc_captain"))
    captains_sprint = sum(1 for e in entries if e.get("is_sprint_captain"))
    print(f"  Gemt {len(records)} ryttere | {captains_gc} GC-kaptajner | {captains_sprint} sprint-kaptajner")


# ── Hovedprogram ─────────────────────────────────────────────────────────────

async def run(target_slug: str | None = None):
    slugs = [target_slug] if target_slug else PCS_RACE_SLUGS

    for pcs_slug in slugs:
        print(f"\n{'='*50}")
        print(f"Løb: {pcs_slug}")

        race = get_or_create_race(pcs_slug)
        if not race:
            print("  FEJL: Kunne ikke finde/oprette løb i DB")
            continue

        try:
            entries = await scrape_startlist(pcs_slug)
        except Exception as e:
            print(f"  SCRAPE FEJL: {e}")
            continue

        if entries:
            save_startlist(race["id"], pcs_slug, entries)
        else:
            print("  Ingen startliste-data (løb er måske ikke annonceret endnu)")

    print("\n\nFærdig!")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(run(target))
