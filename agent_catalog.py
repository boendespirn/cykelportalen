"""
agent_catalog.py
Det autoritative katalog over, hvilke agenter og pipelines admin-dashboardet må
starte — og præcis hvilke kommandoer hver af dem svarer til.

Hvorfor kataloget ligger i kode og ikke i databasen:
  runner.py udfører kommandoer på ejerens egen maskine. Den må derfor ALDRIG
  køre en kommandostreng, den har fået tilsendt. Den slår i stedet et `job_key`
  op her og bygger selv kommandoerne. Lå kataloget i databasen, skulle runneren
  alligevel have en hardkodet allowlist ved siden af — to kilder til sandhed,
  der ville komme ud af trit. Fra nettet kan man altså kun vælge HVILKET
  forudgodkendt job, HVILKET løb og HVILKEN etape, aldrig hvad der køres.

Et job består af ét eller flere TRIN. Et trin er én kommando. Flere trin i ét
job er dét, der gør "Ræsinfo" til én knap i stedet for fem: trinnene køres i
rækkefølge af den samme kørsel, med den samme log og den samme afbryd-knap.

Hvert job kan køres for HELE løbet eller for ÉN etape. Trinnene beskriver selv
begge tilfælde:
  args   — altid med
  whole  — lægges til, når jobbet køres for hele løbet
  stage  — lægges til, når der er valgt én etape; må indeholde {stage}.
           `stage=None` betyder, at trinnet ikke kan afgrænses til én etape;
           det springes så over, i stedet for at køre hele løbet bag ryggen på
           den, der bevidst valgte én etape.

Importeres af:
  - api.py    → viser kataloget i admin og validerer job_key ved indkøring
  - runner.py → bygger og udfører kommandoerne

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

# Ingen etape over dette nummer findes i virkeligheden. Grænsen står her, fordi
# etapenummeret ender i en kommandolinje og derfor skal afvises på vej ind.
MAX_STAGE_NUMBER = 30

# Faser i et løbs livscyklus — styrer grupperingen i admin-UI'et.
PHASE_BEFORE = "before"   # før løbet: startliste, ræsinfo, stigningsprofiler
PHASE_DURING = "during"   # under løbet: resultater, klassement, referater
PHASE_AFTER  = "after"    # efter løbet: historik og efterbehandling
PHASE_GLOBAL = "global"   # ikke bundet til ét løb: nyheder, tv, daglig kørsel

PHASE_LABELS = {
    PHASE_BEFORE: "Før løbet",
    PHASE_DURING: "Under løbet",
    PHASE_AFTER:  "Efter løbet",
    PHASE_GLOBAL: "Uafhængigt af løb",
}

# Job der er kørt før omlægningen af kataloget 2026-09-09. Rækkerne står stadig
# i agent_runs, og uden dette ville historikken vise et råt job_key uden
# forklaring på, hvorfor knappen ikke findes længere.
LEGACY_LABELS = {
    "etapedata":             "Etapedata (nu en del af Ræsinfo)",
    "profilbilleder_pcs":    "Højkvalitets profilbilleder (nu en del af Ræsinfo)",
    "etapeprofiler":         "Hel-etape-højdeprofiler (nu en del af Ræsinfo)",
    "stigninger_opret":      "Stigninger — opret rækker (nu en del af Ræsinfo)",
    "roadbook":              "Roadbook-fakta (nu en del af Ræsinfo)",
    "stigningsprofiler_cf":  "Stigningsprofiler (ClimbFinder) — udgået",
    "stigningsprofiler_gpx": "Stigningsprofiler (GPX-fallback) — udgået",
    "rytterbilleder":        "Rytterbilleder — udgået",
    "resultater_alle":       "Resultater — alle etaper (nu et omfang på Resultater)",
}


def _step(script, args=(), *, whole=(), stage=(), cwd="agents",
          runner="python", label=""):
    """Ét trin = én kommando. Se modulets docstring for whole/stage."""
    return {
        "script": script,
        "args":   list(args),
        "whole":  None if whole is None else list(whole),
        "stage":  None if stage is None else list(stage),
        "cwd":    cwd,
        "runner": runner,
        "label":  label or script,
    }


def _job(key, label, phase, steps, *, needs_race=True, description="",
         covers=(), est_minutes=2, est_stage_minutes=None):
    """Ét katalogpunkt.

    `steps` må indeholde både trin-dicts og job_keys (som streng) — en streng
    foldes rekursivt ud, så "Fuld forberedelse" kan bestå af de andre knapper i
    stedet for en kopi af deres kommandoer, der ville komme ud af trit.
    """
    return {
        "key": key,
        "label": label,
        "phase": phase,
        "steps": list(steps),
        "needs_race": needs_race,
        "description": description,
        "covers": list(covers),
        "est_minutes": est_minutes,
        # Én etape er markant hurtigere end hele løbet — vises i UI'et, så en
        # etapekørsel ikke ser ud til at tage 22 minutter.
        "est_stage_minutes": est_stage_minutes,
    }


JOBS: dict[str, dict] = {j["key"]: j for j in [

    # ── Før løbet ────────────────────────────────────────────────────────────
    _job("startliste", "Startliste", PHASE_BEFORE, [
            _step("startlist_agent.py", ["{pcs_slug}", "--year", "{year}"],
                  stage=None, label="Startliste (PCS)"),
         ],
         description="Henter alle ryttere med hold og startnummer fra PCS. Gælder hele løbet.",
         covers=["startliste"], est_minutes=3),

    # Den samlede informationspipeline. Alt det, en etapeside skal bruge for at
    # være komplet, hentes her i den rækkefølge, trinnene afhænger af hinanden:
    # etaperne skal findes, før de kan få profiler, og stigningsrækkerne skal
    # oprettes, før roadbooket kan skrive kategorier på dem (STG-023).
    _job("raesinfo", "Ræsinfo", PHASE_BEFORE, [
            _step("stage_pcs_agent.py", ["{pcs_slug}", "--year", "{year}"],
                  stage=["--stage", "{stage}"],
                  label="1/6 Etapedata (distance, type, start og mål)"),
            _step("pcs_profile_image_agent.py", ["--race", "{db_slug}", "--overwrite"],
                  stage=["--stage", "{stage}"],
                  label="2/6 Højkvalitets profilbilleder (PCS /info/profiles)"),
            _step("stage_profile_generator.py", ["--race", "{db_slug}", "--write-db"],
                  whole=["--all"], stage=["--stage", "{stage}"],
                  label="3/6 Hel-etape-højdeprofil i eget design (LEG-001)"),
            _step("gpx_climb_agent.py", ["--race", "{db_slug}"],
                  stage=["--stage", "{stage}"],
                  label="4/6 Stigninger — opret stage_climbs-rækker"),
            _step("aso_roadbook_agent.py", ["--race", "{db_slug}", "--write"],
                  stage=["--stages", "{stage}"],
                  label="5/6 Roadbook-fakta (ASO) — kategorier og mellemspurter"),
            # tv_agent.py scraper hele sendeplanen på én gang og kan ikke
            # afgrænses til én etape — derfor kun med, når hele løbet køres.
            # Den står også som selvstændig knap under "Uafhængigt af løb".
            _step("tv_agent.py", [], stage=None,
                  label="6/6 TV-tider (sendeplan)"),
         ],
         description="Alt om løbet og dets etaper i én kørsel: etapedata, profilbilleder, "
                     "vores egen højdeprofil, stigningsrækker, ASO-roadbook og TV-tider.",
         covers=["etapedata", "etapeprofiler", "stigninger", "tv"],
         est_minutes=22, est_stage_minutes=4),

    # Kun VeloViewer. ClimbFinder-profilerne blev taget ud 2026-09-09: vi viser
    # udelukkende VeloViewers eget embed (stage_climbs.veloviewer_segment_id),
    # så en pipeline, der hentede tredjepartsbilleder, havde intet at fylde.
    _job("stigningsprofiler", "Stigningsprofiler (VeloViewer)", PHASE_BEFORE, [
            _step("veloviewer_agent.py", ["--race", "{db_slug}", "--write-db"],
                  stage=["--stage", "{stage}"],
                  label="Strava-segment pr. stigning (VeloViewer-embed)"),
         ],
         description="Finder og verificerer Strava-segmentet for hver stigning. "
                     "Kun segment-ID'et gemmes — frontenden bygger selv VeloViewers embed.",
         covers=["stigningsprofiler"], est_minutes=12, est_stage_minutes=3),

    _job("rytterstats", "Rytterstats (vægt og højde)", PHASE_BEFORE, [
            _step("rider_stats_agent.py", ["--race", "{db_slug}"],
                  stage=None, label="Vægt og højde fra PCS"),
         ],
         description="Udfylder vægt og højde for ryttere, der mangler det. Gælder hele startlisten.",
         covers=["rytterstats"], est_minutes=6),

    _job("fuld_forberedelse", "Fuld forberedelse (hele pipelinen)", PHASE_BEFORE, [
            "startliste", "raesinfo", "stigningsprofiler", "rytterstats",
            "resultater", "referater",
         ],
         description="Kører samtlige trin i rækkefølge. Tager lang tid. "
                     "Vælges én etape, springes de trin over, der kun giver mening for hele løbet.",
         covers=["startliste", "etapedata", "etapeprofiler", "stigninger",
                 "stigningsprofiler", "rytterstats", "tv",
                 "resultater", "klassementer", "referater"],
         est_minutes=75, est_stage_minutes=12),

    # ── Under løbet ──────────────────────────────────────────────────────────
    _job("resultater", "Resultater og klassementer", PHASE_DURING, [
            _step("results_agent.py", ["--race", "{db_slug}"],
                  whole=["--all-stages"], stage=["--stage", "{stage}"],
                  label="Top 10 og alle fire klassementer"),
         ],
         description="Etaperesultat og klassement. Hele løbet lukker huller bagud; "
                     "én etape henter netop den.",
         covers=["resultater", "klassementer"], est_minutes=40, est_stage_minutes=3),

    _job("referater", "Etapereferater", PHASE_DURING, [
            _step("stage_recap_agent.py", ["--race", "{db_slug}"],
                  whole=["--all-stages"], stage=["--stage", "{stage}"],
                  label="'Sådan forløb etapen' fra PCS LiveStats"),
         ],
         description="Skriver etapereferatet ud fra PCS' LiveStats. Kræver at resultaterne er hentet først.",
         covers=["referater"], est_minutes=6, est_stage_minutes=2),

    # ── Efter løbet ──────────────────────────────────────────────────────────
    _job("historisk_fortaelling", "Historisk fortælling", PHASE_AFTER, [
            _step("historic_recap_agent.py", ["--race", "{db_slug}"],
                  whole=["--all-stages"], stage=["--stage", "{stage}"],
                  label="Tilbageskuende fortælling (TourTracker-kilde)"),
         ],
         description="Tilbageskuende fortælling til historiske etapesider.",
         covers=["historisk_fortaelling"], est_minutes=6, est_stage_minutes=2),

    # ── Uafhængigt af løb ────────────────────────────────────────────────────
    _job("nyheder_rss", "Nyheder — hent RSS", PHASE_GLOBAL, [
            _step("rss_news_scraper.py", [], stage=None, label="RSS-scrape"),
         ], needs_race=False,
         description="Scraper nye rånyheder fra RSS-kilderne.", est_minutes=3),

    _job("nyheder_ai", "Nyheder — AI-behandling", PHASE_GLOBAL, [
            _step("ai_news_processor.py", ["--limit", "15"], cwd="root",
                  stage=None, label="Scoring og udvælgelse"),
         ], needs_race=False,
         description="Scorer rånyheder og lægger de bedste i admin-køen.", est_minutes=5),

    _job("tv_tider", "TV-tider", PHASE_GLOBAL, [
            _step("tv_agent.py", [], stage=None, label="Sendeplan for kommende løb"),
         ], needs_race=False,
         description="Opdaterer sendeplanen for alle kommende løb. Indgår også i Ræsinfo.",
         covers=["tv"], est_minutes=3),

    _job("daglig_pipeline", "Daglig kørsel (hele pipelinen)", PHASE_GLOBAL, [
            _step("daily_pipeline.ps1", [], cwd="root", runner="powershell",
                  stage=None, label="Daglig kørsel"),
         ], needs_race=False,
         description="Nyheder, resultater, etapereferater, TV-tider og social posting i ét.",
         covers=["resultater", "klassementer", "referater", "tv"], est_minutes=25),
]}


# ── Opslag ───────────────────────────────────────────────────────────────────

def expand_steps(job_key: str, _seen: tuple[str, ...] = ()) -> list[dict]:
    """Jobbets trin, med job_key-henvisninger foldet ud.

    _seen bryder en henvisningsring: et job, der (via andre) peger på sig selv,
    ville ellers folde ud i det uendelige og hænge både API og runner.
    """
    if job_key in _seen:
        raise ValueError(f"Cirkulær henvisning i kataloget: {' -> '.join((*_seen, job_key))}")
    job = JOBS.get(job_key)
    if job is None:
        raise ValueError(f"Ukendt job: {job_key!r}")

    steps: list[dict] = []
    for entry in job["steps"]:
        if isinstance(entry, str):
            steps += expand_steps(entry, (*_seen, job_key))
        else:
            steps.append(entry)
    return steps


def supports_stage(job_key: str) -> bool:
    """Kan jobbet overhovedet afgrænses til én etape? Falsk, når hvert eneste
    trin er løbsdækkende — så skal UI'et ikke tilbyde et valg, der ikke findes."""
    return any(s["stage"] is not None for s in expand_steps(job_key))


