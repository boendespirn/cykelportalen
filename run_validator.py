"""
run_validator.py
Vurderer, om en agentkørsel rent faktisk hentede det rigtige — ikke bare om
den sluttede uden at krasje.

Hvorfor det er nødvendigt: exitkode 0 betyder kun, at processen ikke faldt om.
Den 2026-09-09 sluttede tv_agent.py med exit 0 efter at have fundet 11
programmer og gemt 0 af dem. To dage før havde results_agent.py exit 0 på en
etape, hvor kun 9 af 10 placeringer nåede databasen. Begge ville stå som
grønne kørsler i dashboardet. Det er den slags, der langsomt undergraver
tilliden til dataene — og tillid er hele forretningen (CLAUDE.md §4).

Sådan virker den:
  1. Før kørslen tages et øjebliksbillede af de fuldstændighedstjek, jobbet
     ifølge kataloget skulle udbedre (job["covers"]).
  2. Efter kørslen tages det samme billede igen.
  3. Forskellen, exitkoden og logens sidste linjer sendes til Claude, som
     svarer med én af tre domme og én sætning på dansk.

Deterministiske signaler afgøres her, ikke af modellen — en traceback er en
fejl, uanset hvad nogen mener om den. Claude bruges til det, der kræver
skøn: hvad loggen faktisk fortæller, og hvad ejeren bør gøre ved det.
Kan modellen ikke nås, står den deterministiske dom ved magt.

Importeres af runner.py.
"""

from __future__ import annotations

import os
import re

from dotenv import load_dotenv

import agent_catalog
from race_completeness import race_completeness

load_dotenv()

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = "claude-haiku-4-5-20251001"   # kører efter hvert job — hurtig og billig

OK      = "ok"
WARNING = "warning"
ERROR   = "error"
SKIPPED = "skipped"

LOG_EXCERPT_CHARS = 3000

# Mønstre der gør en kørsel til en fejl, uanset exitkode. Agenterne fanger
# selv de fleste undtagelser og fortsætter — derfor kan en traceback udmærket
# ende i en kørsel, der formelt gik godt.
HARD_FAIL = [
    re.compile(p, re.I) for p in (
        r"traceback \(most recent call last\)",
        r"\[db fejl",
        r"\[api fejl",
        r"FEJL: .*mangler i \.env",
    )
]


def snapshot(race_slug: str | None, covers: list[str]) -> dict:
    """Status for netop de tjek, jobbet skulle udbedre. Uden løb (globale job)
    findes der ikke noget at måle på."""
    if not race_slug or not covers:
        return {}
    data = race_completeness(race_slug)
    if not data:
        return {}
    return {c["key"]: {"status": c["status"], "detail": c["detail"]}
            for c in data["checks"] if c["key"] in covers}


def _deterministic(exit_code: int, log: str, before: dict, after: dict) -> tuple[str, str]:
    """Den dom, vi kan fælde uden en model. Returnerer (dom, begrundelse)."""
    if exit_code != 0:
        return ERROR, f"Kørslen fejlede med exitkode {exit_code}."

    for pattern in HARD_FAIL:
        if pattern.search(log):
            return ERROR, "Kørslen gik formelt godt, men loggen indeholder en fejl."

    if not after:
        return OK, "Kørslen gennemført."

    still_missing = [k for k, v in after.items() if v["status"] == "mangler"]
    improved = [k for k in after
                if before.get(k, {}).get("status") == "mangler"
                and after[k]["status"] == "ok"]

    if still_missing and not improved:
        return WARNING, ("Kørslen gik godt, men der mangler stadig data: "
                         + "; ".join(after[k]["detail"] for k in still_missing))
    if still_missing:
        return WARNING, ("Noget blev hentet, men der mangler stadig: "
                         + "; ".join(after[k]["detail"] for k in still_missing))
    return OK, "Alt det, jobbet skulle hente, er på plads."


SYSTEM = (
    "Du kontrollerer datakørsler for klassementet.dk, en dansk cykelportal. "
    "Du får en agents log og en før/efter-status for de data, den skulle hente. "
    "Din opgave er at afgøre, om den hentede det rigtige — ikke om den undlod at krasje. "
    "En kørsel, der slutter uden fejl men gemmer nul rækker, er en advarsel, ikke en succes. "
    "Svar i præcis to linjer:\n"
    "DOM: ok | advarsel | fejl\n"
    "NOTE: én sætning på dansk, der siger hvad der skete, og hvad ejeren bør gøre. "
    "Vær konkret og nøgtern. Gentag ikke loggen."
)

VERDICT_MAP = {"ok": OK, "advarsel": WARNING, "fejl": ERROR}


def _ask_claude(job: dict, race_slug: str | None, exit_code: int, log: str,
                before: dict, after: dict, floor: str) -> tuple[str, str] | None:
    if not ANTHROPIC_KEY:
        return None
    try:
        from anthropic import Anthropic
    except ImportError:
        return None

    def fmt(snap: dict) -> str:
        return "\n".join(f"  {k}: {v['status']} — {v['detail']}"
                         for k, v in snap.items()) or "  (ikke relevant for dette job)"

    prompt = f"""Job: {job['label']} ({job['key']})
Beskrivelse: {job['description']}
Løb: {race_slug or 'ikke løbsspecifikt'}
Exitkode: {exit_code}

Status FØR kørslen:
{fmt(before)}

Status EFTER kørslen:
{fmt(after)}

Sidste del af loggen:
{log[-LOG_EXCERPT_CHARS:]}"""

    try:
        client = Anthropic(api_key=ANTHROPIC_KEY)
        resp = client.messages.create(
            model=MODEL, max_tokens=300, system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text = next((b.text for b in resp.content
                     if getattr(b, "type", None) == "text"), "")
    except Exception:
        return None

    verdict, note = None, None
    for line in text.strip().splitlines():
        low = line.strip().lower()
        if low.startswith("dom:"):
            verdict = VERDICT_MAP.get(low.split(":", 1)[1].strip())
        elif low.startswith("note:"):
            note = line.split(":", 1)[1].strip()
    if not verdict or not note:
        return None

    # Modellen må gerne skærpe dommen, men aldrig blødgøre den: en traceback
    # eller en exitkode != 0 er en fejl, uanset hvor pænt loggen ser ud.
    order = {OK: 0, WARNING: 1, ERROR: 2}
    if order[verdict] < order[floor]:
        verdict = floor
    return verdict, note


def validate_run(job_key: str, race_slug: str | None, exit_code: int,
                 log: str, before: dict) -> tuple[str, str]:
    """Returnerer (dom, note) til agent_runs.validation_verdict/-note."""
    job = agent_catalog.JOBS.get(job_key)
    if not job:
        return SKIPPED, "Ukendt job — ingen validering."

    after = snapshot(race_slug, job["covers"])
    floor, reason = _deterministic(exit_code, log, before, after)

    judged = _ask_claude(job, race_slug, exit_code, log, before, after, floor)
    if judged:
        return judged
    return floor, reason


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Brug: python run_validator.py <job_key> <løbs-slug>")
        sys.exit(1)
    key, slug = sys.argv[1], sys.argv[2]
    snap = snapshot(slug, agent_catalog.JOBS[key]["covers"])
    print(f"Øjebliksbillede for {key} / {slug}:")
    for k, v in snap.items():
        print(f"  {k}: {v['status']} — {v['detail']}")
