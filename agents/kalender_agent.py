"""
kalender_agent.py — opretter naeste saesons loeb i `races`, saa workeren har
noget at regne paa.

HVORFOR. Skemalaeggeren (scheduler.py) planlaegger alt ud fra `races`: et loeb,
der ikke staar der, faar aldrig startliste, etaper, resultater eller tekst.
2026-kalenderen blev lagt ind i haanden (race_agent.py mod velowire, cross fra
cykelkalenderen), og det stod derfor som et kendt hul i docs/automatisering.md
§6: "Kalenderen for naeste saeson ... skal oprettes med pcs_url, foer
skemalaeggeren har noget at regne paa."

KILDER.
  * Landevej: PCS' egen WorldTour-kalender (races.php?year=N&circuit=1). Den
    giver baade datoerne og PCS-slug'en, og slug'en er det eneste, de oevrige
    agenter skal bruge (pcs_source.py: races.pcs_url er den ene sandhed).
    Maalt 2026-11-08: 36 loeb for 2027, alle med samme PCS-slug som i 2026.
  * Cykelcross: cykelkalenderen.dk's CX-kalender, samme kilde som 2026-loebene
    kom fra. Vi tager de serier, vi i forvejen henter data for (World Cup,
    Superprestige, X2O Trofee, HG Cross) og VM — herreloebene. Siden svarer
    HTTP 454 uden browser, saa den hentes med Playwright.

REGLER.
  * Agenten OPRETTER kun. En eksisterende raekke roeres aldrig — heller ikke
    dens dato — fordi den kan vaere rettet i haanden eller af en anden agent.
  * Navn, kategori og land arves fra forrige aargang, naar PCS-slug'en er den
    samme. Saa hedder 2027-udgaven det samme som 2026 ("Tour Auvergne
    Rhône-Alpes (Critérium du Dauphiné)"), og vores slug foelger med.
  * Endagsloeb og cross faar etape 1 med datoen med det samme: skemalaeggeren
    planlaegger resultatjagten pr. etape, og et endagsloeb uden etape ville
    staa uden resultat. Etapeloebenes etaper kommer fra stage_pcs_agent.py, naar
    PCS har dem.

Koer:
    py agents/kalender_agent.py --aar 2027              # vis hvad der ville oprettes
    py agents/kalender_agent.py --aar 2027 --write
    py agents/kalender_agent.py --aar 2027 --kun cross --write
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
import time
from datetime import date

import requests
from dotenv import load_dotenv
from slugify import slugify

if (getattr(sys.stdout, "encoding", "") or "").lower().replace("-", "") != "utf8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
WRITE = {**AUTH, "Content-Type": "application/json", "Prefer": "return=representation"}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129 Safari/537.36")

PCS = "https://www.procyclingstats.com"
CX_KALENDER = "https://cykelkalenderen.dk/cyklecross-loeb-kalender"


def sb_get(table: str, params: str) -> list:
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}?{params}", headers=AUTH, timeout=45)
    r.raise_for_status()
    return r.json()


def sb_post(table: str, row: dict) -> dict | None:
    r = requests.post(f"{SUPABASE_URL}/rest/v1/{table}", json=row, headers=WRITE, timeout=45)
    if not r.ok:
        print(f"    [DB-fejl] {table}: {r.status_code} {r.text[:200]}")
        return None
    data = r.json()
    return data[0] if data else None


# ── Landevej: PCS ─────────────────────────────────────────────────────────────

def pcs_kalender(aar: int) -> list[dict]:
    """WorldTour-kalenderen fra PCS. Hver raekke: navn, datoer, PCS-slug, type."""
    from bs4 import BeautifulSoup
    r = requests.get(f"{PCS}/races.php?year={aar}&circuit=1&filter=Filter",
                     headers={"User-Agent": UA}, timeout=45)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    ud = []
    for tr in soup.select("table tr"):
        celler = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
        a = tr.find("a", href=True)
        if len(celler) < 3 or not a:
            continue
        # "race/tour-down-under-2027-gc" / "race/strade-bianche-2027-result"
        m = re.match(rf"race/(.+)-{aar}-(gc|result)$", a["href"])
        if not m:
            continue
        datoer = re.findall(r"(\d{2})\.(\d{2})", celler[0])
        if not datoer:
            continue
        start = date(aar, int(datoer[0][1]), int(datoer[0][0]))
        slut = date(aar, int(datoer[-1][1]), int(datoer[-1][0]))
        ud.append({
            "pcs_slug": m.group(1),
            "navn": re.sub(r"\s+ME$", "", celler[2]).strip(),
            "start": start.isoformat(), "slut": slut.isoformat(),
            "race_type": "stage_race" if m.group(2) == "gc" else "oneday",
        })
    return ud


def forrige_udgave(pcs_slug: str, aar: int) -> dict | None:
    """Samme loeb aaret foer, fundet paa PCS-slug'en i races.pcs_url."""
    rows = sb_get("races", "select=slug,name,category,country_code,race_type"
                           f"&pcs_url=eq.{PCS}/race/{pcs_slug}/{aar - 1}&limit=1")
    return rows[0] if rows else None


