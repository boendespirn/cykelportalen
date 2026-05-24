"""
rss_news_scraper.py
Scraper RSS-feeds fra internationale cykelmedier og gemmer råartikler i raw_news.

Kør: python rss_news_scraper.py
Sæt op i Windows Task Scheduler til at køre 4x dagligt (fx kl. 7, 11, 15, 19).
"""

import os
import sys
import io
import re
import html
import time
import requests
import feedparser
from datetime import datetime, timezone
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

DB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

FEEDS = [
    {"source": "CyclingNews",   "url": "https://www.cyclingnews.com/rss/"},
    {"source": "VeloNews",      "url": "https://www.velonews.com/feed/"},
    {"source": "CyclingWeekly", "url": "https://www.cyclingweekly.com/feed"},
    {"source": "INRNG",         "url": "https://inrng.com/feed/"},
    {"source": "BikeRadar",     "url": "https://www.bikeradar.com/feed/"},
]

MAX_PER_FEED = 15
DELAY = 1.5


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text).strip()


def parse_published(entry) -> str | None:
    try:
        t = entry.get("published_parsed") or entry.get("updated_parsed")
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc).isoformat()
    except Exception:
        pass
    return None


def get_content(entry) -> str:
    for c in entry.get("content", []):
        if c.get("value"):
            return strip_html(c["value"])[:4000]
    return strip_html(entry.get("summary", "") or entry.get("description", ""))[:4000]


def upsert_articles(articles: list[dict]) -> int:
    if not articles:
        return 0
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/raw_news",
        json=articles,
        headers={**DB_HEADERS, "Prefer": "resolution=ignore-duplicates,return=minimal"},
    )
    if not res.ok:
        print(f"  [DB FEJL] {res.status_code}: {res.text[:200]}")
        return 0
    return len(articles)


def scrape_feed(cfg: dict) -> list[dict]:
    source = cfg["source"]
    print(f"  {source}...", end=" ", flush=True)
    try:
        parsed = feedparser.parse(cfg["url"])
        articles = []
        for e in parsed.entries[:MAX_PER_FEED]:
            url   = e.get("link", "").strip()
            title = strip_html(e.get("title", "")).strip()
            if not url or not title:
                continue
            articles.append({
                "external_url": url,
                "source":       source,
                "title":        title,
                "excerpt":      strip_html(e.get("summary", ""))[:500],
                "content":      get_content(e),
                "published_at": parse_published(e),
            })
        print(f"{len(articles)} artikler")
        return articles
    except Exception as ex:
        print(f"FEJL: {ex}")
        return []


def run() -> None:
    print(f"rss_news_scraper.py — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    total = 0
    for feed in FEEDS:
        articles = scrape_feed(feed)
        total += upsert_articles(articles)
        time.sleep(DELAY)
    print(f"\nFærdig: {total} artikler gemt i raw_news")


if __name__ == "__main__":
    run()
