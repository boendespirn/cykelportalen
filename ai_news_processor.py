"""
ai_news_processor.py
Behandler råartikler fra raw_news med Claude (Anthropic API):
  1. Scorer relevans for danske cykelfans (1-10) for ALLE kandidater i puljen
  2. Rangerer de kvalificerede kandidater og omskriver kun den/de allerbedste
     til dansk med interne links (max MAX_DRAFTS_PER_RUN, mål er 1 — se
     STRATEGI.md §1: kvalitet frem for mængde, mens vi venter på indeksering)
  3. Gemmer i news_articles som kladde (kræver godkendelse i /admin)

Interne links følger linkstrategi.py: ugebudget for link-bærende artikler og
andele pr. spand (cross, Giro, Tour, forside ...). Hvert gemt links spand
skrives i news_articles.link_spand, så næste kørsel kan tælle.

Krav: ANTHROPIC_API_KEY i .env

Kør: python ai_news_processor.py
     python ai_news_processor.py --limit 5          (score max 5 kandidater)
     python ai_news_processor.py --max-drafts 1      (skriv kun den allerbedste)
     python ai_news_processor.py --dry-run          (score og vælg, skriv intet)

Køres hver morgen af workeren som trin 2 i jobbet `nyheder` (scheduler.py),
lige efter rss_news_scraper.py. Overskrifterne står i morgenens Telegram-besked.
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
from urllib.parse import quote
from anthropic import Anthropic
import linkstrategi
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

WRITE_MODEL        = "claude-sonnet-5"            # scoring og artikel — ejeren skal godkende resultatet, så kvalitet før pris
# Claude 5 tænker, før den svarer, og tænkningen tæller med i max_tokens. Med
# 3-4000 gik hele budgettet til tænkning, og svaret kom tomt tilbage
# (stop_reason=max_tokens, kun en thinking-blok). Loftet er et loft, ikke et
# forbrug — et normalt svar bruger langt mindre.
WRITE_MAX_TOKENS   = 16000
MIN_SCORE          = 8      # kun tophistorier scores videre (8-10)
MIN_SCORE_CROSS    = 6      # cross har sit eget slot — se vaelg_kladder(); en løbsoptakt scores typisk 6
MIN_SCORE_EKSTRA   = 9      # en ANDEN landevejsartikel samme dag kræver en reelt stor nyhed
MAX_ARTICLES       = 80     # max artikler der SCORES per kørsel (kandidatpuljen)
MAX_DRAFTS_PER_RUN = 2      # max artikler der rent faktisk SKRIVES per kørsel — målet er 1, se STRATEGI.md §1
MAX_ALDER_TIMER    = 36     # ældre råartikler er gamle nyheder, når kørslen er dagligt om morgenen
DELAY              = 0.5    # sekunder mellem API-kald

# Grand Tours og monumenter skal altid kunne linkes til — også uden for deres
# sæson. Det er dem, SEO-strategien bygger mod, og en nyhed om næste års rute
# kommer typisk et halvt år før løbet.
ALTID_LINKBARE = [
    "tour-de-france", "giro-d-italia", "la-vuelta-ciclista-a-espana",
    "milano-sanremo", "ronde-van-vlaanderen", "paris-roubaix",
    "liege-bastogne-liege", "il-lombardia",
]

# ── Løb der linkes til internt (opdateres automatisk fra DB) ─────────────────

def get_active_races() -> list[dict]:
    """Løb, en artikel må linke til: dem omkring i dag plus seneste udgave af
    de store løb.

    Den gamle udgave tog de 30 senest startende løb. I oktober var det 24
    cross-løb og seks andre — Tour de France stod ikke på listen, så en nyhed
    om næste års Tour kunne ikke linke til noget som helst."""
    from datetime import date, timedelta
    hdr = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    i_dag = date.today()
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?select=name,slug,race_type,start_date,end_date"
        f"&end_date=gte.{(i_dag - timedelta(days=30)).isoformat()}"
        f"&start_date=lte.{(i_dag + timedelta(days=60)).isoformat()}"
        f"&order=start_date&limit=80",
        headers=hdr, timeout=30,
    )
    races = res.json() if res.ok else []
    kendte = {r["slug"] for r in races}
    for base in ALTID_LINKBARE:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/races?select=name,slug,race_type,start_date,end_date"
            f"&slug=like.{base}-2*&start_date=lte.{(i_dag + timedelta(days=400)).isoformat()}"
            f"&order=start_date.desc&limit=1",
            headers=hdr, timeout=30,
        )
        for row in (r.json() if r.ok else []):
            if row["slug"] not in kendte:
                races.append(row)
                kendte.add(row["slug"])
    return races


def get_recent_titles(days: int = 4) -> list[str]:
    """Overskrifter, vi selv har skrevet de sidste dage — uanset status.

    Samme historie står i alle feeds, ofte over flere dage (en Tour-præsentation
    kører på CyclingNews, VeloNews og WielerFlits). Uden denne liste ville
    processoren skrive den samme nyhed igen næste morgen fra en ny kilde."""
    from datetime import date, timedelta
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/news_articles?select=title"
        f"&created_at=gte.{(date.today() - timedelta(days=days)).isoformat()}&limit=50",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
        timeout=30,
    )
    return [r["title"] for r in res.json()] if res.ok else []


def get_linkstatus(periode_start: str) -> dict:
    """Hvad linkstrategien allerede har brugt: link-bærende artikler de sidste
    7 dage (ugebudgettet), pr. spand i indeværende periode (andelene) og
    ankertyper pr. linkmål (ankerfordelingen). Afviste kladder tæller ikke —
    deres links kom aldrig på siden."""
    from datetime import date, timedelta
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/news_articles?select=created_at,link_spand,link_maal,link_ankertype"
        f"&link_spand=not.is.null&status=neq.rejected"
        f"&created_at=gte.{min(periode_start, (date.today() - timedelta(days=7)).isoformat())}",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
        timeout=30,
    )
    rows = res.json() if res.ok else []
    uge_start = (date.today() - timedelta(days=7)).isoformat()
    spande: dict[str, int] = {}
    for r in rows:
        if r["created_at"][:10] >= periode_start:
            spande[r["link_spand"]] = spande.get(r["link_spand"], 0) + 1
    ankre = requests.get(
        f"{SUPABASE_URL}/rest/v1/news_articles?select=link_maal,link_ankertype"
        f"&link_ankertype=not.is.null&status=neq.rejected",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
        timeout=30,
    )
    pr_maal: dict[str, list[str]] = {}
    for r in (ankre.json() if ankre.ok else []):
        pr_maal.setdefault(r["link_maal"], []).append(r["link_ankertype"])
    return {
        "uge": sum(1 for r in rows if r["created_at"][:10] >= uge_start),
        "spande": spande,
        "ankre": pr_maal,
    }


def lav_linkplan(status: dict, races: list[dict]) -> tuple[list[dict] | None, str]:
    """Dagens linkplan: prioriterede mål med ankertype — eller None, når
    ugebudgettet er brugt. Returnerer også en linje til loggen."""
    from datetime import date
    pr_uge, andele = linkstrategi.periode(date.today())
    if status["uge"] >= pr_uge:
        return None, f"ugebudget brugt ({status['uge']}/{pr_uge}) — ingen interne links"
    maal = linkstrategi.linkmaal(date.today(), races)
    raekke = linkstrategi.prioriteret(andele, status["spande"], set(maal))
    plan = []
    for spand in raekke:
        for m in maal.get(spand, []):
            if any(p["sti"] == m["sti"] for p in plan):
                continue
            plan.append({**m, "spand": spand,
                         "ankertype": linkstrategi.naeste_ankertype(status["ankre"].get(m["sti"], []))})
    andele_txt = ", ".join(f"{s} {a:.0%}" for s, a in andele.items())
    mangler = [s for s in andele if s not in maal]
    return plan, (f"{status['uge']}/{pr_uge} link-artikler de sidste 7 dage | andele: {andele_txt} | "
                  f"rækkefølge: {' > '.join(raekke)}"
                  + (f" | uden side endnu: {', '.join(mangler)}" if mangler else ""))


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
    """Ubehandlede råartikler fra de sidste MAX_ALDER_TIMER timer.

    Ældre ubehandlede markeres som behandlet i samme omgang. Processoren stod
    stille fra juli til oktober, og uden afskæringen ville dens første kørsel
    have scoret tre måneder gamle nyheder som dagens."""
    from datetime import timedelta
    graense = (datetime.now(timezone.utc) - timedelta(hours=MAX_ALDER_TIMER)).isoformat()
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/raw_news?processed=eq.false&published_at=lt.{quote(graense)}",
        json={"processed": True},
        headers=DB_HEADERS, timeout=30,
    )
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/raw_news"
        f"?processed=eq.false&published_at=gte.{quote(graense)}"
        f"&order=published_at.desc&limit={limit}",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
        timeout=30,
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

SCORE_SYSTEM = """Du er nyhedsredaktør på klassementet.dk og vurderer dagens nyhedskandidater for danske cykelfans — både landevej (UCI WorldTour, Grand Tours, klassikere) og cykelcross (World Cup, Superprestige, X2O Trofee, VM).