def landevej(aar: int) -> list[dict]:
    raekker = []
    for l in pcs_kalender(aar):
        gl = forrige_udgave(l["pcs_slug"], aar)
        if gl:
            base = re.sub(rf"-{aar - 1}$", "", gl["slug"])
            navn, kategori, land = gl["name"], gl["category"], gl["country_code"]
        else:
            base, navn, kategori, land = slugify(l["navn"]), l["navn"], "UCI WorldTour", None
        raekker.append({
            "slug": f"{base}-{aar}", "name": navn, "category": kategori,
            "country_code": land, "start_date": l["start"], "end_date": l["slut"],
            "race_type": l["race_type"],
            "pcs_url": f"{PCS}/race/{l['pcs_slug']}/{aar}",
            "source": "pcs", "source_url": f"{PCS}/races.php?year={aar}&circuit=1",
            "_arvet": bool(gl),
        })
    return raekker


# ── Cykelcross: cykelkalenderen ───────────────────────────────────────────────

# Serie-etiketten paa cykelkalenderen -> vores kategori. Kun de serier, vi
# allerede henter startlister og resultater for (cross_startlist_agent.py,
# cross_results_agent.py), plus VM. Danske loeb og enkeltstaaende crosser er
# udeladt med vilje: dem har vi ingen datakilde til endnu.
SERIER = {
    "WORLD CUP": "UCI Cyclocross World Cup",
    "SUPERPRESTIGE": "Superprestige",
    "X²O TROFEE": "X2O Trofee",
    "HG CROSS": "HG Cross",
}
MAANEDER = {"JAN": 1, "FEB": 2, "MAR": 3, "SEP": 9, "OKT": 10, "NOV": 11, "DEC": 12}
SERIE_SITE = {"HG Cross": "https://hgcross.be"}


def _hent_cx_side() -> str:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page()
        pg.goto(CX_KALENDER, wait_until="networkidle", timeout=60_000)
        time.sleep(2)
        html = pg.content()
        b.close()
    return html


