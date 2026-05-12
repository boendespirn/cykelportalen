"""
news_agent.py
Overvåger RSS-feeds fra cykelmedia og kører automatisk startlist_agent.py
for løb der har nye startliste-omtaler.

Ingen artikler gemmes — feeds bruges udelukkende som trigger.

Krav: pip install feedparser requests python-dotenv
Kør: python news_agent.py
"""

import os
import re
import sys
import io
import asyncio
import subprocess
import requests
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# ── RSS-feeds ─────────────────────────────────────────────────────────────────

RSS_FEEDS = [
    {"url": "https://www.cyclingnews.com/rss/",     "source": "CyclingNews"},
    {"url": "https://www.velonews.com/feed/",        "source": "VeloNews"},
    {"url": "https://inrng.com/feed/",               "source": "INRNG"},
    {"url": "https://www.cyclingweekly.com/feed",    "source": "Cycling Weekly"},
]

# Nøgleord der indikerer en startliste eller holdudtagelse er annonceret
STARTLIST_SIGNALS = [
    "startlist", "start list", "lineup", "line-up",
    "confirmed", "announces", "announced", "selection",
    "team for", "squad for", "starters", "roster",
    "will ride", "set for", "named",
]

# Løbs-keywords → PCS base-slug
RACE_KEYWORDS: dict[str, str] = {
    "tour de france":               "tour-de-france",
    "le tour":                      "tour-de-france",
    "tdf":                          "tour-de-france",
    "giro d'italia":                "giro-d-italia",
    "giro d'italia":           "giro-d-italia",
    " giro ":                       "giro-d-italia",
    "the giro":                     "giro-d-italia",
    "vuelta a españa":         "la-vuelta-ciclista-a-espana",
    "vuelta a espana":              "la-vuelta-ciclista-a-espana",
    "la vuelta":                    "la-vuelta-ciclista-a-espana",
    "paris-roubaix":                "paris-roubaix",
    "paris roubaix":                "paris-roubaix",
    "tour de suisse":               "tour-de-suisse",
    "tour of switzerland":          "tour-de-suisse",
    "criterium du dauphiné":   "criterium-du-dauphine",
    "critérium du dauphiné":   "criterium-du-dauphine",
    "dauphine":                     "criterium-du-dauphine",
    "il lombardia":                 "il-lombardia",
    "liège-bastogne":          "liege-bastogne-liege",
    "liege-bastogne":               "liege-bastogne-liege",
    "amstel gold":                  "amstel-gold-race",
    "strade bianche":               "strade-bianche",
    "tirreno-adriatico":            "tirreno-adriatico",
    "paris-nice":                   "paris-nice",
    "tour of flanders":             "ronde-van-vlaanderen",
    "ronde van vlaanderen":         "ronde-van-vlaanderen",
    "la flèche wallonne":      "la-fleche-wallonne",
    "fleche wallonne":              "la-fleche-wallonne",
    "e3 saxo":                      "e3-saxo-classic",
    "tour de pologne":              "tour-de-pologne",
    "tour de romandie":             "tour-de-romandie",
    "volta a catalunya":            "volta-ciclista-a-catalunya",
}


# ── Supabase helpers ──────────────────────────────────────────────────────────

def sb_get(table: str, params: str) -> list:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}?{params}",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
        timeout=15,
    )
    return res.json() if res.ok else []


def build_race_lookup() -> dict[str, str]:
    """base-slug → vores DB-slug (med årstal)."""
    rows = sb_get("races", "select=id,slug&order=start_date.asc")
    lookup: dict[str, str] = {}
    for row in rows:
        base = re.sub(r"-\d{4}$", "", row["slug"])
        lookup[base] = row["slug"]
    return lookup


# ── RSS-parsing ───────────────────────────────────────────────────────────────

