"""
ai_news_processor.py
Behandler råartikler fra raw_news med Claude (Anthropic API):
  1. Scorer relevans for danske cykelfans (1-10)
  2. Omskriver top-artikler til dansk med interne links
  3. Gemmer i news_articles

Krav: ANTHROPIC_API_KEY i .env

Kør: python ai_news_processor.py
     python ai_news_processor.py --limit 5   (behandl max 5 artikler)

Sæt op i Windows Task Scheduler til at køre efter rss_news_scraper.py.
"""

import os
import sys
import io
import re
import json
import time
import argparse
import requests
from datetime import datetime, timezone
from anthropic import Anthropic
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL   = os.getenv("SUPABASE_URL")
SUPABASE_KEY   = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
ANTHROPIC_KEY  = os.getenv("ANTHROPIC_API_KEY")

DB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

MODEL            = "claude-haiku-4-5-20251001"  # hurtig og billig; skift til claude-sonnet-4-6 for højere kvalitet
MIN_SCORE        = 8      # kun tophistorier publiceres (8-10)
WEEKLY_LIMIT     = 4      # max 4 AI-artikler per uge
MAX_ARTICLES     = 15     # max artikler der scores per kørsel
DELAY            = 0.5    # sekunder mellem API-kald

# ── Løb der linkes til internt (opdateres automatisk fra DB) ─────────────────

def get_active_races() -> list[dict]:
    """Henter igangværende og kommende løb til interne links."""
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?select=name,slug&order=start_date.desc&limit=30",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
    )
    return res.json() if res.ok else []


def get_ongoing_startlists() -> str:
    """
    Returnerer en tekstliste over ryttere i igangværende løb.
    Bruges til faktuel krydsreference — AI må ikke nævne ryttere der IKKE er på listen.
    """
    from datetime import date
    today = date.today().isoformat()

    # Find igangværende løb
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races"
        f"?start_date=lte.{today}&end_date=gte.{today}"
        f"&select=id,name,slug&limit=3",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
    )
    if not res.ok or not res.json():
        return ""

    lines = []
    for race in res.json():
        # Hent startliste
        sl = requests.get(
            f"{SUPABASE_URL}/rest/v1/startlists"
            f"?race_id=eq.{race['id']}"
            f"&select=riders(name,nationality)&status=neq.DNF&limit=250",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
        )
        if not sl.ok:
            continue
        names = [
            e["riders"]["name"]
            for e in sl.json()
            if e.get("riders") and e["riders"].get("name")
        ]
        if names:
            lines.append(f"{race['name']} ({race['slug']}) startliste:")
            lines.append(", ".join(sorted(names)))
            lines.append("")

    return "\n".join(lines)


def get_weekly_published_count() -> int:
    """Returnerer antal AI-artikler publiceret denne uge (siden mandag 00:00)."""
    from datetime import date, timedelta
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/news_articles"
        f"?author=eq.Klassementet AI"
        f"&published_at=gte.{monday.isoformat()}"
        f"&select=id",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
    )
    return len(res.json()) if res.ok else 0


# ── Database ──────────────────────────────────────────────────────────────────

def get_unprocessed(limit: int) -> list[dict]:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/raw_news"
        f"?processed=eq.false&order=published_at.desc&limit={limit}",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
    )
    res.raise_for_status()
    return res.json()


def mark_processed(article_id: str, score: float) -> None:
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/raw_news?id=eq.{article_id}",
        json={"processed": True, "relevance_score": score},
        headers=DB_HEADERS,
    )


def slug_from_title(title: str) -> str:
    from datetime import date
    s = title.lower()
    s = re.sub(r"[æ]", "ae", s); s = re.sub(r"[ø]", "oe", s); s = re.sub(r"[å]", "aa", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return f"{s[:60]}-{date.today().strftime('%Y%m%d')}"


def save_article(data: dict) -> bool:
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/news_articles",
        json=data,
        headers={**DB_HEADERS, "Prefer": "resolution=ignore-duplicates,return=minimal"},
    )
    if not res.ok:
        print(f"  [DB FEJL] {res.status_code}: {res.text[:200]}")
        return False
    return True


def extract_json(text: str) -> dict:
    """Udtræk JSON fra svar der evt. indeholder markdown-kodeblokke."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


# ── Claude API ────────────────────────────────────────────────────────────────

SCORE_SYSTEM = (
    "Du vurderer relevans af cykelartikler for danske UCI WorldTour-fans. "
    "Svar KUN med et heltal 1-10. Ingen anden tekst."
)

REWRITE_SYSTEM = """Du skriver cykel-nyheder til klassementet.dk — Danmarks bedste kilde til professionel cykling og UCI WorldTour.

