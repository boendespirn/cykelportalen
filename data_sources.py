"""
data_sources.py
Hvilke KILDER findes der for et løb — og hvilke pipeline-trin kan derfor køres?

Forskellen på denne fil og race_completeness.py er vigtig:

  race_completeness.py  svarer på "hvad HAR vi hentet?"
  data_sources.py       svarer på "hvad KAN overhovedet hentes?"

Uden det andet spørgsmål ser et løb uden GPX-kilde ud, som om nogen bare har
glemt at trykke på knappen. Man trykker, agenten springer stille over, og næste
gang står manglen der stadig. Med kilderne på bordet ved man med det samme, at
trinnet ikke kan lade sig gøre for dette løb — og hvad man så kan køre i stedet.

De fem kilder, og hvordan de afgøres:

  PCS-løbsside      races.pcs_url. Alt fra ProCyclingStats hænger på den:
                    startliste, etapedata, resultater, rytterstats.

  PCS-etapesider    stages.pcs_stage_url pr. etape. Uden dem kan hverken
                    profilbillederne eller stigningsrækkerne hentes.

  PCS-live          Etapereferatet læses fra …/stage-N/live. Den side findes kun
                    for etapeløb: for endagsløb peger vores URL på løbets
                    forside, og /live derfra svarer 403 (afprøvet 2026-09-09 på
                    Paris-Roubaix, Flandern og Milano-Sanremo). Derfor afgøres
                    den på, om etape-URL'erne overhovedet har et /stage-N-led.

  GPX               climb_profile_generator.CYCLINGSTAGE_GPX_PAGES. Både vores
                    egen hel-etape-højdeprofil og VeloViewer-matchningen bruger
                    ruten, så uden GPX kan ingen af dem laves.

  ASO-roadbook      aso_roadbook_agent.ASO_SITES. Kun ASO's egne løb.

Kilde-nøglerne her skal matche `source` på trinnene i agent_catalog.py — det er
dét, der kobler "kilden mangler" sammen med "dette trin springes over".

Importeres af api.py. Kør `python data_sources.py <løbs-slug>` for at se svaret.
"""

from __future__ import annotations

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

JA      = "ja"
DELVIST = "delvist"
NEJ     = "nej"
UKENDT  = "ukendt"
# En kilde, der slet ikke gaelder for loebet. Adskilt fra NEJ med vilje:
# "ASO-roadbook findes ikke for Tour de Pologne" er ikke en mangel, der
# skal advares om paa hvert eneste ikke-ASO-loeb - og en advarsel, der
# altid staar der, holder man op med at laese.
IKKE_RELEVANT = "ikke_relevant"


def _agents_on_path() -> None:
    agents_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agents")
    if agents_dir not in sys.path:
        sys.path.insert(0, agents_dir)


# Agenterne pakker ved import sys.stdout ind i en ny TextIOWrapper for at kunne
# skrive dansk på en Windows-konsol. Bliver DEN wrapper senere frigivet, lukker
# den den underliggende buffer, og alt videre print i processen dør med
# "I/O operation on closed file". Vi beholder derfor en reference til hver
# wrapper for evigt — den koster nogle få bytes, og alternativet er, at et
# opslag i kataloget kan gøre api.py stum.
_HOLDT_I_LIVE: list = []


def _agent_attr(modul: str, navn: str):
    """Henter én konstant ud af et agent-modul uden at efterlade processens
    stdout omlagt. Returnerer None, hvis modulet ikke kan importeres (fx et
    web-miljø uden agenternes afhængigheder)."""
    _agents_on_path()
    gammel_out, gammel_err = sys.stdout, sys.stderr
    try:
        import importlib
        return getattr(importlib.import_module(modul), navn)
    except Exception:
        return None
    finally:
        if sys.stdout is not gammel_out:
            _HOLDT_I_LIVE.append(sys.stdout)
            sys.stdout = gammel_out
        if sys.stderr is not gammel_err:
            _HOLDT_I_LIVE.append(sys.stderr)
            sys.stderr = gammel_err


def gpx_pages() -> dict | None:
    """GPX-kortet fra climb_profile_generator. None betyder "kan ikke afgøres" —
    modulet kunne ikke importeres — og det skal vises som netop dét, ikke som et
    kryds, der ville få et trin til at se umuligt ud uden grund."""
    return _agent_attr("climb_profile_generator", "CYCLINGSTAGE_GPX_PAGES")


def aso_sites() -> dict | None:
    return _agent_attr("aso_roadbook_agent", "ASO_SITES")


def _kilde(key, label, status, detail, paavirker=()):
    return {
        "key": key,
        "label": label,
        "status": status,               # ja | delvist | nej | ukendt
        "detail": detail,
        "paavirker": list(paavirker),   # hvad kilden bruges til, i klar tekst
    }


def race_sources(race_slug: str) -> list[dict] | None:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?slug=eq.{race_slug}"
        f"&select=id,name,slug,pcs_url&limit=1",
        headers=HEADERS, timeout=30,
    )
    rows = res.json() if res.ok and isinstance(res.json(), list) else []
    if not rows:
        return None
    race = rows[0]

    st = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages?race_id=eq.{race['id']}"
        f"&select=stage_number,pcs_stage_url,source_url&order=stage_number.asc&limit=100",
        headers=HEADERS, timeout=30,
    )
    stages = st.json() if st.ok and isinstance(st.json(), list) else []

    return [
        _pcs_race_source(race),
        _pcs_stage_source(stages),
        _pcs_live_source(stages),
        _gpx_source(race_slug),
        _aso_source(race_slug),
    ]


