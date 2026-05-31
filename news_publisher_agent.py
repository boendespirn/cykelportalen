"""
news_publisher_agent.py
Genererer SEO-optimerede nyhedsartikler til Cykelportalen via Claude API.

STATUS: DORMANT — aktiveres ved lancering på officielt domæne.

Triggers (kald denne agent når):
  - Et løb afsluttes (winner, GC, sprint)
  - Dagens etape er kørt (etapevinder, nøglehændelser)
  - Vigtig startliste offentliggøres (stor navne bekræftet)
  - Styrt, opgiver, overraskelse

Krav:
  pip install anthropic python-slugify python-dotenv requests

Miljøvariabler (i .env):
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
  ANTHROPIC_API_KEY  ← tilføjes ved lancering

Kør manuelt:
  python news_publisher_agent.py --race tour-de-france-2026 --type race_report --title "Vingegaard vinder etape 12"
  python news_publisher_agent.py --race giro-d-italia-2026 --type startlist --title "Giro d'Italia 2027: fuld startliste klar"

Kør fra daily_update.py (fremtidigt):
  if is_ongoing and today_stage completed:
      subprocess.run(["python", "news_publisher_agent.py", "--race", slug, "--type", "race_report"])
"""

import os
import sys
import io
import re
import json
import argparse
import requests
from datetime import datetime
from dotenv import load_dotenv

# python-slugify bruges til at generere URL-venlige slugs
try:
    from slugify import slugify
except ImportError:
    def slugify(text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"[^\w\s-]", "", text)
        return re.sub(r"[\s_-]+", "-", text).strip("-")

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")  # Aktiveres ved lancering

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}

# ── Artikel-prompter per kategori ─────────────────────────────────────────────

PROMPTS: dict[str, str] = {
    "race_report": """Du er redaktør på Cykelportalen.dk — en dansk cykelportal.
Skriv en SEO-optimeret nyhedsartikel på dansk om: {title}

Kontekst: {context}

Krav:
- Sprog: Dansk, journalistisk og engagerende
- Længde: 300-500 ord
- Start med det vigtigste (omvendt pyramide)
- Inkluder relevante søgeord naturligt (løbsnavn, vindernavn, etapenummer)
- Afslut med kort udsigt til næste etape/begivenhed
- Output KUN HTML (ingen markdown, ingen preamble):
  <p>...</p><p>...</p> osv.
  Brug <strong> til vigtige navne første gang de nævnes.
  Brug <h2> til max 2 underoverskrifter.
""",

    "startlist": """Du er redaktør på Cykelportalen.dk — en dansk cykelportal.
Skriv en SEO-optimeret artikel på dansk om startlisten til: {title}

Kontekst: {context}

Krav:
- Sprog: Dansk, entusiastisk men faktabaseret
- Længde: 250-400 ord
- Fremhæv de største navne og deres chances
- Nævn danske ryttere hvis de deltager
- Beskriv hvad der gør dette løb interessant i år
- Output KUN HTML (<p>, <strong>, <h2>):
""",

    "general": """Du er redaktør på Cykelportalen.dk — en dansk cykelportal.
Skriv en kort SEO-optimeret nyhedsartikel på dansk om: {title}

Kontekst: {context}

Krav:
- Sprog: Dansk
- Længde: 200-350 ord
- Faktabaseret og engagerende
- Output KUN HTML (<p>, <strong>):
""",
}

META_PROMPT = """Generer en meta-description på dansk (max 155 tegn) til denne artikel:
Titel: {title}
Kort resume: {excerpt}
Output kun meta-description teksten, intet andet."""

EXCERPT_PROMPT = """Skriv en kort ingress (max 2 sætninger, 150 tegn) på dansk til:
{title}

Output kun ingressen, intet andet."""


# ── Billede-søgning ───────────────────────────────────────────────────────────

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
FREE_LICENSES = {"cc-by", "cc-by-sa", "cc0", "public domain", "cc-by-2.0", "cc-by-sa-4.0", "cc-by-4.0"}