Score hver kandidat 1-10 for nyhedsværdi:
- 9-10: årets største historier — fx præsentationen af næste års Grand Tour-rute, en stor rytters holdskifte eller karrierestop, et afgørende løbsresultat
- 7-8: klart relevant for fans: store navne, danske ryttere, vigtige løb og transfers
- 4-6: sekundære historier, opfølgninger, mindre navne
- 1-3: udstyr, gravel, motion, amatørløb, kåringer, spil og konkurrencer

Cykelcross vurderes på egne præmisser: en sejr eller et stort navn (Van der Poel, Van Aert, Pidcock, Nys, Iserbyt, Van Empel, Brand) i et World Cup-, Superprestige- eller X2O-løb er en 7-8'er for cross-fans, selv om den ikke kan måle sig med en Tour-nyhed.

DUBLETTER: Flere kandidater dækker ofte samme historie. Giv kun den mest fyldestgørende af dem (mest indhold, bedst kilde) den høje score — de øvrige får 1. Står historien allerede blandt vores egne overskrifter, får alle dens kandidater 1.

"cross" er true, når kandidaten handler om cykelcross som disciplin — ikke når en landevejsrytter blot nævner crosssæsonen i forbifarten.

Svar KUN med JSON: [{"i": 1, "score": 8, "cross": false}, ...] — én række pr. kandidat, ingen anden tekst."""

REWRITE_SYSTEM = """Du skriver cykel-nyheder til klassementet.dk — Danmarks bedste kilde til professionel cykling: landevej og cykelcross.

