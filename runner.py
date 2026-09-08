"""
runner.py
Udfører de agent-/pipelinekørsler, du starter fra admin-dashboardet.

Kører på DIN PC — ikke i skyen. Agenterne kræver Playwright/Chromium,
ClimbFinder-login, GPX-kilder og .env, og det miljø findes kun her. Railway
kører kun api.py. Derfor: knappen i browseren lægger en række i `agent_runs`
med status='queued', og dette program henter den og udfører den.

Start den (og lad vinduet stå åbent, mens du bruger dashboardet):

    python runner.py

    python runner.py --once      kør ét job og stop (til fejlsøgning)
    python runner.py --list      vis kataloget
    python runner.py --job resultater --race la-vuelta-ciclista-a-espana-2026
                                 kør ét job direkte uden om dashboardet

Sikkerhed — læs dette, før du ændrer noget her:
  Runneren udfører ALDRIG en kommando, den har fået tilsendt. Den modtager kun
  et `job_key` og et løbs-slug, slår job'et op i agent_catalog.JOBS og bygger
  selv kommandoen derfra. Et ukendt job_key afvises. Det er hele grunden til,
  at det er forsvarligt at lade en webside starte processer på din maskine.
  Indfør aldrig et felt, hvor kommandoen eller dens argumenter kommer udefra.

Robusthed:
  - Ét job ad gangen. To tunge Playwright-kørsler samtidig løb tør for
    hukommelse under Vuelta-backfillen 2026-09-08.
  - Krasjer runneren midt i et job, står rækken tilbage som 'running'. Ved
    opstart nulstilles den slags forældede rækker til 'failed', så
    dashboardet ikke viser et job, der kører i al evighed.
  - Al udskrift gemmes; de sidste LOG_TAIL_CHARS tegn skrives til databasen,
    så du kan læse fejlen i admin uden adgang til maskinen.
"""

from __future__ import annotations

import argparse
import io
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

import agent_catalog
import run_validator

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

READ_HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
DB_HEADERS   = {**READ_HEADERS, "Content-Type": "application/json", "Prefer": "return=representation"}

RUNS_URL = f"{SUPABASE_URL}/rest/v1/agent_runs"

POLL_SECONDS   = 15
LOG_TAIL_CHARS = 8000     # nok til at rumme en Python-traceback med god margin
JOB_TIMEOUT_S  = 3 * 60 * 60
HOST           = socket.gethostname()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(msg: str) -> None:
    print(f"{datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


# ── Kø ────────────────────────────────────────────────────────────────────────

def claim_next_job() -> dict | None:
    """Tager det ældste ventende job og markerer det som kørende.

    Markeringen sker med `status=eq.queued` i selve PATCH-filteret, så to
    runnere aldrig kan tage det samme job: den andens PATCH rammer nul rækker.
    """
    res = requests.get(
        f"{RUNS_URL}?status=eq.queued&select=id,job_key,race_slug,args"
        f"&order=queued_at.asc&limit=1",
        headers=READ_HEADERS, timeout=30,
    )
    if not res.ok:
        log(f"[kø] kunne ikke læse køen: {res.status_code} {res.text[:120]}")
        return None
    rows = res.json()
    if not rows:
        return None

    row = rows[0]
    claim = requests.patch(
        f"{RUNS_URL}?id=eq.{row['id']}&status=eq.queued",
        json={"status": "running", "started_at": now(), "runner_host": HOST},
        headers=DB_HEADERS, timeout=30,
    )
    if not claim.ok or not claim.json():
        return None      # en anden runner nåede den først
    return row


def finish_job(run_id: str, exit_code: int, log_tail: str,
               verdict: str | None = None, note: str | None = None) -> None:
    status = "success" if exit_code == 0 else "failed"
    res = requests.patch(
        f"{RUNS_URL}?id=eq.{run_id}",
        json={
            "status": status,
            "finished_at": now(),
            "exit_code": exit_code,
            "log_tail": log_tail[-LOG_TAIL_CHARS:],
            "validation_verdict": verdict,
            "validation_note": note,
        },
        headers={**DB_HEADERS, "Prefer": "return=minimal"}, timeout=30,
    )
    if not res.ok:
        log(f"[db] kunne ikke gemme resultatet: {res.status_code} {res.text[:120]}")


def reset_stale_runs() -> None:
    """Rækker, der stod som 'running', da runneren sidst stoppede, kan ikke
    genoptages — processen er væk. Markér dem som fejlet, så dashboardet ikke
    viser et job, der tilsyneladende kører i al evighed."""
    res = requests.get(f"{RUNS_URL}?status=eq.running&select=id,job_key",
                       headers=READ_HEADERS, timeout=30)
    if not res.ok or not res.json():
        return
    stale = res.json()
    requests.patch(
        f"{RUNS_URL}?status=eq.running",
        json={
            "status": "failed",
            "finished_at": now(),
            "log_tail": "Kørslen blev afbrudt, da runneren stoppede. Start jobbet igen.",
        },
        headers={**DB_HEADERS, "Prefer": "return=minimal"}, timeout=30,
    )
    log(f"[opstart] nulstillede {len(stale)} afbrudt(e) kørsel/kørsler: "
        + ", ".join(s["job_key"] for s in stale))


def heartbeat() -> None:
    """Fortæller dashboardet, at runneren er i live. Uden det ville et klik på
    en knap se ud til at virke, mens jobbet i virkeligheden blot lå i kø, til
    PC'en næste gang blev tændt."""
    try:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/runner_status?on_conflict=host",
            json={"host": HOST, "last_seen": now()},
            headers={**DB_HEADERS, "Prefer": "resolution=merge-duplicates,return=minimal"},
            timeout=15,
        )
    except requests.RequestException:
        pass      # et manglende hjerteslag må aldrig stoppe en kørsel