def search_wikimedia(query: str) -> str | None:
    """Søger Wikimedia Commons efter et CC-licenseret cykelbillede."""
    try:
        params = {
            "action": "query",
            "list": "search",
            "srsearch": f"{query} cycling",
            "srnamespace": "6",  # Kun filer
            "srlimit": "5",
            "format": "json",
        }
        res = requests.get(WIKIMEDIA_API, params=params, timeout=10)
        if not res.ok:
            return None
        results = res.json().get("query", {}).get("search", [])
        for r in results:
            title = r.get("title", "")
            if not title.startswith("File:"):
                continue
            # Hent billedinfo incl. licens
            info_res = requests.get(WIKIMEDIA_API, params={
                "action": "query",
                "titles": title,
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "format": "json",
            }, timeout=10)
            if not info_res.ok:
                continue
            pages = info_res.json().get("query", {}).get("pages", {})
            for page in pages.values():
                ii = page.get("imageinfo", [{}])[0]
                license_str = ii.get("extmetadata", {}).get("LicenseShortName", {}).get("value", "").lower()
                if any(lic in license_str for lic in FREE_LICENSES):
                    url = ii.get("url", "")
                    if url and any(url.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")):
                        return url
    except Exception:
        pass
    return None


def find_article_image(title: str) -> tuple[str | None, str | None]:
    """
    Finder bedste billede til en artikel.
    Prioritet: 1) Wikimedia CC-billede, 2) Rytters PCS-foto
    Returnerer (image_url, rider_id).
    """
    # 1) Wikimedia-søgning på nøgleord fra titlen
    words = [w for w in title.split() if len(w) > 4]
    search_term = " ".join(words[:3])
    wiki_url = search_wikimedia(search_term)
    if wiki_url:
        return wiki_url, None

    # 2) Rider photo fallback — match rytternavne i titlen
    try:
        riders_res = requests.get(
            f"{SUPABASE_URL}/rest/v1/riders?select=id,name,photo_url&photo_url=not.is.null",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            timeout=15,
        )
        if riders_res.ok:
            title_lower = title.lower()
            for rider in riders_res.json():
                parts = rider["name"].lower().split()
                for part in parts:
                    if len(part) > 3 and part in title_lower:
                        return rider["photo_url"], rider["id"]
    except Exception:
        pass

    return None, None


# ── Supabase helpers ──────────────────────────────────────────────────────────

def sb_get(table: str, params: str) -> list:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}?{params}",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
        timeout=15,
    )
    return res.json() if res.ok else []


def sb_upsert(table: str, record: dict, conflict: str) -> bool:
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={conflict}",
        json=[record],
        headers=SUPABASE_HEADERS,
    )
    if not res.ok:
        print(f"  [DB FEJL] {res.status_code}: {res.text[:300]}")
    return res.ok


# ── Claude API wrapper ────────────────────────────────────────────────────────

def call_claude(prompt: str, max_tokens: int = 1000) -> str:
    """Kalder Claude claude-sonnet-4-6 via Anthropic Messages API."""
    if not ANTHROPIC_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY ikke sat — aktivér ved lancering")

    res = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    if not res.ok:
        raise RuntimeError(f"Claude API fejl: {res.status_code} — {res.text[:200]}")

    return res.json()["content"][0]["text"].strip()


# ── Kontekst-builder ──────────────────────────────────────────────────────────

def build_context(race_slug: str, article_type: str) -> str:
    """Henter relevant data fra DB til at berige prompten med kontekst."""
    parts = []

    # Løb-info
    race_rows = sb_get("races", f"slug=eq.{race_slug}&select=name,start_date,end_date,category&limit=1")
    if race_rows:
        r = race_rows[0]
        parts.append(f"Løb: {r['name']} ({r.get('category','')}) — {r.get('start_date','')} til {r.get('end_date','')}")

    # Startliste (top kaptajner)
    if article_type in ("startlist", "race_report"):
        captains = sb_get(
            "startlists",
            f"race_id=eq.(SELECT id FROM races WHERE slug='{race_slug}')&is_gc_captain=eq.true"
            f"&select=riders(name,nationality,speciality),teams(name)&limit=10",
        )
        if captains:
            names = [f"{e['riders']['name']} ({e['teams']['name']})" for e in captains if e.get('riders') and e.get('teams')]
            if names:
                parts.append("GC-favoritter: " + ", ".join(names))

    return "\n".join(parts) if parts else "Ingen yderligere kontekst tilgængelig."