def parse_feed(feed_url: str, source_name: str, max_age_days: int = 2) -> list[dict]:
    """Returnerer artikler der er max max_age_days dage gamle."""
    try:
        import feedparser
    except ImportError:
        print("  feedparser ikke installeret — kør: py -m pip install feedparser")
        return []

    try:
        feed = feedparser.parse(feed_url)
    except Exception as e:
        print(f"  [{source_name}] Fejl: {e}")
        return []

    if not feed.entries:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    articles = []

    for entry in feed.entries:
        title = entry.get("title", "").strip()
        url   = entry.get("link", "").strip()
        if not title or not url:
            continue

        # Tjek alder — spring over gamle artikler
        pub_dt = None
        for key in ("published", "updated"):
            raw = entry.get(key)
            if raw:
                try:
                    pub_dt = parsedate_to_datetime(raw).astimezone(timezone.utc)
                    break
                except Exception:
                    try:
                        pub_dt = datetime(*entry.get(f"{key}_parsed", [])[:6], tzinfo=timezone.utc)
                        break
                    except Exception:
                        pass

        if pub_dt and pub_dt < cutoff:
            continue

        summary_raw = entry.get("summary", "") or entry.get("description", "") or ""
        summary = re.sub(r"<[^>]+>", " ", summary_raw).strip()

        articles.append({
            "title":   title,
            "url":     url,
            "source":  source_name,
            "text":    f"{title} {summary}".lower(),
            "pub_dt":  pub_dt,
        })

    return articles


def detect_race(text: str, race_lookup: dict[str, str]) -> str | None:
    """Finder vores DB-slug ud fra artikeltekst."""
    for keyword, base_slug in RACE_KEYWORDS.items():
        if keyword in text:
            db_slug = race_lookup.get(base_slug)
            if db_slug:
                return db_slug
    return None


def has_startlist_signal(text: str) -> bool:
    return any(kw in text for kw in STARTLIST_SIGNALS)


# ── Hoved ────────────────────────────────────────────────────────────────────

def run():
    print("Bygger løbs-lookup...")
    race_lookup = build_race_lookup()
    print(f"  {len(race_lookup)} løb i DB\n")

    races_to_rescrape: set[str] = set()
    races_mentioned: dict[str, int] = {}  # slug → antal artikler

    for feed_info in RSS_FEEDS:
        source = feed_info["source"]
        print(f"[{source}]")
        articles = parse_feed(feed_info["url"], source, max_age_days=2)

        if not articles:
            print(f"  Ingen nye artikler (seneste 2 dage)\n")
            continue

        print(f"  {len(articles)} nylige artikler")

        for art in articles:
            race_slug = detect_race(art["text"], race_lookup)
            if not race_slug:
                continue

            races_mentioned[race_slug] = races_mentioned.get(race_slug, 0) + 1

            if has_startlist_signal(art["text"]):
                races_to_rescrape.add(race_slug)
                pub_str = art["pub_dt"].strftime("%d/%m") if art["pub_dt"] else "?"
                print(f"  → Startliste-signal [{race_slug}]: {art['title'][:70]} ({pub_str})")

        print()

    # ── Opsummering ──────────────────────────────────────────────────────────

    if races_mentioned:
        print("Løb nævnt i dag:")
        for slug, count in sorted(races_mentioned.items(), key=lambda x: -x[1]):
            signal = " ← STARTLISTE" if slug in races_to_rescrape else ""
            print(f"  {slug}: {count} artikler{signal}")
        print()

    if races_to_rescrape:
        print(f"Kører startlist_agent for {len(races_to_rescrape)} løb...\n")
        # Udtræk PCS base-slug (uden årstal) til startlist_agent
        for db_slug in sorted(races_to_rescrape):
            pcs_slug = re.sub(r"-\d{4}$", "", db_slug)
            print(f"  py startlist_agent.py {pcs_slug}")
            try:
                result = subprocess.run(
                    [sys.executable, "startlist_agent.py", pcs_slug],
                    capture_output=False,
                    timeout=180,
                )
                if result.returncode != 0:
                    print(f"  [FEJL] startlist_agent returnerede {result.returncode}")
            except subprocess.TimeoutExpired:
                print(f"  [TIMEOUT] {pcs_slug}")
            except Exception as e:
                print(f"  [FEJL] {e}")
    else:
        print("Ingen startliste-signaler i dag — ingen scraping nødvendig.")

    print("\nFærdig!")


if __name__ == "__main__":
    run()