Regler:
- Skriv altid på korrekt, engageret dansk (sportsmedie-tone som TV 2 Sport)
- Omskriv originalen grundigt — aldrig direkte oversæt
- Artiklerne skal være fyldestgørende: giv al vigtig information, forklar kontekst og baggrund
- LINKS — følg linkplanen i opgaven:
  - Står der "INGEN interne links", må artiklen ikke indeholde et eneste internt link.
  - Ellers MAKSIMALT 2 interne links: (1) ét strategisk link til det FØRSTE mål i linkplanen, artiklen er reelt relevant for, med den angivne ankertype, og (2) valgfrit ét link til det løb, artiklen primært handler om, ved første naturlige omtale (kun løbsnavnet som ankertekst).
  - Relevans er et krav: et link til et løb må kun sættes, hvis artiklen handler om løbet. Er intet løbsmål relevant, så brug forsiden — med en naturlig sætning, aldrig en påklistret henvisning.
  - Ankerteksten skal læses som en naturlig del af sætningen — aldrig "klik her".
  - Link kun til den UDGAVE, artiklen handler om: en nyhed om Tour de France 2027 må ikke linke til /tour-de-france-2026. Står udgaven ikke på listen, så link ikke til løbet.
  - Gentag ALDRIG samme link. Skriv løbsnavnet plain text alle andre gange det nævnes.
