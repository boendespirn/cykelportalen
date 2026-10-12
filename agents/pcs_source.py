"""
pcs_source.py
Én kilde til sandhed for, hvad et løb hedder hos ProCyclingStats.

Hvorfor filen findes (DATA-007):
  Oversættelsen mellem vores slug og PCS' slug stod i fire uenige lister —
  `stage_pcs_agent.PCS_RACE_SLUGS`, `startlist_agent.PCS_RACE_SLUGS`,
  `tv_agent.RACE_KEYWORDS` og `races.pcs_url` i databasen. Følgerne var ikke
  teoretiske: startliste-agentens liste kendte hverken Omloop, Brugge-De Panne,
  Cyclassics, San Sebastián, Copenhagen Sprint eller Lombardia, så 14 af 21
  endagsløb fik ALDRIG hentet en startliste i 2026 — ikke fordi noget fejlede,
  men fordi løbet ikke stod på listen. Og PCS skifter slug uden varsel
  (`tour-of-flanders` → `ronde-van-vlaanderen`, hele Dauphinéen →
  `tour-auvergne-rhone-alpes`), hvorefter hver liste skulle rettes for sig.

Reglen herefter:
  **`races.pcs_url` i databasen er det eneste sted, PCS-navnet står.**
  Agenterne spørger her i stedet for at kende kalenderen selv. Et nyt løb på
  kalenderen bliver dermed automatisk kendt af alle agenter, så snart rækken
  har en pcs_url.

  De gamle lister bevares som NØDFALD, så et løb uden pcs_url stadig kan
  hentes — men nødfaldet siger tydeligt fra i loggen, for det er netop den
  tavse uenighed, filen her skal fjerne.

Kør `python agents/pcs_source.py --aar 2026` for at se sæsonens løb og deres
PCS-slug, og `--tjek` for at hente hver URL og se, om den stadig svarer. En tom
PCS-side betyder FORKERT SLUG, ikke "løbet er ikke kørt endnu" (DATA-006).
"""

from __future__ import annotations

import argparse
import io
import os
import re
import sys
from datetime import date

import requests
from dotenv import load_dotenv

# BEMÆRK: stdout pakkes IKKE om her. Modulet importeres af agenterne, og en ny
# TextIOWrapper om den samme buffer lukker bufferen, når den første wrapper
# bliver ryddet op — hvorefter alt videre print i processen dør med
# "I/O operation on closed file" (samme fælde som beskrevet i data_sources.py;
# den væltede stage_pcs_agent 2026-10-13). Omlægningen sker kun i __main__.
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

PCS_URL_MØNSTER = re.compile(r"/race/([^/]+)/(\d{4})")


def pcs_slug_fra_url(pcs_url: str | None) -> str | None:
    """'…/race/tour-auvergne-rhone-alpes/2026' → 'tour-auvergne-rhone-alpes'."""
    if not pcs_url:
        return None
    m = PCS_URL_MØNSTER.search(pcs_url)
    return m.group(1) if m else None


def saesonens_loeb(aar: int, kun_med_pcs: bool = True) -> list[dict]:
    """Alle løb i sæsonen, ældste først, med deres PCS-slug slået op.

    Det er denne liste, agenterne skal gå igennem, når de kører uden et
    bestemt løb — ikke en hardkodet konstant, der skal vedligeholdes i hånden
    hvert år.
    """
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races"
        f"?select=id,slug,name,pcs_url,race_type,start_date,end_date"
        f"&start_date=gte.{aar}-01-01&start_date=lt.{aar + 1}-01-01"
        f"&order=start_date.asc&limit=1000",
        headers=AUTH, timeout=60,
    )
    if not res.ok:
        print(f"[pcs_source] kunne ikke læse races: {res.status_code}")
        return []
    ud = []
    for r in res.json():
        r["pcs_slug"] = pcs_slug_fra_url(r.get("pcs_url"))
        if kun_med_pcs and not r["pcs_slug"]:
            continue
        ud.append(r)
    return ud


def loeb_for_pcs_slug(pcs_slug: str, aar: int) -> dict | None:
    """Vores races-række for et PCS-slug — slået op på pcs_url, ikke på en liste.

    Returnerer None, hvis ingen række peger på det slug. Kalderen skal så sige
    tydeligt fra i stedet for at oprette et nyt løb: et dublet-løb ved siden af
    det rigtige er værre end en fejlmeddelelse, fordi dataen lander et sted,
    ingen kigger.
    """
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races"
        f"?select=id,slug,name,pcs_url,race_type,start_date,end_date"
        f"&pcs_url=ilike.*/race/{pcs_slug}/{aar}*&limit=1",
        headers=AUTH, timeout=30,
    )
    rækker = res.json() if res.ok else []
    if not rækker:
        return None
    rækker[0]["pcs_slug"] = pcs_slug
    return rækker[0]


# ── Kilde-tjek før sæsonen ────────────────────────────────────────────────────

def tjek_saeson(aar: int) -> int:
    """Henter hver pcs_url og siger til, hvis den svarer tomt.

    Kræver Playwright, fordi PCS afviser almindelige klienter. Returnerer
    antallet af løb, der ikke svarede — 0 betyder, at hele kalenderen kan
    hentes.
    """
    import time

    from bs4 import BeautifulSoup
    from playwright.sync_api import sync_playwright

    loeb = saesonens_loeb(aar, kun_med_pcs=False)
    uden_url = [r for r in loeb if not r.get("pcs_slug")]
    med_url = [r for r in loeb if r.get("pcs_slug")]

    print(f"pcs_source — tjekker {len(med_url)} løb i {aar}\n")
    fejl = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for r in med_url:
            endags = (r.get("race_type") or "").startswith("one")
            url = r["pcs_url"].rstrip("/") + ("/result" if endags else "/stage-1/result")
            side = browser.new_page()
            side.set_extra_http_headers(
                {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
            try:
                side.goto(url, wait_until="domcontentloaded", timeout=20000)
                time.sleep(1.2)
                suppe = BeautifulSoup(side.content(), "html.parser")
                aktive = [c for c in suppe.find_all("div", class_="resultCont")
                          if "hide" not in (c.get("class") or [])]
                rækker = max([len(t.find_all("tr")) for c in aktive for t in c.find_all("table")] or [0])
            except Exception as e:
                rækker = 0
                print(f"     [{type(e).__name__}] {url}")
            side.close()
            if rækker >= 5:
                print(f"  OK   {r['slug']:52} {r['pcs_slug']}")
            else:
                fejl += 1
                print(f"  TOM  {r['slug']:52} {r['pcs_slug']}  ← forkert slug?")
        browser.close()

    for r in uden_url:
        print(f"  ?    {r['slug']:52} ingen pcs_url i databasen")
    print(f"\n{fejl} løb svarede tomt, {len(uden_url)} mangler pcs_url.")
    return fejl + len(uden_url)


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser()
    p.add_argument("--aar", type=int, default=date.today().year)
    p.add_argument("--tjek", action="store_true",
                   help="Hent hver PCS-URL og meld dem, der svarer tomt")
    args = p.parse_args()

    if args.tjek:
        sys.exit(1 if tjek_saeson(args.aar) else 0)

    for r in saesonens_loeb(args.aar, kun_med_pcs=False):
        print(f"{r['start_date']}  {r['slug']:52} {r.get('pcs_slug') or '— ingen pcs_url —'}")
