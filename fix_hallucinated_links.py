"""
fix_hallucinated_links.py
Engangs-oprydning for NEWS-001: fjerner hallucinerede interne links
(fx /jonas-vingegaard, /tour-de-france-klassement, /riders/x, /ryttere/x)
fra allerede publicerede artikler i news_articles. Bruger samme
sanitize_links()-logik som ai_news_processor.py's fremadrettede fix.

Kør altid først uden --apply for at se diff. Skriv kun med --apply.

Kør: python fix_hallucinated_links.py            (dry-run, viser diff)
     python fix_hallucinated_links.py --apply     (skriver rettelserne)
"""

import os
import sys
import io
import re
import argparse
import requests
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}


def get_all_race_slugs() -> set[str]:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?select=slug&limit=2000",
        headers=HEADERS,
    )
    res.raise_for_status()
    return {r["slug"] for r in res.json()}


def get_published_articles() -> list[dict]:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/news_articles"
        "?select=id,slug,title,content&status=eq.published&limit=1000",
        headers=HEADERS,
    )
    res.raise_for_status()
    return res.json()


def sanitize_links(content: str, race_slugs: set[str]) -> str:
    def is_allowed(url: str) -> bool:
        if url.startswith("https://klassementet.dk"):
            url = url[len("https://klassementet.dk"):] or "/"
        elif url.startswith("http://") or url.startswith("https://"):
            return True  # ægte ekstern kilde
        if url == "/":
            return True
        m = re.match(r"^/([^/]+)(?:/stage/\d+)?$", url)
        return bool(m) and m.group(1) in race_slugs

    def replace(match: re.Match) -> str:
        text, url = match.group(1), match.group(2)
        return match.group(0) if is_allowed(url) else text

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", replace, content)


def update_article(article_id: str, content: str) -> bool:
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/news_articles?id=eq.{article_id}",
        headers={**HEADERS, "Content-Type": "application/json", "Prefer": "return=minimal"},
        json={"content": content},
    )
    return res.ok


def main(apply: bool) -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("FEJL: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY mangler i .env")
        sys.exit(1)

    race_slugs = get_all_race_slugs()

    articles = get_published_articles()
    print(f"{len(articles)} publicerede artikler hentet, {len(race_slugs)} kendte løbs-slugs")

    changed = 0
    for art in articles:
        original = art["content"] or ""
        fixed = sanitize_links(original, race_slugs)
        if fixed == original:
            continue

        changed += 1
        print(f"\n=== {art['title'][:70]} (/nyheder/{art['slug']}) ===")
        # Vis kun de ændrede linkmål, ikke hele artiklen
        removed = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", original)
        kept = set(re.findall(r"\[([^\]]+)\]\(([^)]+)\)", fixed))
        for text, url in removed:
            if (text, url) not in kept:
                print(f"  fjerner link: [{text}]({url})  ->  \"{text}\"")

        if apply:
            ok = update_article(art["id"], fixed)
            print("  -> gemt" if ok else "  -> FEJL ved skrivning")

    print(f"\n{changed} artikel(er) {'rettet' if apply else 'ville blive rettet (dry-run, brug --apply for at skrive)'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Skriv rettelserne til DB (default: dry-run)")
    args = parser.parse_args()
    main(apply=args.apply)