- Omvendt pyramide: det vigtigste først, derefter baggrund og detaljer
- Lov aldrig live-dækning: klassementet.dk har ingen live-opdateringer eller live-tracking. Skriv ikke "følg med undervejs/under løbet/live" — en henvisning må kun love det, siden har: startliste, etaper, stigningsprofiler, resultater og klassement
- Brug SEO-søgeord naturligt: løbets navn, rytternes navne, "cykling" — og "cykelcross" i cross-artikler
- KUN FAKTA FRA KILDEN: tilføj aldrig resultater, tal, holdtilknytninger eller citater, der ikke står i originalen. Baggrund må kun være almen, sikker viden — er du i tvivl om et faktum, så udelad det
- FAKTUEL PRÆCISION: Nævn KUN ryttere i et løb hvis de faktisk er på startlisten. Hvis du er i tvivl, undlad at nævne dem i den løbs-kontekst
- Svar KUN med ren JSON — ingen markdown-blokke, ingen forklaringer"""


def score_batch(client: Anthropic, articles: list[dict],
                recent_titles: list[str]) -> list[tuple[float, bool]]:
    """Scorer alle kandidater i ÉT kald — (score, er_cross) pr. kandidat.

    Indtil 2026-10-23 fik hver kandidat sit eget Haiku-kald og ét tal tilbage.
    Det var støjende og blindt for resten af dagens pulje: Tour de France
    2027-ruten fik 7 og røg ud, mens en af dens seks dubletter fik 8. Set
    samlet kan modellen sammenligne, og den kan selv samle dubletterne.

    Fejler kaldet, eller mangler en kandidat i svaret, får den score 0 — en
    nyhed skrives hellere ikke end på et gæt (CLAUDE.md §6)."""
    linjer = []
    for i, art in enumerate(articles, 1):
        resume = re.sub(r"\s+", " ", (art.get("excerpt") or ""))[:240]
        linjer.append(f"{i}. [{art['source']}, {len(art.get('content') or '')} tegn] "
                      f"{art['title']}\n   {resume}")
    prompt = "Dagens kandidater:\n\n" + "\n".join(linjer)
    if recent_titles:
        prompt += "\n\nVores egne overskrifter de sidste dage:\n" + "\n".join(
            f"- {t}" for t in recent_titles)

    ud = [(0.0, False) for _ in articles]
    try:
        resp = client.messages.create(
            model=WRITE_MODEL,
            max_tokens=WRITE_MAX_TOKENS,
            system=SCORE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        if resp.stop_reason == "max_tokens":
            print("  [SCORE AFHUGGET] svaret nåede token-loftet — ingen kandidater kvalificerer sig i dag")
            return ud
        text = next((b.text for b in resp.content
                     if getattr(b, "type", None) == "text"), "")
        # Rækkerne læses én for én i stedet for som ét JSON-dokument: én
        # skæv række (et ekstra komma, en kommentar) må ikke tage hele dagens
        # pulje med sig.
        for m in re.finditer(r'\{[^{}]*?"i"\s*:\s*(\d+)[^{}]*?"score"\s*:\s*(\d+(?:\.\d+)?)'
                             r'[^{}]*?"cross"\s*:\s*(true|false)[^{}]*\}', text):
            i = int(m.group(1)) - 1
            if 0 <= i < len(articles):
                ud[i] = (min(float(m.group(2)), 10.0), m.group(3) == "true")
    except Exception as e:
        print(f"  [SCORE FEJL] {e} — ingen kandidater kvalificerer sig i dag")
    return ud


def linkplan_tekst(plan: list[dict] | None, races: list[dict]) -> str:
    """Linkplanen som tekst til prompten. plan=None: ugens budget er brugt."""
    if plan is None:
        return ("LINKPLAN: INGEN interne links i denne artikel — ugens budget for "
                "link-bærende artikler er brugt.")
    linjer = ["LINKPLAN — strategiske mål i prioriteret rækkefølge (brug det første, artiklen er reelt relevant for):"]
    for m in plan:
        if m["sti"] == "/":
            anker = 'ankertekst "Klassementet" eller en naturlig beskrivelse af siden'
        elif m["sti"] == linkstrategi.CROSS_KALENDER:
            anker = ('ankertekst som "cykelcross-kalenderen", "kalenderen for cykelcross" '
                     'eller "årets crossløb"')
        else:
            anker = "ankertype: " + linkstrategi.ANKER_FORKLARING[m["ankertype"]].format(
                navn=m["navn"], aar=m["aar"])
        linjer.append(f"- {m['navn']}: {m['sti']} ({anker})")
    linjer.append("\nLøbssider der må bruges til link (2) — kun hvis artiklen handler om løbet:")
    linjer += [f"- {r['name']}: /{r['slug']}" for r in races]
    return "\n".join(linjer)


def rewrite_article(client: Anthropic, article: dict, races: list[dict], startlist_context: str,
                    plan: list[dict] | None) -> dict | None:
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
{linkplan_tekst(plan, races)}

Returner præcis dette JSON:
{{
  "title": "Dansk titel (SEO-optimeret, max 70 tegn)",
  "excerpt": "Kort resume på dansk (max 160 tegn, bruges som meta-description)",
  "content": "Fuld artikel på dansk (600-900 ord). Brug \\n\\n mellem afsnit. Dæk emnet grundigt: baggrund, context, citater, hvad det betyder fremadrettet. Links efter linkplanen ovenfor; alle andre nævnelser af løbet skrives som plain text.",
  "category": "resultater|startliste|transfer|profil|analyse|cykelcross|generelt (brug cykelcross for alle cross-nyheder)",
  "linkmaal": "stien på det strategiske linkmål, du brugte, fx /, eller null"
}}"""

    try:
        resp = client.messages.create(
            model=WRITE_MODEL,
            max_tokens=WRITE_MAX_TOKENS,
            system=REWRITE_SYSTEM,
            # Ingen temperature: parameteren er udfaset for Claude 5-modellerne
            # og giver HTTP 400 (samme fælde som i race_recap_agent.py).
            messages=[{"role": "user", "content": prompt}],
        )
        # Et afhugget svar er en halv artikel — og ugyldig JSON. Hellere
        # ingen kladde end en, der slutter midt i en sætning.
        if resp.stop_reason == "max_tokens":
            print("  [AFHUGGET] svaret nåede token-loftet — intet gemt")
            return None
        text = next((b.text for b in resp.content
                     if getattr(b, "type", None) == "text"), "")
        return extract_json(text)
    except Exception as e:
        print(f"  [REWRITE FEJL] {e}")
        return None