def cross(aar: int) -> list[dict]:
    """Herreloebene i de fire serier + VM med dato i `aar`."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(_hent_cx_side(), "html.parser")
    ud, set_ = [], set()
    for a in soup.find_all("a", href=re.compile(rf"^/loeb/.+-{aar}$")):
        href = a["href"]
        if re.search(r"-k-\d{4}$", href):              # kvindeloebet
            continue
        # Dato, serie og land staar i det omsluttende <article class="cx-event">,
        # ikke i linket — og med smaa bogstaver: VERSALERNE er CSS.
        kort = a.find_parent("article") or a
        linjer = [x.strip().upper() if len(x.strip()) <= 14 else x.strip()
                  for x in kort.get_text("\n", strip=True).split("\n") if x.strip()]
        serie = next((s for s in SERIER if s in linjer), None)
        er_vm = href.startswith("/loeb/vm-i-cyklecross-")
        if not serie and not er_vm:
            continue
        navn = next((x for x in linjer if "[M" in x), None)
        if not navn or "[M+K]" in navn and not er_vm:
            continue
        # Datoen staar som "01" + "JAN" lige foer serien
        dag = next((int(x) for x in linjer if re.fullmatch(r"\d{1,2}", x)), None)
        mnd = next((MAANEDER[x] for x in linjer if x in MAANEDER), None)
        land = next((x for x in linjer if re.fullmatch(r"[A-Z]{2}", x)), None)
        if not dag or not mnd:
            continue
        navn = re.sub(r"\s*\[[^\]]*\]\s*", "", navn)
        navn = re.sub(r"\s*\(tidl\.[^)]*\)", "", navn).strip()
        ck_slug = href.rsplit("/", 1)[1]
        if er_vm:
            kategori = "UCI Cyclocross World Championships"
            slug = f"vm-i-cykelcross-{aar}"
            navn = "VM i cykelcross"
        else:
            kategori = SERIER[serie]
            # Samme form som 2026-raekkerne: "uci-cx-world-cup-<by>-<aar>".
            slug = ck_slug.replace("uci-world-cup-", "uci-cx-world-cup-")
        if slug in set_:
            continue
        set_.add(slug)
        d = date(aar, mnd, dag).isoformat()
        ud.append({
            "slug": slug, "name": navn, "category": kategori, "country_code": land,
            "start_date": d, "end_date": d, "race_type": "cyclocross",
            "pcs_url": None, "source": "cykelkalenderen",
            "source_url": SERIE_SITE.get(kategori, CX_KALENDER),
        })
    return ud


# ── Skrivning ─────────────────────────────────────────────────────────────────

def opret(raekker: list[dict], skriv: bool) -> int:
    if not raekker:
        return 0
    eksisterende = {r["slug"] for r in sb_get(
        "races", "select=slug&slug=in.(" + ",".join(r["slug"] for r in raekker) + ")")}
    nye = 0
    for r in raekker:
        arvet = r.pop("_arvet", None)
        if r["slug"] in eksisterende:
            print(f"  findes   {r['slug']}")
            continue
        mark = "" if arvet in (None, True) else "  (NYT loeb — tjek navn og land)"
        print(f"  {'opretter' if skriv else 'ville oprette'} {r['slug']:<52} "
              f"{r['start_date']}  {r['category']}{mark}")
        nye += 1
        if not skriv:
            continue
        race = sb_post("races", r)
        if race and r["race_type"] in ("oneday", "cyclocross"):
            sb_post("stages", {"race_id": race["id"], "stage_number": 1,
                               "date": r["start_date"]})
    return nye


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aar", type=int, required=True)
    ap.add_argument("--kun", choices=["landevej", "cross"])
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    if not SUPABASE_URL or not SUPABASE_KEY:
        sys.exit("SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY mangler")

    i_alt = 0
    if args.kun in (None, "landevej"):
        print(f"Landevej {args.aar} (PCS WorldTour-kalender)")
        lv = landevej(args.aar)
        if not lv:
            # Tom kalender er et kildeproblem, ikke "ingen loeb": PCS svarer
            # 200 med en tom tabel paa et aar, de ikke har endnu.
            sys.exit(f"PCS' kalender for {args.aar} gav ingen loeb")
        i_alt += opret(lv, args.write)
    if args.kun in (None, "cross"):
        print(f"\nCykelcross {args.aar} (cykelkalenderen)")
        i_alt += opret(cross(args.aar), args.write)
    print(f"\n{i_alt} nye loeb {'oprettet' if args.write else '— intet gemt, koer med --write'}")


if __name__ == "__main__":
    main()
