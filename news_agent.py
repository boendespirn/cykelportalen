"""
news_agent.py
Henter cykelnyheder fra RSS-feeds og gemmer dem i Supabase.
Tagger artikler til løb baseret på keyword-matching mod løbsnavne i DB.

Krav: pip install feedparser requests python-dotenv
Kør: python news_agent.py
"""

import os
import re
import sys
import io
import requests
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}

# ── RSS-feeds ─────────────────────────────────────────────────────────────────

RSS_FEEDS = [
    {"url": "https://www.cyclingnews.com/rss/",           "source": "CyclingNews"},
    {"url": "https://www.velonews.com/feed/",              "source": "VeloNews"},
    {"url": "https://inrng.com/feed/",                     "source": "INRNG"},
    {"url": "https://www.cyclingweekly.com/feed",          "source": "Cycling Weekly"},
    {"url": "https://www.procyclingnews.com/rss.xml",      "source": "ProCyclingNews"},
    {"url": "https://www.wielerflits.nl/rss/nieuws/",      "source": "Wielerflits"},
]

# Nøgleord → PCS base-slug (uden årstal) for matching mod løbsnavne
# Bruges til at finde race_id i DB
RACE_KEYWORDS: dict[str, str] = {
    "tour de france":          "tour-de-france",
    "le tour":                 "tour-de-france",
    " tdf ":                   "tour-de-france",
    "giro d'italia":           "giro-d-italia",
    "giro d’italia":      "giro-d-italia",
    " giro ":                  "giro-d-italia",
    "the giro":                "giro-d-italia",
    "vuelta a españa":    "la-vuelta-ciclista-a-espana",
    "la vuelta":               "la-vuelta-ciclista-a-espana",
    "paris-roubaix":           "paris-roubaix",
    "paris roubaix":           "paris-roubaix",
    "tour de suisse":          "tour-de-suisse",
    "tour of switzerland":     "tour-de-suisse",
    "criterium du dauphiné": "criterium-du-dauphine",
    "critérium du dauphiné": "criterium-du-dauphine",
    "dauphine":                "criterium-du-dauphine",
    "il lombardia":            "il-lombardia",
    "il giro di lombardia":    "il-lombardia",
    "liège-bastogne":     "liege-bastogne-liege",
    "liege-bastogne":          "liege-bastogne-liege",
    "amstel gold":             "amstel-gold-race",
    "strade bianche":          "strade-bianche",
    "tirreno-adriatico":       "tirreno-adriatico",
    "paris-nice":              "paris-nice",
    "tour of flanders":        "ronde-van-vlaanderen",
    "ronde van vlaanderen":    "ronde-van-vlaanderen",
    "la flèche wallonne": "la-fleche-wallonne",
    "fleche wallonne":         "la-fleche-wallonne",
    "e3 saxo":                 "e3-saxo-classic",
    "tour de pologne":         "tour-de-pologne",
    "tour de romandie":        "tour-de-romandie",
    "volta a catalunya":       "volta-ciclista-a-catalunya",
}


# ── Supabase helpers ──────────────────────────────────────────────────────────

def sb_get(table: str, params: str) -> list:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}?{params}",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
        timeout=15,
    )
    return res.json() if res.ok else []


def sb_upsert(table: str, records: list, conflict: str) -> bool:
    if not records:
        return True
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={conflict}",
        json=records,
        headers=SUPABASE_HEADERS,
        timeout=15,
    )
    if not res.ok:
        print(f"  [DB FEJL] {table}: {res.status_code} — {res.text[:300]}")
    return res.ok


# ── Byg race-lookup fra DB ────────────────────────────────────────────────────

def build_race_lookup() -> dict[str, str]:
    """Returnerer dict: pcs-base-slug → race_id fra DB."""
    rows = sb_get("races", "select=id,slug,name&order=start_date.asc")
    lookup: dict[str, str] = {}
    for row in rows:
        slug = row["slug"]
        # Fjern årstal fra slug: "tour-de-france-2026" → "tour-de-france"
        base = re.sub(r"-\d{4}$", "", slug)
        lookup[base] = row["id"]
    return lookup


