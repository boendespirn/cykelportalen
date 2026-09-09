"""
runner.py
Udfører de agent-/pipelinekørsler, du starter fra admin-dashboardet.

Kører på DIN PC — ikke i skyen. Agenterne kræver Playwright/Chromium,
GPX-kilder, Strava-nøgler og .env, og det miljø findes kun her. Railway kører
kun api.py. Derfor: knappen i browseren lægger en række i `agent_runs` med
status='queued', og dette program henter den og udfører den.

Start den (og lad vinduet stå åbent, mens du bruger dashboardet):

    python runner.py

    python runner.py --once      kør ét job og stop (til fejlsøgning)
    python runner.py --list      vis kataloget
    python runner.py --job resultater --race la-vuelta-ciclista-a-espana-2026
                                 kør ét job direkte uden om dashboardet
    python runner.py --job raesinfo --race tour-de-france-2026 --stage 7
                                 samme, men kun for én etape

Sikkerhed — læs dette, før du ændrer noget her:
  Runneren udfører ALDRIG en kommando, den har fået tilsendt. Den modtager kun
  et `job_key`, et løbs-slug og evt. et etapenummer, slår job'et op i
  agent_catalog.JOBS og bygger selv kommandoerne derfra. Et ukendt job_key
  afvises. Det er hele grunden til, at det er forsvarligt at lade en webside
  starte processer på din maskine. Indfør aldrig et felt, hvor kommandoen
  eller dens argumenter kommer udefra.

Fortryd og afbryd:
  Et job må ikke tages, før `not_before` er passeret. API'et sætter det et
  stykke ude i fremtiden (CANCEL_WINDOW_SECONDS i api.py), så der altid er tid
  til at nå Afbryd-knappen — uden det ville en kørsel, der ramte runnerens
  poll et sekund efter klikket, være i gang, før man nåede at fortryde.
  Er kørslen først startet, sætter Afbryd i stedet `cancel_requested`. Vi
  læser flaget undervejs og dræber processen (med hele dens træ — Playwright
  starter Chromium som barneproces, og den ville ellers leve videre).

Robusthed:
  - Ét job ad gangen. To tunge Playwright-kørsler samtidig løb tør for
    hukommelse under Vuelta-backfillen 2026-09-08.
  - Et job kan bestå af flere trin (fx "Ræsinfo"). Et trin, der fejler,
    stopper ikke de øvrige — de senere trin arbejder på data, der allerede
    ligger i databasen, og er derfor ofte stadig nyttige. Kørslen som helhed
    markeres som fejlet, og oversigten nederst i loggen viser hvilket trin.
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
import threading
import time
from collections import deque
from datetime import datetime, timezone
from urllib.parse import quote

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
CANCEL_POLL_S  = 5        # hvor ofte vi spørger, om Afbryd er trykket
LOG_TAIL_CHARS = 8000     # nok til at rumme en Python-traceback med god margin
MAX_STEP_LINES = 2000     # pr. trin — holder hukommelsen nede på lange kørsler
JOB_TIMEOUT_S  = 3 * 60 * 60
HOST           = socket.gethostname()

# Exitkode vi selv finder på. 130 er konventionen for "afbrudt af bruger".
EXIT_CANCELLED = 130


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _filter_value(value: str) -> str:
    """URL-koder en vaerdi, der skal staa i et PostgREST-filter.

    Noedvendig for tidsstempler: ISO-formatet slutter paa "+00:00", og et bart
    '+' i en query-streng laeses som et mellemrum. "...853629+00:00" naaede
    derfor frem som "...853629 00:00", PostgREST afviste hele kaldet med
    22007 (invalid input syntax for timestamp), og claim_next_job() fik aldrig
    fat i et eneste job. Fundet 2026-09-09, da etape 17's referat blev
    liggende i koeen for evigt.
    """
    return quote(value, safe="")


def log(msg: str) -> None:
    print(f"{datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


# ── Kø ────────────────────────────────────────────────────────────────────────

def claim_next_job() -> dict | None:
    """Tager det ældste ventende job, hvis fortryd-vinduet er udløbet, og
    markerer det som kørende.

    Markeringen sker med `status=eq.queued` i selve PATCH-filteret, så to
    runnere aldrig kan tage det samme job: den andens PATCH rammer nul rækker.
    `cancel_requested` filtreres fra som livrem-og-seler — API'et sætter selv
    status='cancelled' på et job, der afbrydes i køen, men rammer runneren og
    afbrydelsen samme sekund, må jobbet ikke slippe igennem alligevel.
    """
    res = requests.get(
        f"{RUNS_URL}?status=eq.queued&not_before=lte.{_filter_value(now())}&cancel_requested=is.false"
        f"&select=id,job_key,race_slug,stage_number,args"
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


def cancel_requested(run_id: str) -> bool:
    """Er Afbryd trykket, mens jobbet kørte? Et netværksglimt må ikke dræbe en
    kørsel, så vi svarer nej, når vi ikke kan få fat i databasen."""
    try:
        res = requests.get(
            f"{RUNS_URL}?id=eq.{run_id}&select=cancel_requested&limit=1",
            headers=READ_HEADERS, timeout=10,
        )
        rows = res.json() if res.ok else []
        return bool(rows and rows[0].get("cancel_requested"))
    except requests.RequestException:
        return False


def finish_job(run_id: str, exit_code: int, log_tail: str,
               verdict: str | None = None, note: str | None = None,
               cancelled: bool = False) -> None:
    status = "cancelled" if cancelled else ("success" if exit_code == 0 else "failed")
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


def enqueue(job_key: str, race_slug: str | None, stage_number: int | None = None,
            trigger: str = "cli") -> str | None:
    res = requests.post(
        RUNS_URL,
        json={"job_key": job_key, "race_slug": race_slug,
              "stage_number": stage_number, "trigger": trigger},
        headers=DB_HEADERS, timeout=30,
    )
    if not res.ok:
        log(f"[kø] kunne ikke lægge job i kø: {res.status_code} {res.text[:160]}")
        return None
    return res.json()[0]["id"]


# ── Udførsel ──────────────────────────────────────────────────────────────────

def _kill_tree(proc: subprocess.Popen) -> None:
    """Dræber processen OG dens børn.

    proc.kill() alene er ikke nok: agenterne starter Playwright, som starter
    Chromium i en egen proces. Dræber vi kun Python-processen, bliver browseren
    stående og æder hukommelse, indtil PC'en genstartes.
    """
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=30)
            return
        except Exception:
            pass      # falder igennem til den almindelige vej nedenfor
    try:
        proc.kill()
    except Exception:
        pass


def _run_step(cmd: list[str], cwd: str, run_id: str | None) -> tuple[int, str, bool]:
    """Kører én kommando. Returnerer (exitkode, output, blev_afbrudt).

    Outputtet læses i en baggrundstråd, mens hovedtråden holder øje med uret og
    med Afbryd-flaget. Uden den tråd ville et blokerende read() betyde, at vi
    først opdagede en afbrydelse, når processen alligevel var færdig.
    """
    # Agenterne skriver dansk tekst; uden dette får vi UnicodeEncodeError, når
    # stdout ikke er en interaktiv UTF-8-terminal (samme fix som i agenterne).
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
    except Exception as e:
        return 1, f"Kunne ikke starte processen: {type(e).__name__}: {e}\n", False

    lines: deque[str] = deque(maxlen=MAX_STEP_LINES)

    def pump() -> None:
        for line in proc.stdout:
            lines.append(line)
            print(line, end="", flush=True)

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()

    deadline   = time.monotonic() + JOB_TIMEOUT_S
    next_check = time.monotonic() + CANCEL_POLL_S
    cancelled  = False

    while proc.poll() is None:
        time.sleep(0.4)
        clock = time.monotonic()
        if clock > deadline:
            _kill_tree(proc)
            reader.join(timeout=10)
            lines.append(f"\nJobbet blev afbrudt efter {JOB_TIMEOUT_S // 3600} timer.\n")
            return 124, "".join(lines), False
        if run_id and clock >= next_check:
            next_check = clock + CANCEL_POLL_S
            if cancel_requested(run_id):
                log("[afbryd] Afbryd er trykket - stopper processen")
                _kill_tree(proc)
                cancelled = True
                break

    reader.join(timeout=10)
    if cancelled:
        lines.append("\n*** AFBRUDT: koerslen blev stoppet fra dashboardet. ***\n")
        return EXIT_CANCELLED, "".join(lines), True
    return proc.returncode, "".join(lines), False


def _summary(outcomes: list[tuple[str, str]], total: int) -> str:
    lines = [f"\n{'=' * 62}\nOversigt over trin:\n"]
    for i, (status, label) in enumerate(outcomes, 1):
        lines.append(f"  {i}/{total}  {status:<16} {label}\n")
    skipped = total - len(outcomes)
    if skipped:
        lines.append(f"  ({skipped} trin blev ikke koert)\n")
    return "".join(lines)


def execute(job_key: str, race_slug: str | None, stage_number: int | None,
            run_id: str | None = None) -> tuple[int, str, bool]:
    """Kører jobbets trin i rækkefølge.

    Returnerer (exitkode, opsamlet output, blev_afbrudt). Exitkoden er det
    FØRSTE trins kode, der ikke var 0 — så en fejl midt i en pipeline ikke kan
    skjules af, at det sidste trin gik godt.
    """
    try:
        steps = agent_catalog.build_commands(job_key, race_slug, stage_number)
    except ValueError as e:
        # Afvist af kataloget — ukendt job, ugyldigt slug eller etapenummer.
        # Kør aldrig noget.
        return 2, f"Afvist af agent_catalog: {e}", False

    label = agent_catalog.label_for(job_key)
    scope = agent_catalog.scope_label(stage_number)
    log(f"[koer] {label}" + (f" - {race_slug}, {scope}" if race_slug else ""))

    parts: list[str] = [f"{label} - {race_slug or 'uden loeb'} ({scope})\n"
                        f"{len(steps)} trin\n"]
    first_error = 0
    outcomes: list[tuple[str, str]] = []

    for i, step in enumerate(steps, 1):
        header = (f"\n{'=' * 62}\n"
                  f"Trin {i}/{len(steps)}: {step['label']}\n"
                  f"$ {' '.join(step['cmd'])}\n"
                  f"{'=' * 62}\n")
        print(header, end="", flush=True)
        parts.append(header)

        code, out, was_cancelled = _run_step(step["cmd"], step["cwd"], run_id)
        parts.append(out)

        if was_cancelled:
            outcomes.append(("AFBRUDT", step["label"]))
            parts.append(_summary(outcomes, len(steps)))
            return EXIT_CANCELLED, "".join(parts), True

        outcomes.append(("OK" if code == 0 else f"FEJL (exit {code})", step["label"]))
        if code != 0 and first_error == 0:
            first_error = code
        # Et fejlet trin stopper ikke de øvrige: de senere trin arbejder på data,
        # der allerede ligger i databasen, og er ofte stadig nyttige.

    parts.append(_summary(outcomes, len(steps)))
    return first_error, "".join(parts), False


def mark_started(run_id: str) -> None:
    """Bruges af --job-vejen, som springer køen over og derfor ikke er gået
    gennem claim_next_job()'s statusskift."""
    requests.patch(
        f"{RUNS_URL}?id=eq.{run_id}",
        json={"status": "running", "started_at": now(), "runner_host": HOST},
        headers={**DB_HEADERS, "Prefer": "return=minimal"}, timeout=30,
    )