def interne_links(content: str) -> list[str]:
    """Stierne på alle interne links i artiklen, i rækkefølge."""
    stier = []
    for url in re.findall(r"\[[^\]]+\]\(([^)]+)\)", content):
        if url.startswith("https://klassementet.dk"):
            url = url[len("https://klassementet.dk"):] or "/"
        if url.startswith("/"):
            stier.append(url)
    return stier


def fjern_interne_links(content: str) -> str:
    """Interne links bliver til plain text — ugens linkbudget er brugt."""
    def replace(match: re.Match) -> str:
        url = match.group(2)
        intern = url.startswith("/") or url.startswith("https://klassementet.dk")
        return match.group(1) if intern else match.group(0)
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", replace, content)


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

def vaelg_kladder(scored: list[tuple[float, dict]], max_drafts: int) -> list[tuple[float, dict]]:
    """Dagens kladder: højst én landevej og én cross, og højst max_drafts.

    Cross får sit eget slot med en lavere tærskel (MIN_SCORE_CROSS). Scoret
    mod landevejens store navne taber en cross-nyhed altid — en Superprestige-
    sejr bliver aldrig en 8'er ved siden af en Tour-præsentation — og så kom
    der aldrig cross på siden, selv om sæsonen er 24 løb lang.

    En anden landevejsartikel tages kun, når der ingen cross-kladde er, og
    nyheden er en reel undtagelse (MIN_SCORE_EKSTRA, jf. STRATEGI.md §2: to
    store, indbyrdes uafhængige nyheder samme dag)."""
    vej   = sorted((p for p in scored if not p[1].get("_cross") and p[0] >= MIN_SCORE),
                   key=lambda p: p[0], reverse=True)
    cross = sorted((p for p in scored if p[1].get("_cross") and p[0] >= MIN_SCORE_CROSS),
                   key=lambda p: p[0], reverse=True)
    valgt = vej[:1] + cross[:1]
    if not cross and len(vej) > 1 and vej[1][0] >= MIN_SCORE_EKSTRA:
        valgt.append(vej[1])
    return valgt[:max_drafts]


