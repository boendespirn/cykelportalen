"""
agent_catalog.py
Det autoritative katalog over, hvilke agenter og pipelines admin-dashboardet må
starte — og præcis hvilken kommando hver af dem svarer til.

Hvorfor kataloget ligger i kode og ikke i databasen:
  runner.py udfører kommandoer på ejerens egen maskine. Den må derfor ALDRIG
  køre en kommandostreng, den har fået tilsendt. Den slår i stedet et `job_key`
  op her og bygger selv kommandoen. Lå kataloget i databasen, skulle runneren
  alligevel have en hardkodet allowlist ved siden af — to kilder til sandhed,
  der ville komme ud af trit. Fra nettet kan man altså kun vælge HVILKET
  forudgodkendt job og HVILKET løb, aldrig hvad der køres.

Importeres af:
  - api.py    → viser kataloget i admin og validerer job_key ved indkøring
  - runner.py → bygger og udfører kommandoen

Kør `python agent_catalog.py` for at se kataloget og de kommandoer, det giver.
"""

from __future__ import annotations

import os
import re
import sys

ROOT_DIR   = os.path.dirname(os.path.abspath(__file__))
AGENTS_DIR = os.path.join(ROOT_DIR, "agents")

# DB-slug ser altid ud som "<base>-<år>", fx "tour-de-france-2026".
DB_SLUG_RE = re.compile(r"^(?P<base>[a-z0-9-]+?)-(?P<year>(19|20)\d{2})$")

# Kun disse tegn må optræde i et løbs-slug, der kommer udefra. Alt andet
# afvises, før det kommer i nærheden af en kommandolinje.
SAFE_SLUG_RE = re.compile(r"^[a-z0-9-]{3,80}$")

# Faser i et løbs livscyklus — styrer grupperingen i admin-UI'et.
PHASE_BEFORE = "before"   # før løbet: startliste, etapedata, profiler
PHASE_DURING = "during"   # under løbet: resultater, klassement, referater
PHASE_AFTER  = "after"    # efter løbet: historik og efterbehandling
PHASE_GLOBAL = "global"   # ikke bundet til ét løb: nyheder, tv, daglig kørsel

PHASE_LABELS = {
    PHASE_BEFORE: "Før løbet",
    PHASE_DURING: "Under løbet",
    PHASE_AFTER:  "Efter løbet",
    PHASE_GLOBAL: "Uafhængigt af løb",
}


def _job(key, label, phase, script, args=(), *, needs_race=True, cwd="agents",
         runner="python", description="", covers=(), est_minutes=2):
    """Ét katalogpunkt. `args` må indeholde pladsholderne {db_slug}, {pcs_slug}
    og {year} — de erstattes i build_command()."""
    return {
        "key": key,
        "label": label,
        "phase": phase,
        "script": script,
        "args": list(args),
        "needs_race": needs_race,
        "cwd": cwd,
        "runner": runner,
        "description": description,
        "covers": list(covers),
        "est_minutes": est_minutes,
    }