def enqueue(job_key: str, race_slug: str | None, trigger: str = "cli") -> str | None:
    res = requests.post(
        RUNS_URL,
        json={"job_key": job_key, "race_slug": race_slug, "trigger": trigger},
        headers=DB_HEADERS, timeout=30,
    )
    if not res.ok:
        log(f"[kø] kunne ikke lægge job i kø: {res.status_code} {res.text[:160]}")
        return None
    return res.json()[0]["id"]


# ── Udførsel ──────────────────────────────────────────────────────────────────

def execute(job_key: str, race_slug: str | None) -> tuple[int, str]:
    """Kører jobbet og returnerer (exitkode, opsamlet output)."""
    try:
        cmd = agent_catalog.build_command(job_key, race_slug)
        cwd = agent_catalog.cwd_for(job_key)
    except ValueError as e:
        # Afvist af kataloget — ukendt job eller ugyldigt slug. Kør aldrig noget.
        return 2, f"Afvist af agent_catalog: {e}"

    label = agent_catalog.JOBS[job_key]["label"]
    header = f"$ {' '.join(cmd)}\n"
    log(f"[kør] {label}" + (f" — {race_slug}" if race_slug else ""))

    # Agenterne skriver dansk tekst; uden dette får vi UnicodeEncodeError, når
    # stdout ikke er en interaktiv UTF-8-terminal (samme fix som i agenterne).
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    try:
        proc = subprocess.run(
            cmd, cwd=cwd, env=env, timeout=JOB_TIMEOUT_S,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
        return proc.returncode, header + (proc.stdout or "")
    except subprocess.TimeoutExpired:
        return 124, header + f"Jobbet blev afbrudt efter {JOB_TIMEOUT_S // 3600} timer."
    except Exception as e:
        return 1, header + f"Kunne ikke starte processen: {type(e).__name__}: {e}"


def mark_started(run_id: str) -> None:
    """Bruges af --job-vejen, som springer køen over og derfor ikke er gået
    gennem claim_next_job()'s statusskift."""
    requests.patch(
        f"{RUNS_URL}?id=eq.{run_id}",
        json={"status": "running", "started_at": now(), "runner_host": HOST},
        headers={**DB_HEADERS, "Prefer": "return=minimal"}, timeout=30,
    )


def run_one(run: dict) -> None:
    job_key, race_slug = run["job_key"], run.get("race_slug")

    # Øjebliksbilledet skal tages FØR kørslen — ellers kan valideringen ikke
    # se forskel på "hentede intet" og "der var intet at hente".
    job = agent_catalog.JOBS.get(job_key)
    before = run_validator.snapshot(race_slug, job["covers"]) if job else {}

    exit_code, output = execute(job_key, race_slug)

    try:
        verdict, note = run_validator.validate_run(job_key, race_slug, exit_code, output, before)
    except Exception as e:
        # En fejl i valideringen må aldrig skjule resultatet af selve kørslen.
        verdict, note = None, f"Valideringen kunne ikke gennemføres: {type(e).__name__}: {e}"

    finish_job(run["id"], exit_code, output, verdict, note)
    log(f"[færdig] {job_key} → exit {exit_code}" + (f" — {verdict}: {note}" if verdict else ""))


# ── Hoved ─────────────────────────────────────────────────────────────────────

def loop(once: bool) -> None:
    log(f"runner.py kører på {HOST} — poller hvert {POLL_SECONDS}. sekund. Ctrl+C for at stoppe.")
    reset_stale_runs()
    idle_notified = False
    while True:
        heartbeat()
        try:
            run = claim_next_job()
        except requests.RequestException as e:
            log(f"[net] {type(e).__name__}: {e} — prøver igen")
            time.sleep(POLL_SECONDS)
            continue

        if run is None:
            if not idle_notified:
                log("[venter] ingen job i køen")
                idle_notified = True
            if once:
                return
            time.sleep(POLL_SECONDS)
            continue

        idle_notified = False
        run_one(run)
        if once:
            return


def main() -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("FEJL: SUPABASE_URL og SUPABASE_SERVICE_ROLE_KEY skal stå i .env")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Udfører agent-job fra admin-dashboardet.")
    parser.add_argument("--once", action="store_true", help="Kør ét job og stop")
    parser.add_argument("--job", default=None, help="Læg dette job i køen og kør det med det samme")
    parser.add_argument("--race", default=None, help="Løbets DB-slug til --job")
    parser.add_argument("--list", action="store_true", help="Vis kataloget og stop")
    args = parser.parse_args()

    if args.list:
        for job in agent_catalog.list_jobs():
            scope = "kræver løb" if job["needs_race"] else "uden løb"
            print(f"{job['key']:<24} {job['label']:<45} ({scope})")
        return

    if args.job:
        if args.job not in agent_catalog.JOBS:
            print(f"FEJL: ukendt job {args.job!r}. Kør --list for at se kataloget.")
            sys.exit(1)
        run_id = enqueue(args.job, args.race)
        if not run_id:
            sys.exit(1)
        mark_started(run_id)
        run_one({"id": run_id, "job_key": args.job, "race_slug": args.race})
        return

    loop(args.once)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nrunner.py stoppet.")
