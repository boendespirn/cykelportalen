"""
race_recap_agent.py
Skriver ét samlet dansk referat af HELE løbets forløb ("race_recap") og gemmer
det på løbet, ikke på en etape.

Hvorfor det ikke bare er endnu et etapereferat: en bruger, der lander på
/la-vuelta-ciclista-a-espana-2026 efter løbet, vil vide hvordan løbet blev
afgjort — hvornår klassementet vendte, hvem der holdt, hvem der brød sammen —
ikke læse 21 enkeltreferater og selv sy historien sammen. Det er præcis dét,
etapereferaterne IKKE kan svare på hver for sig (CLAUDE.md §1).

Kildegrundlag — udelukkende vores egen, allerede verificerede database:
  * stages.stage_recap for hver etape (skrevet af stage_recap_agent.py)
  * etapevinderne fra results
  * de endelige klassementer efter sidste kørte etape
Der hentes intet udefra. Agenten kan derfor ikke opfinde en hændelse, der ikke
allerede står i et referat, vi selv har kontrolleret.

Hvornår den må køre:
  Først når løbet er kørt færdigt (end_date er passeret). Et "samlet referat"
  skrevet midtvejs ville stå på løbssiden og påstå at være hele historien,
  mens de afgørende bjergetaper endnu ikke var kørt — den slags er værre end
  ingen tekst (CLAUDE.md §4). --force omgår kravet, men skriver det i loggen.

Krav:
  - ANTHROPIC_API_KEY i .env

Kør:
  python agents/race_recap_agent.py --race la-vuelta-ciclista-a-espana-2026
  python agents/race_recap_agent.py --race ... --force      (skriv igen / før tid)
  python agents/race_recap_agent.py --race ... --dry-run    (vis, gem ikke)

Re-run er sikkert: uden --force springes et løb med et eksisterende referat over.
"""

import os
import sys
import io
import re
import argparse
from datetime import date, datetime, timezone

import requests
from anthropic import Anthropic
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL  = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY  = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")

READ_HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
DB_HEADERS = {**READ_HEADERS, "Content-Type": "application/json", "Prefer": "return=minimal"}

MODEL = "claude-sonnet-5"   # løbssidens redaktionelle hovedtekst — kvalitet før pris
MAX_TOKENS = 3000

# Under så stor en andel etapereferater er der ikke historie nok til at skrive
# et samlet forløb — så skulle modellen fylde hullerne selv.
MIN_RECAP_ANDEL = 0.8

CLASSIFICATION_NAVNE = {
    "gc":        "Samlet klassement",
    "points":    "Pointkonkurrencen",
    "mountains": "Bjergkonkurrencen",
    "youth":     "Ungdomskonkurrencen",
}


# ── Database ──────────────────────────────────────────────────────────────────

def get_race(slug: str) -> dict | None:
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?slug=eq.{slug}"
        f"&select=id,name,slug,start_date,end_date,race_type,race_recap&limit=1",
        headers=READ_HEADERS, timeout=30,
    )
    data = r.json() if r.ok else []
    return data[0] if data else None


def get_stages(race_id: str) -> list[dict]:
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages?race_id=eq.{race_id}"
        f"&select=id,stage_number,date,distance_km,stage_type,start_location,"
        f"finish_location,elevation_gain_m,stage_recap,data_status"
        f"&order=stage_number.asc&limit=100",
        headers=READ_HEADERS, timeout=30,
    )
    r.raise_for_status()
    return r.json()


def get_stage_winners(race_id: str) -> dict[str, str]:
    """stage_id -> vinderens navn. Ét kald frem for ét pr. etape."""
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/results?race_id=eq.{race_id}&position=eq.1"
        f"&select=stage_id,riders(name)&limit=100",
        headers=READ_HEADERS, timeout=30,
    )
    rows = r.json() if r.ok and isinstance(r.json(), list) else []
    return {row["stage_id"]: (row.get("riders") or {}).get("name")
            for row in rows if row.get("stage_id")}


def get_final_standings(race_id: str, after_stage: int) -> dict[str, list[dict]]:
    """De endelige klassementer, dvs. dem efter den sidst kørte etape."""
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/classifications?race_id=eq.{race_id}"
        f"&after_stage_number=eq.{after_stage}&position=lte.5"
        f"&select=classification_type,position,time_gap_seconds,points,riders(name)"
        f"&order=position.asc&limit=100",
        headers=READ_HEADERS, timeout=30,
    )
    rows = r.json() if r.ok and isinstance(r.json(), list) else []
    ud: dict[str, list[dict]] = {}
    for row in rows:
        ud.setdefault(row["classification_type"], []).append(row)
    return ud