def run(limit: int, max_drafts: int, dry_run: bool = False) -> None:
    if not ANTHROPIC_KEY:
        print("FEJL: ANTHROPIC_API_KEY mangler i .env")
        print("Hent nøgle på: https://console.anthropic.com/settings/keys")
        sys.exit(1)

    client            = Anthropic(api_key=ANTHROPIC_KEY)
    articles          = get_unprocessed(limit)
    races             = get_active_races()
    startlist_context = get_ongoing_startlists()
    recent_titles     = get_recent_titles()

    print(f"ai_news_processor.py — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
          + (" — TØRKØRSEL, intet skrives" if dry_run else ""))
    print(f"Fandt {len(articles)} ubehandlede artikler (seneste {MAX_ALDER_TIMER} t) | "
          f"{len(races)} løb til interne links | {len(recent_titles)} egne overskrifter til dublet-tjek")
    print(f"Max {max_drafts} artikel(er) skrives denne kørsel: én landevej + én cykelcross (jf. STRATEGI.md §2)")
    print(f"Artikler gemmes som kladder — godkend på klassementet.dk/admin\n")

    # ── Trin 1: Score ALLE kandidater først, før vi skriver noget ────────────
    # Vi skal kunne sammenligne dagens nyheder og vælge den allerbedste,
    # i stedet for blot at skrive den første, der overstiger tærsklen.
    scored: list[tuple[float, dict]] = []
    for i, (art, (score, cross)) in enumerate(
            zip(articles, score_batch(client, articles, recent_titles)), 1):
        art["_cross"] = cross
        mærke = " [cross]" if cross else ""
        print(f"[{i}/{len(articles)}] {score:>4.0f}/10{mærke}  {art['source']}: {art['title'][:70]}")
        scored.append((score, art))

    # Modellen giver altid mindst 1. Står alt på 0, fejlede scoringen — og så
    # skal jobbet fejle, så runneren melder det på Telegram, i stedet for at
    # ligne en stille dag uden nyheder. Intet er markeret som behandlet, så
    # morgendagens kørsel tager puljen igen.
    if scored and all(score == 0 for score, _ in scored):
        print("\nFEJL: scoringen gav intet resultat — se [SCORE FEJL] ovenfor")
        sys.exit(2)

    # ── Trin 2: Vælg kun den/de allerbedste ─────────────────────────────────
    # Stabil sortering: ved lige score vinder den nyeste (articles kom allerede
    # i published_at-faldende rækkefølge fra get_unprocessed()).
    to_draft = vaelg_kladder(scored, max_drafts)
    valgte = {id(a) for _, a in to_draft}
    skipped = len(scored) - len(to_draft)

    print(f"\nValgt til kladde ({len(to_draft)}):")
    for score, art in to_draft:
        print(f"  {score:.0f}/10{' [cross]' if art.get('_cross') else ''}  {art['title'][:80]}")
    if dry_run:
        from datetime import date
        plan, plan_log = lav_linkplan(
            get_linkstatus(linkstrategi.periode_fra(date.today()).isoformat()), races)
        print(f"\nLinkplan: {plan_log}")
        for p in plan or []:
            print(f"  {p['spand']:>8}  {p['sti']}  ({p['ankertype']})")
        print("\nTørkørsel — intet skrevet, intet markeret som behandlet.")
        return

    # Alt det fravalgte markeres behandlet, så det ikke kommer igen i morgen.
    for score, art in scored:
        if id(art) not in valgte:
            mark_processed(art["id"], score)

    from datetime import date
    linkstatus = get_linkstatus(linkstrategi.periode_fra(date.today()).isoformat())
    races_by_slug = {r["slug"]: r for r in races}

    drafted = failed = 0
    for score, art in to_draft:
        print(f"\nSkriver: {art['title'][:70]} (score {score:.0f}/10)")
        plan, plan_log = lav_linkplan(linkstatus, races)
        print(f"  Linkplan: {plan_log}")

        result = rewrite_article(client, art, races, startlist_context, plan)
        if not result or not result.get("title") or not result.get("content"):
            print("  -> FEJL ved omskrivning")
            mark_processed(art["id"], score)
            failed += 1
            time.sleep(DELAY)
            continue

        content = sanitize_links(result["content"], races)
        if plan is None:
            content = fjern_interne_links(content)
        # Hvad artiklen faktisk linker til — ikke hvad modellen siger, den
        # gjorde. Det første link til et mål i planen er det strategiske.
        links = interne_links(content)
        plan_stier = {p["sti"]: p for p in plan or []}
        strategisk = next((plan_stier[s] for s in links if s in plan_stier), None)
        link_felter = {}
        if strategisk:
            link_felter = {"link_spand": strategisk["spand"], "link_maal": strategisk["sti"],
                           "link_ankertype": strategisk["ankertype"] if strategisk["sti"] != "/" else None}
        elif links:
            link_felter = {"link_spand": linkstrategi.spand_for(links[0], races_by_slug) or "andet",
                           "link_maal": links[0]}

        slug = slug_from_title(result["title"])
        saved = save_article({
            "slug":             slug,
            "title":            result["title"],
            "excerpt":          result.get("excerpt", ""),
            "content":          content,
            **link_felter,
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
            if link_felter:
                print(f"     Interne links: {', '.join(links)} (spand: {link_felter['link_spand']})")
                linkstatus["uge"] += 1
                spand = link_felter["link_spand"]
                linkstatus["spande"][spand] = linkstatus["spande"].get(spand, 0) + 1
                if link_felter.get("link_ankertype"):
                    linkstatus["ankre"].setdefault(link_felter["link_maal"], []).append(
                        link_felter["link_ankertype"])
            drafted += 1
        else:
            failed += 1

        time.sleep(DELAY)

    print(f"\nFærdig: {drafted} kladder gemt, {skipped} fravalgt, {failed} fejl")
    print(f"Godkend på: klassementet.dk/admin")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=MAX_ARTICLES,
                        help=f"Max artikler der SCORES per kørsel (default: {MAX_ARTICLES})")
    parser.add_argument("--max-drafts", type=int, default=MAX_DRAFTS_PER_RUN,
                        help=f"Max artikler der rent faktisk SKRIVES per kørsel (default: {MAX_DRAFTS_PER_RUN}, mål er 1)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Score og vælg, men skriv ingen artikel og markér intet som behandlet")
    args = parser.parse_args()
    run(args.limit, args.max_drafts, args.dry_run)