JOBS: dict[str, dict] = {j["key"]: j for j in [

    # ── Før løbet ────────────────────────────────────────────────────────────
    _job("startliste", "Startliste", PHASE_BEFORE,
         "startlist_agent.py", ["{pcs_slug}", "--year", "{year}"],
         description="Henter alle ryttere med hold og startnummer fra PCS.",
         covers=["startliste"], est_minutes=3),

    _job("etapedata", "Etapedata", PHASE_BEFORE,
         "stage_pcs_agent.py", ["{pcs_slug}", "--year", "{year}"],
         description="Opretter/opdaterer etaper: distance, type, start og mål.",
         covers=["etapedata"], est_minutes=4),

    _job("profilbilleder_pcs", "Højkvalitets profilbilleder", PHASE_BEFORE,
         "pcs_profile_image_agent.py", ["--race", "{db_slug}", "--overwrite"],
         description="Erstatter lavopløste PCS-profiler med versionerne fra /info/profiles.",
         covers=["etapeprofiler"], est_minutes=4),

    _job("etapeprofiler", "Hel-etape-højdeprofiler (eget design)", PHASE_BEFORE,
         "stage_profile_generator.py", ["--race", "{db_slug}", "--all", "--write-db"],
         description="Genererer vores egne højdeprofiler ud fra GPX. Kun disse må vises (LEG-001).",
         covers=["etapeprofiler"], est_minutes=8),

    _job("stigninger_opret", "Stigninger — opret rækker", PHASE_BEFORE,
         "gpx_climb_agent.py", ["--race", "{db_slug}"],
         description="Opretter stage_climbs med klatreinfo fra PCS. Skal køre før de to profil-job.",
         covers=["stigninger"], est_minutes=5),

    _job("stigningsprofiler_cf", "Stigningsprofiler (ClimbFinder)", PHASE_BEFORE,
         "climbfinder_agent.py", ["--race", "{db_slug}"],
         description="Henter profiler for de enkelte stigninger fra ClimbFinder.",
         covers=["stigningsprofiler"], est_minutes=10),

    _job("stigningsprofiler_gpx", "Stigningsprofiler (GPX-fallback)", PHASE_BEFORE,
         "climb_profile_generator.py",
         ["--race", "{db_slug}", "--all", "--style", "full", "--write-db"],
         description="Genererer profiler for de stigninger, ClimbFinder ikke fandt.",
         covers=["stigningsprofiler"], est_minutes=10),

    _job("roadbook", "Roadbook-fakta (ASO)", PHASE_BEFORE,
         "aso_roadbook_agent.py", ["--race", "{db_slug}", "--write"],
         description="Stigningskategorier og mellemspurter fra ASO's roadbook. No-op for ikke-ASO-løb.",
         covers=["stigninger"], est_minutes=3),

    _job("rytterbilleder", "Rytterbilleder", PHASE_BEFORE,
         "rider_photo_agent.py", ["--race", "{db_slug}"],
         description="Henter manglende eller brudte rytterfotos fra PCS.",
         covers=["rytterbilleder"], est_minutes=6),

    _job("rytterstats", "Rytterstats (vægt og højde)", PHASE_BEFORE,
         "rider_stats_agent.py", ["--race", "{db_slug}"],
         description="Udfylder vægt og højde for ryttere, der mangler det.",
         covers=["rytterstats"], est_minutes=6),

    _job("fuld_forberedelse", "Fuld forberedelse (hele pipelinen)", PHASE_BEFORE,
         "race_prep_pipeline.py", ["{pcs_slug}", "--year", "{year}"],
         description="Kører samtlige forberedelsestrin i rækkefølge. Tager lang tid.",
         covers=["startliste", "etapedata", "etapeprofiler", "stigninger",
                 "stigningsprofiler", "rytterbilleder", "rytterstats",
                 "resultater", "klassementer", "referater"],
         est_minutes=45),

    # ── Under løbet ──────────────────────────────────────────────────────────
    _job("resultater", "Resultater — seneste etape", PHASE_DURING,
         "results_agent.py", ["--race", "{db_slug}"],
         description="Top 10 og alle fire klassementer for den senest kørte etape.",
         covers=["resultater", "klassementer"], est_minutes=3),

    _job("resultater_alle", "Resultater — alle etaper", PHASE_DURING,
         "results_agent.py", ["--race", "{db_slug}", "--all-stages"],
         description="Henter resultat og klassement for samtlige kørte etaper. Bruges til at lukke huller.",
         covers=["resultater", "klassementer"], est_minutes=40),

    _job("referater", "Etapereferater", PHASE_DURING,
         "stage_recap_agent.py", ["--race", "{db_slug}", "--all-stages"],
         description="Skriver 'Sådan forløb etapen' ud fra PCS' LiveStats. Kræver at resultaterne er hentet først.",
         covers=["referater"], est_minutes=6),

    # ── Efter løbet ──────────────────────────────────────────────────────────
    _job("historisk_fortaelling", "Historisk fortælling", PHASE_AFTER,
         "historic_recap_agent.py", ["--race", "{db_slug}", "--all-stages"],
         description="Tilbageskuende fortælling til historiske etapesider (TourTracker-kilde).",
         covers=["historisk_fortaelling"], est_minutes=6),

    # ── Uafhængigt af løb ────────────────────────────────────────────────────
    _job("nyheder_rss", "Nyheder — hent RSS", PHASE_GLOBAL,
         "rss_news_scraper.py", [], needs_race=False,
         description="Scraper nye rånyheder fra RSS-kilderne.",
         est_minutes=3),

    _job("nyheder_ai", "Nyheder — AI-behandling", PHASE_GLOBAL,
         "ai_news_processor.py", ["--limit", "15"], needs_race=False, cwd="root",
         description="Scorer rånyheder og lægger de bedste i admin-køen.",
         est_minutes=5),

    _job("tv_tider", "TV-tider", PHASE_GLOBAL,
         "tv_agent.py", [], needs_race=False,
         description="Opdaterer sendeplanen for de kommende løb.",
         covers=["tv"], est_minutes=3),

    _job("daglig_pipeline", "Daglig kørsel (hele pipelinen)", PHASE_GLOBAL,
         "daily_pipeline.ps1", [], needs_race=False, cwd="root", runner="powershell",
         description="Nyheder, resultater, etapereferater, TV-tider og social posting i ét.",
         covers=["resultater", "klassementer", "referater", "tv"],
         est_minutes=25),
]}