def save_recap(race_id: str, tekst: str) -> bool:
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/races?id=eq.{race_id}",
        json={"race_recap": tekst,
              "race_recap_generated_at": datetime.now(timezone.utc).isoformat()},
        headers=DB_HEADERS, timeout=30,
    )
    if not r.ok:
        print(f"  [DB FEJL] {r.status_code} {r.text[:200]}")
    return r.ok


# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM = (
    "Du skriver den samlede beretning om et cykelløb til klassementet.dk, en dansk "
    "cykelportal. Du får løbets egne etapereferater, etapevindere og de endelige "
    "klassementer, og skal binde dem sammen til ÉN fortælling om, hvordan hele løbet "
    "forløb og blev afgjort.\n"
    "Skriv i datid, i nøgternt dansk cykelkommentator-sprog. Ingen clickbait, ingen "
    "superlativer uden dækning, ingen tomme fyldsætninger.\n"
    "Du funderer dig UDELUKKENDE i de oplyste fakta. Opfind aldrig navne, tal, angreb "
    "eller hændelser, der ikke fremgår af materialet — er du i tvivl, udelad det.\n"
    "Fortæl hvordan løbet udviklede sig: hvem der tog føringen hvornår, hvilke etaper "
    "der flyttede klassementet, hvornår afgørelsen faldt, og hvordan de øvrige "
    "konkurrencer blev vundet. Referér etaper ved nummer, så læseren kan slå dem op. "
    "Gentag ikke hver etape efter tur — vælg det, der afgjorde løbet.\n"
    "Rytternavne skrives 'Fornavn Efternavn'. Klassementerne er hentet fra en kilde, "
    "der skriver 'EFTERNAVN Fornavn' — vend dem om, og bevar accenter og specialtegn "
    "præcis som de står.\n"
    "Længde: 400-600 ord fordelt på 4-6 afsnit adskilt af blanke linjer.\n"
    "Svar KUN med selve teksten i almindelig prosa — ingen overskrift, ingen markdown, "
    "ingen indledning som 'Her er referatet'."
)


def _standings_tekst(standings: dict[str, list[dict]]) -> str:
    if not standings:
        return "(ingen klassementer registreret)"
    dele = []
    for key, navn in CLASSIFICATION_NAVNE.items():
        raekker = standings.get(key)
        if not raekker:
            continue
        linjer = []
        for row in raekker:
            rytter = (row.get("riders") or {}).get("name") or "?"
            if key == "gc" and row.get("time_gap_seconds") is not None:
                gap = int(row["time_gap_seconds"])
                ekstra = " (vinder)" if gap == 0 else f" (+{gap // 60}.{gap % 60:02d})"
            elif row.get("points") is not None:
                ekstra = f" ({int(row['points'])} point)"
            else:
                ekstra = ""
            linjer.append(f"    {row['position']}. {rytter}{ekstra}")
        dele.append(f"  {navn}:\n" + "\n".join(linjer))
    return "\n".join(dele)


def build_prompt(race: dict, stages: list[dict], winners: dict[str, str],
                 standings: dict[str, list[dict]]) -> str:
    blokke = []
    for s in stages:
        if s.get("data_status"):
            blokke.append(f"Etape {s['stage_number']} ({s.get('date')}): AFLYST "
                          f"({s['data_status']}) — indgår ikke i løbets forløb.")
            continue
        rute = " - ".join(x for x in (s.get("start_location"), s.get("finish_location")) if x)
        hoved = f"Etape {s['stage_number']} ({s.get('date')}): {rute}"
        if s.get("distance_km"):
            hoved += f", {s['distance_km']} km"
        if s.get("stage_type"):
            hoved += f", {s['stage_type']}"
        vinder = winners.get(s["id"])
        if vinder:
            hoved += f"\n  Vinder: {vinder}"
        referat = (s.get("stage_recap") or "").strip()
        blokke.append(hoved + (f"\n  Referat: {referat}" if referat
                               else "\n  Referat: (mangler — nævn ikke denne etape)"))

    return (
        f"Løb: {race['name']}\n"
        f"Periode: {race.get('start_date')} til {race.get('end_date')}\n"
        f"Antal etaper: {len(stages)}\n\n"
        f"ENDELIGE KLASSEMENTER:\n{_standings_tekst(standings)}\n\n"
        f"ETAPERNE MED VORES EGNE REFERATER:\n\n" + "\n\n".join(blokke)
    )


