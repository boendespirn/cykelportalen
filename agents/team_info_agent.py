"""
team_info_agent.py
Genererer danske holdbeskrivelser og historik for alle professionelle hold
via Claude API og gemmer i teams.description og teams.history_text.

Kør: python team_info_agent.py
     python team_info_agent.py --slug team-visma-lease-a-bike
"""

import os, sys, io, json, time, argparse, requests
from dotenv import load_dotenv
import anthropic

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")

SB_AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
SB_HEADERS = {**SB_AUTH, "Content-Type": "application/json", "Prefer": "return=minimal"}

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

BATCH_SIZE = 10


def get_teams(slug: str | None = None) -> list[dict]:
    url = f"{SUPABASE_URL}/rest/v1/teams?select=slug,name,country_code,founded_year"
    if slug:
        url += f"&slug=eq.{slug}"
    url += "&order=name.asc"
    res = requests.get(url, headers=SB_AUTH)
    return res.json() if res.ok else []


def update_team(slug: str, description: str, history_text: str) -> bool:
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/teams?slug=eq.{slug}",
        json={"description": description, "history_text": history_text},
        headers=SB_HEADERS,
    )
    return res.ok


def generate_descriptions(teams: list[dict]) -> list[dict]:
    team_list = "\n".join(
        f"- {t['name']}"
        + (f" ({t['country_code']})" if t.get("country_code") else "")
        + (f", grundlagt {t['founded_year']}" if t.get("founded_year") else "")
        for t in teams
    )

    prompt = f"""Du er redaktør på en dansk cykelportal. For hvert hold nedenfor skal du skrive to korte danske sætninger:
1. "description": 1 sætning om holdet i dag — hvem er de primære ryttere, hvad er holdets styrke (klatrere, sprintere, klassiker-ryttere osv.)
2. "history_text": 1 sætning om holdets historie — hvornår grundlagt, vigtigste sejre eller udvikling

Svar KUN med et JSON-array i dette format:
[
  {{"slug": "team-slug", "description": "...", "history_text": "..."}},
  ...
]

Hold:
{team_list}

Slugs til reference:
{json.dumps({t['name']: t['slug'] for t in teams}, ensure_ascii=False)}
"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()
    # Udtræk JSON-array fra responsen
    start = text.find("[")
    end = text.rfind("]") + 1
    if start == -1 or end == 0:
        print(f"  FEJL: Kunne ikke parse JSON fra svar")
        return []
    return json.loads(text[start:end])


def proofread_descriptions(results: list[dict]) -> list[dict]:
    """Selvstændigt korrekturtrin (jf. OPT-004): retter danske sprogfejl —
    manglende mellemrum, manglende bøjning (fx "verdens" i stedet for "verden"),
    ufuldstændige sætninger — i de allerede genererede tekster, før de skrives til DB.
    Fejler korrekturtrinnet, bruges de ukorrigerede tekster i stedet (aldrig blokerende)."""
    if not results:
        return results

    prompt = f"""Du er korrekturlæser på en dansk cykelportal. Gennemgå hvert hold nedenfor og ret
eventuelle danske sprogfejl i "description" og "history_text" — manglende mellemrum, manglende
bøjning (fx genitiv-s), ufuldstændige eller afbrudte sætninger. Bevar betydning og omtrentlig længde.
Er en tekst allerede korrekt, returnér den uændret.

Svar KUN med et JSON-array i samme format som input:
{json.dumps(results, ensure_ascii=False)}
"""

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()
        start = text.find("[")
        end = text.rfind("]") + 1
        if start == -1 or end == 0:
            print("  ADVARSEL: korrekturtrin kunne ikke parses — bruger ukorrigerede tekster")
            return results
        corrected = json.loads(text[start:end])
        return corrected if corrected else results
    except Exception as e:
        print(f"  ADVARSEL: korrekturtrin fejlede ({e}) — bruger ukorrigerede tekster")
        return results


def run(slug: str | None = None) -> None:
    teams = get_teams(slug)
    if not teams:
        print("Ingen hold fundet.")
        return

    print(f"{len(teams)} hold fundet\n")

    # Behandl i batches
    for i in range(0, len(teams), BATCH_SIZE):
        batch = teams[i:i + BATCH_SIZE]
        print(f"Batch {i // BATCH_SIZE + 1}: {', '.join(t['name'] for t in batch)}")

        try:
            results = generate_descriptions(batch)
        except Exception as e:
            print(f"  FEJL ved API-kald: {e}")
            time.sleep(2)
            continue

        results = proofread_descriptions(results)

        for r in results:
            team_slug = r.get("slug", "")
            description = r.get("description", "")
            history = r.get("history_text", "")
            if not team_slug or not description:
                continue
            if update_team(team_slug, description, history):
                print(f"  ✓ {team_slug}")
            else:
                print(f"  ✗ {team_slug} (DB-fejl)")

        if i + BATCH_SIZE < len(teams):
            time.sleep(1)

    print("\nFærdig!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", default=None, help="Hold-slug, udelad for alle hold")
    args = parser.parse_args()
    run(args.slug)