# ── De enkelte kilder ────────────────────────────────────────────────────────

def _pcs_race_source(race):
    paavirker = ["Startliste", "Etapedata", "Resultater", "Rytterstats"]
    if race.get("pcs_url"):
        return _kilde("pcs_race", "PCS — løbsside", JA, race["pcs_url"], paavirker)
    return _kilde("pcs_race", "PCS — løbsside", NEJ,
                  "Ingen PCS-URL på løbet. Alt fra ProCyclingStats er blokeret.",
                  paavirker)


def _pcs_stage_source(stages):
    paavirker = ["Højkvalitets profilbilleder", "Stigninger — opret rækker"]
    if not stages:
        return _kilde("pcs_stages", "PCS — etapesider", NEJ,
                      "Ingen etaper oprettet endnu. Kør Ræsinfo for hele ræset først.",
                      paavirker)
    med = [s for s in stages if s.get("pcs_stage_url") or s.get("source_url")]
    if len(med) == len(stages):
        return _kilde("pcs_stages", "PCS — etapesider", JA,
                      f"Alle {len(stages)} etaper har en PCS-URL", paavirker)
    if med:
        return _kilde("pcs_stages", "PCS — etapesider", DELVIST,
                      f"{len(med)} af {len(stages)} etaper har en PCS-URL", paavirker)
    return _kilde("pcs_stages", "PCS — etapesider", NEJ,
                  f"Ingen af de {len(stages)} etaper har en PCS-URL", paavirker)


def _pcs_live_source(stages):
    """Live-tidslinjen findes kun for etapeløb.

    Vi afgør det på URL'ens form frem for at hente siden: et opslag pr. løb ville
    gøre dashboardet langsomt, og formen er et paalideligt kendetegn — en
    etapeside hedder …/stage-N, mens et endagsløb kun har løbets forside, hvor
    /live svarer 403.
    """
    paavirker = ["Etapereferat (trin 2 i Resultater)"]
    if not stages:
        return _kilde("pcs_live", "PCS — live-tidslinje", NEJ,
                      "Ingen etaper oprettet endnu", paavirker)
    urls = [(s.get("pcs_stage_url") or s.get("source_url") or "") for s in stages]
    med_stage = [u for u in urls if "/stage-" in u]
    if med_stage and len(med_stage) == len(stages):
        return _kilde("pcs_live", "PCS — live-tidslinje", JA,
                      f"Etapeløb — tidslinje pr. etape på alle {len(stages)} etaper",
                      paavirker)
    if med_stage:
        return _kilde("pcs_live", "PCS — live-tidslinje", DELVIST,
                      f"{len(med_stage)} af {len(stages)} etaper har en etape-URL med tidslinje",
                      paavirker)
    return _kilde("pcs_live", "PCS — live-tidslinje", NEJ,
                  "Endagsløb — PCS har ingen live-tidslinje at skrive referatet ud fra "
                  "(/live på løbets forside svarer 403). Etapereferatet springes over.",
                  paavirker)


def _gpx_source(race_slug):
    paavirker = ["Hel-etape-højdeprofil (eget design)", "Stigningsprofiler (VeloViewer)"]
    pages = gpx_pages()
    if pages is None:
        return _kilde("gpx", "GPX-rute (cyclingstage.com)", UKENDT,
                      "Kunne ikke slå GPX-kilderne op i dette miljø", paavirker)
    if race_slug in pages:
        return _kilde("gpx", "GPX-rute (cyclingstage.com)", JA, pages[race_slug], paavirker)
    return _kilde("gpx", "GPX-rute (cyclingstage.com)", NEJ,
                  "Ingen GPX-kilde konfigureret for løbet (se CYCLINGSTAGE_GPX_PAGES). "
                  "Uden ruten kan hverken vores egen højdeprofil eller "
                  "VeloViewer-matchningen laves.", paavirker)


def _aso_source(race_slug):
    paavirker = ["Roadbook-fakta (trin 5 i Ræsinfo)"]
    sites = aso_sites()
    if sites is None:
        return _kilde("aso", "ASO-roadbook", UKENDT,
                      "Kunne ikke slå ASO-løbene op i dette miljø", paavirker)
    if race_slug in sites:
        return _kilde("aso", "ASO-roadbook", JA, sites[race_slug], paavirker)
    return _kilde("aso", "ASO-roadbook", IKKE_RELEVANT,
                  "Ikke et ASO-løb. Trinnet springer over af sig selv og er ufarligt "
                  "— det er ikke en mangel.", paavirker)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Brug: python data_sources.py <løbs-slug>")
        sys.exit(1)
    kilder = race_sources(sys.argv[1])
    if kilder is None:
        print("Løbet blev ikke fundet")
        sys.exit(1)
    ikon = {JA: "OK ", DELVIST: "~  ", NEJ: "X  ", UKENDT: "?  ", IKKE_RELEVANT: "-  "}
    for k in kilder:
        print(f"{ikon.get(k['status'], '?  ')}{k['label']:<30} {k['detail']}")
        print(f"     bruges til: {', '.join(k['paavirker'])}")
