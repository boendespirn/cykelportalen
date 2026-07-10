"""
ai_news_processor.py
Behandler råartikler fra raw_news med Claude (Anthropic API):
  1. Scorer relevans for danske cykelfans (1-10) for ALLE kandidater i puljen
  2. Rangerer de kvalificerede kandidater og omskriver kun den/de allerbedste
     til dansk med interne links (max MAX_DRAFTS_PER_RUN, mål er 1 — se
     STRATEGI.md §1: kvalitet frem for mængde, mens vi venter på indeksering)
  3. Gemmer i news_articles som kladde (kræver godkendelse i /admin)

Krav: ANTHROPIC_API_KEY i .env

Kør: python ai_news_processor.py
     python ai_news_processor.py --limit 5          (score max 5 kandidater)
     python ai_news_processor.py --max-drafts 1      (skriv kun den allerbedste)

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

MODEL              = "claude-haiku-4-5-20251001"  # hurtig og billig; skift til claude-sonnet-4-6 for højere kvalitet
MIN_SCORE          = 8      # kun tophistorier scores videre (8-10)
MAX_ARTICLES       = 15     # max artikler der SCORES per kørsel (kandidatpuljen)
MAX_DRAFTS_PER_RUN = 2      # max artikler der rent faktisk SKRIVES per kørsel — målet er 1, se STRATEGI.md §1
DELAY              = 0.5    # sekunder mellem API-kald

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
- LINKS — MAKSIMALT 2 links i hele artiklen:
  1. Ét link til det løb artiklen primært handler om — brug kun løbets navn som ankertekst (fx [Tour de France](/tour-de-france-2026)) og link KUN første gang løbsnavnet nævnes naturligt i brødteksten. Intet årstal i ankerteksten.
  2. Valgfrit: ét link til forsiden [Klassementet](/) hvis der er en naturlig sætning om at følge med på siden — ellers ingen.
  - Gentag ALDRIG samme link. Skriv løbsnavnet plain text alle andre gange det nævnes.
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
  "content": "Fuld artikel på dansk (600-900 ord). Brug \\n\\n mellem afsnit. Dæk emnet grundigt: baggrund, context, citater, hvad det betyder fremadrettet. MAX 2 links: ét til det primære løb (første nævnelse, kun løbsnavn som ankertekst) + evt. ét til forsiden [Klassementet](/). Alle andre nævnelser af løbet skrives som plain text.",
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


def sanitize_links(content: str, races: list[dict]) -> str:
    """Fjerner (til plain text) ethvert INTERNT markdown-link, der ikke peger på
    et kendt løb (evt. dets etapesider), eller forsiden. Ægte eksterne links
    (kilder som uci.org) røres ikke. rewrite_article()s prompt beder Claude om
    kun at bruge løbslinks, men LLM'en følger det ikke altid (se NEWS-001:
    publicerede artikler med hallucinerede links som /jonas-vingegaard,
    /tour-de-france-klassement). Dette er et deterministisk sikkerhedsnet
    før DB-skrivning."""
    race_slugs = {r["slug"] for r in races}

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


# ── Hoved ─────────────────────────────────────────────────────────────────────

def run(limit: int, max_drafts: int) -> None:
    if not ANTHROPIC_KEY:
        print("FEJL: ANTHROPIC_API_KEY mangler i .env")
        print("Hent nøgle på: https://console.anthropic.com/settings/keys")
        sys.exit(1)

    client            = Anthropic(api_key=ANTHROPIC_KEY)
    articles          = get_unprocessed(limit)
    races             = get_active_races()
    startlist_context = get_ongoing_startlists()

    print(f"ai_news_processor.py — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Fandt {len(articles)} ubehandlede artikler | {len(races)} løb til interne links")
    print(f"Max {max_drafts} artikel(er) skrives denne kørsel (mål: 1, jf. STRATEGI.md §1)")
    print(f"Artikler gemmes som kladder — godkend på klassementet.dk/admin\n")

    # ── Trin 1: Score ALLE kandidater først, før vi skriver noget ────────────
    # Vi skal kunne sammenligne dagens nyheder og vælge den allerbedste,
    # i stedet for blot at skrive den første, der overstiger tærsklen.
    qualified = []
    skipped = 0
    for i, art in enumerate(articles, 1):
        print(f"[{i}/{len(articles)}] {art['title'][:70]}")
        score = score_article(client, art)
        print(f"  Score: {score:.0f}/10", end="")

        if score < MIN_SCORE:
            print(" — for lav, springer over")
            mark_processed(art["id"], score)
            skipped += 1
        else:
            print(" — kvalificeret, sammenlignes med dagens øvrige kandidater")
            qualified.append((score, art))

        time.sleep(DELAY)

    # ── Trin 2: Vælg kun den/de allerbedste blandt de kvalificerede ─────────
    # Stabil sortering: ved lige score vinder den nyeste (articles kom allerede
    # i published_at-faldende rækkefølge fra get_unprocessed()).
    qualified.sort(key=lambda pair: pair[0], reverse=True)
    to_draft = qualified[:max_drafts]
    not_drafted = qualified[max_drafts:]

    if not_drafted:
        titles = ", ".join(a["title"][:50] for _, a in not_drafted)
        print(f"\n{len(not_drafted)} kvalificeret(e) artikel(er) IKKE skrevet (dagligt loft nået): {titles}")
        for score, art in not_drafted:
            mark_processed(art["id"], score)  # markér behandlet, så den ikke gentages i morgen

    drafted = failed = 0
    for score, art in to_draft:
        print(f"\nSkriver: {art['title'][:70]} (score {score:.0f}/10)")

        result = rewrite_article(client, art, races, startlist_context)
        if not result or not result.get("title") or not result.get("content"):
            print("  -> FEJL ved omskrivning")
            mark_processed(art["id"], score)
            failed += 1
            time.sleep(DELAY)
            continue

        slug = slug_from_title(result["title"])
        saved = save_article({
            "slug":             slug,
            "title":            result["title"],
            "excerpt":          result.get("excerpt", ""),
            "content":          sanitize_links(result["content"], races),
            "meta_description": result.get("excerpt", "")[:160],
            "category":         result.get("category", "generelt"),
            "author":           "Klassementet AI",
            "source_url":       art["external_url"],
            "is_advertorial":   False,
            "status":           "draft",
            "published_at":     None,
        })

        mark_processed(art["id"], score)

        if saved:
            print(f"  -> Kladde gemt: /nyheder/{slug}")
            drafted += 1
        else:
            failed += 1

        time.sleep(DELAY)

    print(f"\nFærdig: {drafted} kladder gemt, {len(not_drafted)} kvalificerede-men-ikke-skrevet (dagligt loft), {skipped} for lav score, {failed} fejl")
    print(f"Godkend på: klassementet.dk/admin")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=MAX_ARTICLES,
                        help=f"Max artikler der SCORES per kørsel (default: {MAX_ARTICLES})")
    parser.add_argument("--max-drafts", type=int, default=MAX_DRAFTS_PER_RUN,
                        help=f"Max artikler der rent faktisk SKRIVES per kørsel (default: {MAX_DRAFTS_PER_RUN}, mål er 1)")
    args = parser.parse_args()
    run(args.limit, args.max_drafts)