def match_race(text: str, race_lookup: dict[str, str]) -> str | None:
    """Finder race_id ud fra tekstindhold ved keyword-matching."""
    lower = text.lower()
    for keyword, base_slug in RACE_KEYWORDS.items():
        if keyword in lower:
            race_id = race_lookup.get(base_slug)
            if race_id:
                return race_id
    return None


# ── RSS-parsing ───────────────────────────────────────────────────────────────

def parse_feed(feed_url: str, source_name: str) -> list[dict]:
    """Henter og parser ét RSS-feed. Returnerer liste af artikel-dicts."""
    try:
        import feedparser
    except ImportError:
        print("  feedparser ikke installeret — kør: pip install feedparser")
        return []

    try:
        feed = feedparser.parse(feed_url)
    except Exception as e:
        print(f"  [{source_name}] FEJL ved parsing: {e}")
        return []

    if feed.bozo and not feed.entries:
        print(f"  [{source_name}] Ingen entries (bozo={feed.bozo_exception})")
        return []

    articles = []
    for entry in feed.entries:
        title = entry.get("title", "").strip()
        url   = entry.get("link", "").strip()
        if not title or not url:
            continue

        # Publiceringstidspunkt
        pub_at = None
        for key in ("published", "updated", "created"):
            raw = entry.get(key)
            if raw:
                try:
                    pub_at = parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat()
                    break
                except Exception:
                    try:
                        pub_at = datetime(*entry.get(f"{key}_parsed", [])[:6],
                                          tzinfo=timezone.utc).isoformat()
                        break
                    except Exception:
                        pass

        # Sammendrag — strip HTML-tags
        summary_raw = entry.get("summary", "") or entry.get("description", "") or ""
        summary = re.sub(r"<[^>]+>", " ", summary_raw).strip()
        summary = re.sub(r"\s{2,}", " ", summary)[:500] if summary else None

        articles.append({
            "title":        title,
            "url":          url,
            "source":       source_name,
            "summary":      summary,
            "published_at": pub_at,
        })

    return articles


# ── Hoved ────────────────────────────────────────────────────────────────────

def run():
    print("Bygger løbs-lookup fra DB...")
    race_lookup = build_race_lookup()
    print(f"  {len(race_lookup)} løb i DB")

    total_new = 0

    for feed_info in RSS_FEEDS:
        source = feed_info["source"]
        print(f"\n[{source}] {feed_info['url']}")

        articles = parse_feed(feed_info["url"], source)
        if not articles:
            print(f"  0 artikler")
            continue

        print(f"  {len(articles)} artikler fundet")

        records = []
        for art in articles:
            combined_text = f"{art['title']} {art.get('summary', '') or ''}"
            race_id = match_race(combined_text, race_lookup)

            records.append({
                "title":        art["title"],
                "url":          art["url"],
                "source":       art["source"],
                "summary":      art["summary"],
                "published_at": art["published_at"],
                "race_id":      race_id,
                "tags":         [],
            })

        # Gem i batches af 50 — upsert på url (unique)
        new_count = 0
        for i in range(0, len(records), 50):
            batch = records[i:i + 50]
            res = requests.post(
                f"{SUPABASE_URL}/rest/v1/news_articles?on_conflict=url",
                json=batch,
                headers={**SUPABASE_HEADERS, "Prefer": "resolution=ignore-duplicates,return=representation"},
                timeout=15,
            )
            if res.ok:
                try:
                    new_count += len(res.json())
                except Exception:
                    pass
            else:
                print(f"  [DB FEJL] {res.status_code}: {res.text[:200]}")

        tagged = sum(1 for r in records if r["race_id"])
        print(f"  {new_count} nye gemt | {tagged} tagget til løb")
        total_new += new_count

    print(f"\nFærdig! {total_new} nye artikler i alt.")


if __name__ == "__main__":
    run()