def run_one(run: dict) -> None:
    job_key   = run["job_key"]
    race_slug = run.get("race_slug")
    stage     = run.get("stage_number")

    # Øjebliksbilledet skal tages FØR kørslen — ellers kan valideringen ikke
    # se forskel på "hentede intet" og "der var intet at hente".
    job = agent_catalog.JOBS.get(job_key)
    before = run_validator.snapshot(race_slug, job["covers"]) if job else {}

    exit_code, output, was_cancelled = execute(job_key, race_slug, stage, run["id"])

    if was_cancelled:
        # Ingen validering af en afbrudt kørsel: den nåede ikke at gøre sit
        # arbejde færdigt, så en "mangler stadig data"-dom ville være støj.
        finish_job(run["id"], exit_code, output, "skipped",
                   "Afbrudt fra dashboardet - ingen kontrol foretaget.", cancelled=True)
        log(f"[afbrudt] {job_key}")
        return

    try:
        verdict, note = run_validator.validate_run(job_key, race_slug, exit_code, output, before)
    except Exception as e:
        # En fejl i valideringen må aldrig skjule resultatet af selve kørslen.
        verdict, note = None, f"Valideringen kunne ikke gennemfoeres: {type(e).__name__}: {e}"

    finish_job(run["id"], exit_code, output, verdict, note)
    log(f"[faerdig] {job_key} -> exit {exit_code}" + (f" - {verdict}: {note}" if verdict else ""))