def list_jobs() -> list[dict]:
    """Kataloget som en liste — i katalogets egen rækkefølge, så UI'et viser
    trinnene i den rækkefølge, de normalt køres."""
    out = []
    for job in JOBS.values():
        out.append({
            **{k: v for k, v in job.items() if k != "steps"},
            "supports_stage": job["needs_race"] and supports_stage(job["key"]),
            "step_labels": [s["label"] for s in expand_steps(job["key"])],
        })
    return out


def label_for(job_key: str) -> str:
    """Menneskeligt navn — også for job, der er taget ud af kataloget siden."""
    job = JOBS.get(job_key)
    if job:
        return job["label"]
    return LEGACY_LABELS.get(job_key, job_key)


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


def _cwd_path(step: dict) -> str:
    return AGENTS_DIR if step["cwd"] == "agents" else ROOT_DIR


def build_commands(job_key: str, race_slug: str | None,
                   stage_number: int | None = None) -> list[dict]:
    """Den ENESTE vej fra (job_key, løb, etape) til kommandolinjer.

    Returnerer en liste af {label, cmd, cwd} — ét element pr. trin, i den
    rækkefølge de skal køres. Rejser ValueError ved ukendt job, manglende løb,
    et slug der ikke består SAFE_SLUG_RE, eller et etapenummer uden for
    området — funktionen kaldes med data, der stammer fra en webformular.
    """
    job = JOBS.get(job_key)
    if job is None:
        raise ValueError(f"Ukendt job: {job_key!r}")

    if stage_number is not None:
        if not job["needs_race"]:
            raise ValueError(f"Job {job_key!r} hører ikke til et løb og kan ikke køres for én etape")
        if isinstance(stage_number, bool) or not isinstance(stage_number, int):
            raise ValueError(f"Etapenummer skal være et heltal, ikke {stage_number!r}")
        if not 1 <= stage_number <= MAX_STAGE_NUMBER:
            raise ValueError(f"Etapenummer uden for området 1–{MAX_STAGE_NUMBER}: {stage_number}")
        if not supports_stage(job_key):
            raise ValueError(f"Job {job_key!r} kan kun køres for hele løbet")

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
            "stage":    str(stage_number) if stage_number is not None else "",
        }
    else:
        subs = {}

    out: list[dict] = []
    for step in expand_steps(job_key):
        extra = step["whole"] if stage_number is None else step["stage"]
        if extra is None:
            if stage_number is not None:
                continue      # trinnet kan ikke afgrænses — spring det over
            extra = []        # whole=None: ingen ekstra argumenter, men kør

        cwd = _cwd_path(step)
        script = os.path.join(cwd, step["script"])
        if step["runner"] == "powershell":
            head = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", script]
        else:
            head = [sys.executable, script]

        out.append({
            "label": step["label"],
            "cmd":   head + [a.format(**subs) for a in (*step["args"], *extra)],
            "cwd":   cwd,
        })

    if not out:
        raise ValueError(f"Job {job_key!r} har ingen trin, der kan køres for én etape")
    return out


def scope_label(stage_number: int | None) -> str:
    """Kort beskrivelse af omfanget — bruges i log og i admin."""
    return "hele løbet" if stage_number is None else f"etape {stage_number}"


if __name__ == "__main__":
    demo = "tour-de-france-2026"
    for job in JOBS.values():
        slug = demo if job["needs_race"] else None
        stage_ok = job["needs_race"] and supports_stage(job["key"])
        print(f"\n{job['key']}  —  {job['label']}  [{PHASE_LABELS[job['phase']]}]"
              f"{'' if stage_ok else '  (kun hele løbet)'}")
        scopes = [None, 7] if stage_ok else [None]
        for scope in scopes:
            try:
                cmds = build_commands(job["key"], slug, scope)
            except ValueError as e:
                print(f"  {scope_label(scope)}: FEJL: {e}")
                continue
            print(f"  {scope_label(scope)}:")
            for c in cmds:
                shown = " ".join(os.path.basename(x) if os.path.sep in x else x
                                 for x in c["cmd"])
                print(f"    - {shown}")