Regler:
- Skriv altid på korrekt, engageret dansk (sportsmedie-tone som TV 2 Sport)
- Omskriv originalen grundigt — aldrig direkte oversæt
- Artiklerne skal være fyldestgørende: giv al vigtig information, forklar kontekst og baggrund
- Nævn [klassementet.dk](/) naturligt 1 gang som kilden for cykling og resultater
- Tilføj interne links med Markdown til løb der nævnes (fx [Giro d'Italia 2026](/giro-d-italia-2026))
- Brug SEO-søgeord naturligt: "cykling", "professionel cykling", "cykelresultater", "UCI WorldTour"
- FAKTUEL PRÆCISION: Nævn KUN ryttere i et løb hvis de faktisk er på startlisten. Hvis du er i tvivl, undlad at nævne dem i den løbs-kontekst
- Svar KUN med ren JSON — ingen markdown-blokke, ingen forklaringer"""


def score_article(client: Anthropic, article: dict) -> float:
    prompt = (
        f"Titel: {article['title']}\n"
        f"Kilde: {article['source']}\n"
        f"Resume: {article['excerpt'][:300]}"
    )
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=10,
            system=SCORE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        m = re.search(r"\b(\d+(?:\.\d+)?)\b", raw)
        if m:
            val = float(m.group(1))
            if val > 10:
                val = val / 10
            return min(val, 10.0)
        return 5.0
    except Exception as e:
        print(f" [score fejl: {e}]", end="")
        return 5.0


def rewrite_article(client: Anthropic, article: dict, races: list[dict], startlist_context: str) -> dict | None:
    race_list = "\n".join(f"- {r['name']}: /{r['slug']}" for r in races[:15])
    factcheck_block = f"""
FAKTUEL KRYDSREFERENCE — igangværende løb og deres startlister:
{startlist_context}

Vigtigt: Hvis artiklen nævner en rytter i forbindelse med et igangværende løb, men rytterens navn IKKE fremgår af startlisten ovenfor, må du IKKE skrive at rytteren deltager i det løb. Fjern eller korriger sådanne påstande.
""" if startlist_context else ""

    prompt = f"""Omskriv denne cykelartikel til dansk for klassementet.dk.

Original titel: {article['title']}
Kilde: {article['source']}
Indhold:
{article['content'][:3000]}
{factcheck_block}
Interne links der må bruges (kun hvis løbet nævnes i artiklen):
{race_list}

Returner præcis dette JSON:
{{
  "title": "Dansk titel (SEO-optimeret, max 70 tegn)",
  "excerpt": "Kort resume på dansk (max 160 tegn, bruges som meta-description)",
  "content": "Fuld artikel på dansk (600-900 ord). Brug \\n\\n mellem afsnit. Dæk emnet grundigt: baggrund, context, citater, hvad det betyder fremadrettet. Tilføj interne links med Markdown der hvor de passer naturligt.",
  "category": "resultater|startliste|transfer|profil|analyse|generelt"
}}"""

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1200,
            system=REWRITE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        return extract_json(resp.content[0].text)
    except Exception as e:
        print(f"  [REWRITE FEJL] {e}")
        return None


# ── Hoved ─────────────────────────────────────────────────────────────────────

def run(limit: int) -> None:
    if not ANTHROPIC_KEY:
        print("FEJL: ANTHROPIC_API_KEY mangler i .env")
        print("Hent nøgle på: https://console.anthropic.com/settings/keys")
        sys.exit(1)

    client            = Anthropic(api_key=ANTHROPIC_KEY)
    articles          = get_unprocessed(limit)
    races             = get_active_races()
    startlist_context = get_ongoing_startlists()

    weekly_count = get_weekly_published_count()
    slots_left   = max(0, WEEKLY_LIMIT - weekly_count)

    print(f"ai_news_processor.py — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Fandt {len(articles)} ubehandlede artikler | {len(races)} løb til interne links")
    print(f"Denne uge: {weekly_count}/{WEEKLY_LIMIT} artikler publiceret ({slots_left} pladser tilbage)\n")

    if slots_left == 0:
        print("Ugens kvote på 4 artikler er nået — springer over.")
        # Marker alligevel alle som processed så de ikke hober sig op
        for art in articles:
            mark_processed(art["id"], 0.0)
        return

    published = skipped = failed = 0

    for i, art in enumerate(articles, 1):
        print(f"[{i}/{len(articles)}] {art['title'][:70]}")

        # Trin 1: Relevans-scoring
        score = score_article(client, art)
        print(f"  Score: {score:.0f}/10", end="")

        if score < MIN_SCORE:
            print(" — for lav, springer over")
            mark_processed(art["id"], score)
            skipped += 1
            time.sleep(DELAY)
            continue

        if published >= slots_left:
            print(" — ugens kvote opbrugt, stopper")
            mark_processed(art["id"], score)
            # Marker resten som processed
            for remaining in articles[i:]:
                mark_processed(remaining["id"], 0.0)
            break

        print(" — omskriver...")

        # Trin 2: Omskrivning
        result = rewrite_article(client, art, races, startlist_context)
        if not result or not result.get("title") or not result.get("content"):
            print("  -> FEJL ved omskrivning")
            mark_processed(art["id"], score)
            failed += 1
            time.sleep(DELAY)
            continue

        # Trin 3: Gem i news_articles
        slug = slug_from_title(result["title"])
        saved = save_article({
            "slug":             slug,
            "title":            result["title"],
            "excerpt":          result.get("excerpt", ""),
            "content":          result["content"],
            "meta_description": result.get("excerpt", "")[:160],
            "category":         result.get("category", "generelt"),
            "author":           "Klassementet AI",
            "source_url":       art["external_url"],
            "is_advertorial":   False,
            "published_at":     datetime.now(timezone.utc).isoformat(),
        })

        mark_processed(art["id"], score)

        if saved:
            print(f"  -> Publiceret: /nyheder/{slug}")
            published += 1
        else:
            failed += 1

        time.sleep(DELAY)

    print(f"\nFærdig: {published} publiceret, {skipped} sprunget over, {failed} fejl")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=MAX_ARTICLES,
                        help=f"Max artikler per kørsel (default: {MAX_ARTICLES})")
    args = parser.parse_args()
    run(args.limit)