# ── Hoved ─────────────────────────────────────────────────────────────────────

def loop(once: bool) -> None:
    log(f"runner.py koerer paa {HOST} - poller hvert {POLL_SECONDS}. sekund. Ctrl+C for at stoppe.")
    reset_stale_runs()
    idle_notified = False
    while True:
        heartbeat()
        try:
            run = claim_next_job()
        except requests.RequestException as e:
            log(f"[net] {type(e).__name__}: {e} - proever igen")
            time.sleep(POLL_SECONDS)
            continue

        if run is None:
            if not idle_notified:
                log("[venter] ingen job i koeen")
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
        print("FEJL: SUPABASE_URL og SUPABASE_SERVICE_ROLE_KEY skal staa i .env")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Udfoerer agent-job fra admin-dashboardet.")
    parser.add_argument("--once", action="store_true", help="Koer eet job og stop")
    parser.add_argument("--job", default=None, help="Laeg dette job i koeen og koer det med det samme")
    parser.add_argument("--race", default=None, help="Loebets DB-slug til --job")
    parser.add_argument("--stage", type=int, default=None,
                        help="Koer kun for denne etape (default: hele loebet)")
    parser.add_argument("--list", action="store_true", help="Vis kataloget og stop")
    args = parser.parse_args()

    if args.list:
        for job in agent_catalog.list_jobs():
            scope = "kraever loeb" if job["needs_race"] else "uden loeb"
            if job["supports_stage"]:
                scope += ", kan koeres pr. etape"
            print(f"{job['key']:<24} {job['label']:<38} ({scope})")
            for step in job["step_labels"]:
                print(f"{'':<24}   - {step}")
        return

    if args.job:
        if args.job not in agent_catalog.JOBS:
            print(f"FEJL: ukendt job {args.job!r}. Koer --list for at se kataloget.")
            sys.exit(1)
        try:
            agent_catalog.build_commands(args.job, args.race, args.stage)
        except ValueError as e:
            print(f"FEJL: {e}")
            sys.exit(1)
        run_id = enqueue(args.job, args.race, args.stage)
        if not run_id:
            sys.exit(1)
        mark_started(run_id)
        run_one({"id": run_id, "job_key": args.job,
                 "race_slug": args.race, "stage_number": args.stage})
        return

    loop(args.once)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nrunner.py stoppet.")