# ── Hoved ─────────────────────────────────────────────────────────────────────

def generate_article(
    title: str,
    race_slug: str | None = None,
    article_type: str = "general",
    is_advertorial: bool = False,
    author: str = "Cykelportalen",
) -> dict | None:
    """
    Genererer én artikel og returnerer DB-record klar til upsert.
    Returnerer None hvis ANTHROPIC_KEY ikke er sat.
    """
    if not ANTHROPIC_KEY:
        print("  [DORMANT] ANTHROPIC_API_KEY ikke sat — springer over")
        return None

    print(f"  Genererer artikel: {title}")

    # Opbyg kontekst
    context = build_context(race_slug, article_type) if race_slug else "Ingen specifik kontekst."

    # Generér indhold
    template = PROMPTS.get(article_type, PROMPTS["general"])
    content_html = call_claude(template.format(title=title, context=context), max_tokens=1200)

    # Generér excerpt og meta
    excerpt = call_claude(EXCERPT_PROMPT.format(title=title), max_tokens=100)
    meta = call_claude(META_PROMPT.format(title=title, excerpt=excerpt), max_tokens=60)

    # Find race_id hvis slug er givet
    race_id = None
    if race_slug:
        rows = sb_get("races", f"slug=eq.{race_slug}&select=id&limit=1")
        race_id = rows[0]["id"] if rows else None

    # Find billede — Wikimedia CC eller rytter-foto
    image_url, rider_id = find_article_image(title)
    if image_url:
        print(f"  Billede: {image_url[:70]}...")

    slug_base = slugify(title)
    timestamp = datetime.now().strftime("%Y%m%d")
    article_slug = f"{slug_base}-{timestamp}"

    return {
        "slug":             article_slug,
        "title":            title,
        "excerpt":          excerpt[:200],
        "content":          content_html,
        "meta_description": meta[:155],
        "category":         article_type,
        "author":           author,
        "race_id":          race_id,
        "rider_id":         rider_id,
        "image_url":        image_url,
        "is_advertorial":   is_advertorial,
        "published_at":     datetime.utcnow().isoformat() + "Z",
    }


def run(title: str, race_slug: str | None, article_type: str, is_advertorial: bool, author: str):
    print(f"\n=== news_publisher_agent.py ===")
    print(f"Titel: {title}")
    print(f"Type:  {article_type}")
    print(f"Løb:   {race_slug or '—'}")

    if not ANTHROPIC_KEY:
        print("\n  [DORMANT] Agenten er ikke aktiveret endnu.")
        print("  Tilføj ANTHROPIC_API_KEY til .env for at aktivere.")
        return

    record = generate_article(title, race_slug, article_type, is_advertorial, author)
    if not record:
        return

    ok = sb_upsert("news_articles", record, "slug")
    if ok:
        print(f"\n  Artikel publiceret: /nyheder/{record['slug']}")
    else:
        print("\n  DB-fejl ved publicering")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generér og publicér nyhedsartikel")
    parser.add_argument("--title",         required=True,  help="Artiklens overskrift")
    parser.add_argument("--race",          default=None,   help="DB-løbets slug (fx tour-de-france-2026)")
    parser.add_argument("--type",          default="general",
                        choices=["race_report", "startlist", "general", "interview", "analysis"],
                        help="Artikelkategori")
    parser.add_argument("--advertorial",   action="store_true", help="Marker som sponsoreret indhold")
    parser.add_argument("--author",        default="Cykelportalen", help="Forfatter")
    args = parser.parse_args()

    run(
        title=args.title,
        race_slug=args.race,
        article_type=args.type,
        is_advertorial=args.advertorial,
        author=args.author,
    )
