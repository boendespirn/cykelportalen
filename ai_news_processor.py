"""
ai_news_processor.py
Behandler råartikler fra raw_news med OpenAI:
  1. Scorer relevans for danske cykelfans (1-10)
  2. Omskriver top-artikler til dansk med interne links
  3. Gemmer i news_articles

Krav: OPENAI_API_KEY i .env

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
from openai import OpenAI
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
OPENAI_KEY   = os.getenv("OPENAI_API_KEY")

DB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

MODEL            = "gpt-4o-mini"
MIN_SCORE        = 6      # artikler under denne score springes over
MAX_ARTICLES     = 20     # max artikler per kørsel (cost-kontrol)
DELAY            = 1.0    # sekunder mellem API-kald

# ── Løb der linkes til internt (opdateres automatisk fra DB) ─────────────────

def get_active_races() -> list[dict]:
    """Henter igangværende og kommende løb til interne links."""
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?select=name,slug&order=start_date.desc&limit=30",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
    )
    return res.json() if res.ok else []


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


# ── OpenAI ────────────────────────────────────────────────────────────────────

SCORE_SYSTEM = (
    "Du vurderer relevans af cykelartikler for danske UCI WorldTour-fans. "
    "Svar KUN med et heltal 1-10. Ingen anden tekst."
)

REWRITE_SYSTEM = """Du skriver cykel-nyheder til klassementet.dk — en dansk portal for UCI WorldTour-fans.

Regler:
- Skriv altid på korrekt, engageret dansk (sportsmedie-tone)
- Omskriv originalen — aldrig direkte oversæt
- Tilføj interne links med Markdown: [Giro d'Italia 2026](/giro-ditalia-2026) hvis løbet nævnes
- SEO: inkluder de vigtigste søgeord naturligt i teksten
- Svar KUN med ren JSON — ingen markdown-blokke"""


def score_article(client: OpenAI, article: dict) -> float:
    prompt = (
        f"Titel: {article['title']}\n"
        f"Kilde: {article['source']}\n"
        f"Resume: {article['excerpt'][:300]}"
    )
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SCORE_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=10,
            temperature=0,
        )
        raw = resp.choices[0].message.content.strip()
        # Udtræk første tal fra svaret (håndterer "7", "7/10", "Score: 8" osv.)
        m = re.search(r"\b(\d+(?:\.\d+)?)\b", raw)
        if m:
            val = float(m.group(1))
            # Normaliser hvis modellen svarede på 0-100 skala
            if val > 10:
                val = val / 10
            return min(val, 10.0)
        return 5.0  # fallback: behandl som middel
    except Exception as e:
        print(f" [score fejl: {e}]", end="")
        return 5.0


def rewrite_article(client: OpenAI, article: dict, races: list[dict]) -> dict | None:
    race_list = "\n".join(f"- {r['name']}: /{r['slug']}" for r in races[:15])
    prompt = f"""Omskriv denne cykelartikel til dansk for klassementet.dk.

Original titel: {article['title']}
Kilde: {article['source']}
Indhold:
{article['content'][:3000]}

Interne links der må bruges (kun hvis løbet nævnes i artiklen):
{race_list}

Returner præcis dette JSON:
{{
  "title": "Dansk titel (SEO-optimeret, max 70 tegn)",
  "excerpt": "Kort resume på dansk (max 160 tegn, bruges som meta-description)",
  "content": "Fuld artikel på dansk (300-600 ord). Brug \\n\\n mellem afsnit. Tilføj interne links med Markdown der hvor de passer naturligt.",
  "category": "resultater|startliste|transfer|profil|analyse|generelt"
}}"""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": REWRITE_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=1200,
            temperature=0.7,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"  [REWRITE FEJL] {e}")
        return None


# ── Hoved ─────────────────────────────────────────────────────────────────────

def run(limit: int) -> None:
    if not OPENAI_KEY or OPENAI_KEY == "din-nøgle-her":
        print("FEJL: OPENAI_API_KEY mangler i .env")
        print("Hent nøgle på: https://platform.openai.com/api-keys")
        sys.exit(1)

    client = OpenAI(api_key=OPENAI_KEY)
    articles = get_unprocessed(limit)
    races    = get_active_races()

    print(f"ai_news_processor.py — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Fandt {len(articles)} ubehandlede artikler | {len(races)} løb til interne links\n")

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

        print(" — omskriver...")

        # Trin 2: Omskrivning
        result = rewrite_article(client, art, races)
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