def list_jobs() -> list[dict]:
    """Kataloget som en liste — i katalogets egen rækkefølge, så UI'et viser
    trinnene i den rækkefølge, de normalt køres."""
    return list(JOBS.values())


def split_race_slug(db_slug: str) -> tuple[str, int]:
    """'tour-de-france-2026' → ('tour-de-france', 2026)."""
    m = DB_SLUG_RE.match(db_slug)
    if not m:
        raise ValueError(f"Ugyldigt løbs-slug: {db_slug!r} (forventer '<navn>-<år>')")
    return m.group("base"), int(m.group("year"))


def pcs_slug_for(db_slug: str) -> str:
    """DB-slug → det slug, PCS bruger.

    De fleste løb hedder det samme begge steder; undtagelserne står i
    startlist_agent.PCS_TO_DB_SLUG, som vi vender om her i stedet for at
    duplikere listen (den ændrer sig, når nye løb tilføjes).
    """
    base, _ = split_race_slug(db_slug)
    if AGENTS_DIR not in sys.path:
        sys.path.insert(0, AGENTS_DIR)
    try:
        from startlist_agent import PCS_TO_DB_SLUG
    except Exception:
        # Kan modulet ikke importeres (fx manglende .env i et web-miljø), er
        # navnesammenfald langt det mest sandsynlige — brug basen som den er.
        return base
    for pcs, db_base in PCS_TO_DB_SLUG.items():
        if db_base == base:
            return pcs
    return base


def build_command(job_key: str, race_slug: str | None) -> list[str]:
    """Den ENESTE vej fra et job_key til en kommandolinje.

    Rejser ValueError ved ukendt job, manglende løb eller et slug, der ikke
    består SAFE_SLUG_RE — kaldes med data, der stammer fra en webformular.
    """
    job = JOBS.get(job_key)
    if job is None:
        raise ValueError(f"Ukendt job: {job_key!r}")

    if job["needs_race"]:
        if not race_slug:
            raise ValueError(f"Job {job_key!r} kræver et løb")
        if not SAFE_SLUG_RE.match(race_slug):
            raise ValueError(f"Ugyldigt løbs-slug: {race_slug!r}")
        _, year = split_race_slug(race_slug)
        subs = {
            "db_slug":  race_slug,
            "pcs_slug": pcs_slug_for(race_slug),
            "year":     str(year),
        }
    else:
        subs = {}

    cwd = cwd_for(job_key)
    script = os.path.join(cwd, job["script"])

    if job["runner"] == "powershell":
        head = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script]
    else:
        head = [sys.executable, script]

    return head + [a.format(**subs) for a in job["args"]]


def cwd_for(job_key: str) -> str:
    job = JOBS[job_key]
    return AGENTS_DIR if job["cwd"] == "agents" else ROOT_DIR


if __name__ == "__main__":
    demo = "tour-de-france-2026"
    for job in list_jobs():
        slug = demo if job["needs_race"] else None
        try:
            cmd = build_command(job["key"], slug)
            shown = " ".join(os.path.basename(c) if os.path.sep in c else c for c in cmd)
        except ValueError as e:
            shown = f"FEJL: {e}"
        print(f"{job['key']:<24} {PHASE_LABELS[job['phase']]:<18} {shown}")
