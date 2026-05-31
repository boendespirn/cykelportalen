"""
race_description_agent.py
Genererer korte danske faktabokse om UCI WorldTour-løb og gemmer i races.description.

Kør: python race_description_agent.py
     python race_description_agent.py --slug giro-d-italia-2026
"""

import os, io, sys, json, time, argparse, requests
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

BATCH_SIZE = 8


def get_races(slug: str | None = None) -> list[dict]:
    url = f"{SUPABASE_URL}/rest/v1/races?select=slug,name,country_code,start_date,end_date,category"
    if slug:
        url += f"&slug=eq.{slug}"
    else:
        url += '&category=in.("UCI WorldTour","2.UWT","1.UWT","UWT")'
    url += "&order=start_date.asc"
    res = requests.get(url, headers=SB_AUTH)
    return res.json() if res.ok else []


def update_race(slug: str, description: str) -> bool:
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/races?slug=eq.{slug}",
        json={"description": description},
        headers=SB_HEADERS,
    )
    return res.ok


def generate_descriptions(races: list[dict]) -> list[dict]:
    race_list = "\n".join(
        f"- {r['name']} ({r.get('country_code', '?')}, slug: {r['slug']})"
        for r in races
    )

    prompt = f"""Du er redaktør på en dansk cykelportal. For hvert løb nedenfor skal du skrive én dansk sætning (max 120 tegn) der kort fortæller:
- Hvad løbet er (Grand Tour, Monument, etapeløb?)
- Historisk kontekst (stiftet hvornår, berømt for hvad?)
- Evt. særpræg (bjerge, cykelklassiker, publikum)

Eksempler på god stil:
"Verdens hårdeste etapeløb med 21 etaper gennem Italiens smukkeste bjerge — grundlagt i 1909."
"Klassikernes klassiker — pavéstenene i Flandern har skabt de største helte i cykelsporten siden 1913."

Svar KUN med et JSON-array:
[
  {{"slug": "løb-slug", "description": "..."}},
  ...
]

Løb:
{race_list}
"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()
    start = text.find("[")
    end = text.rfind("]") + 1
    if start == -1 or end == 0:
        print(f"  FEJL: Kunne ikke parse JSON")
        return []
    return json.loads(text[start:end])


def run(slug: str | None = None) -> None:
    races = get_races(slug)
    if not races:
        print("Ingen løb fundet.")
        return

    print(f"{len(races)} løb fundet\n")

    for i in range(0, len(races), BATCH_SIZE):
        batch = races[i:i + BATCH_SIZE]
        print(f"Batch {i // BATCH_SIZE + 1}: {', '.join(r['name'] for r in batch)}")

        try:
            results = generate_descriptions(batch)
        except Exception as e:
            print(f"  FEJL: {e}")
            time.sleep(2)
            continue

        for r in results:
            race_slug = r.get("slug", "")
            description = r.get("description", "").strip()
            if not race_slug or not description:
                continue
            if update_race(race_slug, description):
                print(f"  ✓ {race_slug}: {description[:70]}")
            else:
                print(f"  ✗ {race_slug} (DB-fejl)")

        if i + BATCH_SIZE < len(races):
            time.sleep(1)

    print("\nFærdig!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", default=None)
    args = parser.parse_args()
    run(args.slug)