def clean(text: str) -> str:
    text = re.sub(r"^\s*```[a-z]*\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    text = text.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1]
    return text.strip()


def call_claude(client: Anthropic, prompt: str) -> str | None:
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS, system=SYSTEM,
            # Ingen temperature: parameteren er udfaset for Claude 5-modellerne
            # og giver HTTP 400.
            messages=[{"role": "user", "content": prompt}],
        )
        # Et afhugget svar er en halv beretning midt i en sætning — den må
        # aldrig nå databasen (CLAUDE.md §6: hellere tomt end forkert).
        if resp.stop_reason == "max_tokens":
            print("  [AFHUGGET] svaret nåede token-loftet — intet skrevet")
            return None
        text = next((b.text for b in resp.content
                     if getattr(b, "type", None) == "text"), "")
        return clean(text) or None
    except Exception as e:
        print(f"  [API FEJL] {e}")
        return None


# ── Hoved ─────────────────────────────────────────────────────────────────────

def run(race_slug: str, force: bool, dry_run: bool) -> int:
    if not dry_run and not ANTHROPIC_KEY:
        print("FEJL: ANTHROPIC_API_KEY mangler i .env")
        return 1

    race = get_race(race_slug)
    if not race:
        print(f"FEJL: løb '{race_slug}' ikke fundet i databasen")
        return 1

    print(f"race_recap_agent — {race['name']}")

    slut = race.get("end_date") or race.get("start_date")
    if slut and slut >= date.today().isoformat():
        if not force:
            print(f"  Løbet er ikke kørt færdigt endnu (slutter {slut}).")
            print("  Et samlet referat skrevet nu ville påstå at være hele historien.")
            print("  Kør igen efter sidste etape, eller brug --force.")
            return 0
        print(f"  [FORCE] løbet slutter først {slut} — skriver alligevel.")

    if race.get("race_recap") and not force:
        print("  Løbet har allerede et samlet referat. Brug --force for at skrive det om.")
        return 0

    stages = get_stages(race["id"])
    if not stages:
        print("  Ingen etaper i databasen — intet at skrive ud fra.")
        return 1

    # "Kørt" er BÅDE ikke-aflyst OG afholdt. Uden datofiltret ville --force midt
    # i et løb regne de kommende etaper med — og så lede efter et klassement
    # efter en etape, der ikke er kørt endnu.
    i_dag = date.today().isoformat()
    koerte = [s for s in stages
              if not s.get("data_status") and s.get("date") and s["date"] <= i_dag]
    med_referat = [s for s in koerte if (s.get("stage_recap") or "").strip()]
    andel = len(med_referat) / len(koerte) if koerte else 0
    print(f"  {len(med_referat)} af {len(koerte)} kørte etaper har et referat ({andel:.0%})")

    if andel < MIN_RECAP_ANDEL:
        uden = [str(s["stage_number"]) for s in koerte
                if not (s.get("stage_recap") or "").strip()]
        print(f"  For få etapereferater til at skrive løbets historie "
              f"(kræver {MIN_RECAP_ANDEL:.0%}).")
        print(f"  Mangler etape: {', '.join(uden)}")
        print("  Kør resultat-jobbet for hele løbet først — det skriver referaterne.")
        return 1

    if not koerte:
        print("  Ingen kørte etaper endnu — intet forløb at fortælle om.")
        return 1

    sidste = max(s["stage_number"] for s in koerte)
    standings = get_final_standings(race["id"], sidste)
    if not standings.get("gc"):
        print(f"  Intet samlet klassement efter etape {sidste} — "
              "kør resultat-jobbet for hele løbet først.")
        return 1

    winners = get_stage_winners(race["id"])
    prompt = build_prompt(race, stages, winners, standings)
    print(f"  Grundlag: {len(prompt)} tegn til modellen")

    if dry_run:
        print("\n--- GRUNDLAG (dry-run, intet gemt) ---\n")
        print(prompt[:4000])
        return 0

    client = Anthropic(api_key=ANTHROPIC_KEY)
    tekst = call_claude(client, prompt)
    if not tekst:
        print("  Intet referat skrevet.")
        return 1

    print(f"\n--- REFERAT ({len(tekst.split())} ord) ---\n")
    print(tekst)
    print()

    if not save_recap(race["id"], tekst):
        return 1
    print(f"  Gemt på {race['slug']}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--race", required=True, help="Løbets DB-slug")
    parser.add_argument("--force", action="store_true",
                        help="Skriv igen, selv om der findes et referat — og selv om "
                             "løbet ikke er kørt færdigt")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true",
                        help="Vis grundlaget, kald ikke modellen, gem ikke")
    args = parser.parse_args()
    sys.exit(run(args.race, args.force, args.dry_run))


if __name__ == "__main__":
    main()
