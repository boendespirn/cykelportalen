"""
cross_startlist_agent.py — startlister til cykelcross fra arrangoerernes PDF'er.

HVORFOR EN EGEN AGENT. `startlist_agent.py` henter fra ProCyclingStats via
`races.pcs_url`. Intet cross-loeb har et pcs_url, og PCS opretter foerst siden
faa dage foer loebet. Arrangoererne lagde den derimod ud i loebsugen, og deres
PDF er RIGERE end PCS: startnummer, navn, UCI-ID, nationalitet, hold OG
UCI-ranking i én tabel. Rankingen er den, favoritlisten paa loebssiden sorterer
efter, saa den kommer gratis med.

Maalt 2026-10-17 paa Berencross Meulebeke: 57 ryttere, 47 med UCI-ranking.

HVORFOR IKKE cyclocross24.com, som har alle 24 loeb: den ligger bag Cloudflares
bot-beskyttelse og svarer "Performing security verification" paa en headless
browser. Vi omgaar ikke en bot-spaerre (CLAUDE.md §7). Arrangoerernes egne
sider er derimod helt aabne.

DAEKNING. Kun de serier, hvis arrangoer selv udgiver PDF'erne: HG Cross
(hgcross.be), Superprestige (loebets kalenderside) og X2O Trofee (hvert loebs
eget site, /renners/). PDF'en kommer i loebsugen, saa agenten proever alle
cross-loeb og melder aerligt, naar der intet er.

Koer:
    py agents/cross_startlist_agent.py --race hg-cross-meulebeke-berencross-2026
    py agents/cross_startlist_agent.py --alle --dry-run
"""
from __future__ import annotations

import argparse
import os
import re
import sys

import requests
from dotenv import load_dotenv
from slugify import slugify

load_dotenv()

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
WRITE = {**AUTH, "Content-Type": "application/json",
         "Prefer": "resolution=merge-duplicates"}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129 Safari/537.36")

# Arrangoerernes sider pr. serie (races.category). Listen staar her og ikke i
# databasen, fordi en ny serie kraever en kodeaendring alligevel: dens
# PDF-navngivning skal verificeres, foer vi stoler paa den.
SERIE_SITES = {
    "HG Cross": "https://hgcross.be",
}

# Sider paa arrangoerens site, der aldrig er et loeb.
IKKE_LOEB = re.compile(
    r"/(contact|cookiebeleid|feed|foto|hospitality|kalender|privacy|nieuws|"
    r"shop|tickets|vacature|over-ons|wp-|category|tag)/", re.I)

# Vi vil have HERRE-ELITE-listen. Raekkefoelgen er prioriteret: det foerste
# moenster, der rammer, vinder — saa en generisk "Men" ikke kaprer juniorlisten.
ELITE_MOENSTRE = [
    # "(?<!wo)": Koppenbergcross 2026 havde baade "...-Men-Elite.pdf" og
    # "...-Women-Elite.pdf", og "men-elite" staar ogsaa i den sidste.
    re.compile(r"(?<!wo)men[-_ ]?elite", re.I),
    re.compile(r"elite[-_ ]?men", re.I),
    re.compile(r"heren[-_ ]?elite", re.I),
    # Heerde 2026: "ELITE-MANNEN-Startlijst-22-10-2026.pdf" — hollandsk.
    re.compile(r"elite[-_ ]?mannen", re.I),
]

# Linjer i PDF'en, der er dokument-chrome og aldrig rytterdata. Uden dette
# klistrede sidefoden ("BERENCROSS MEULEBEKE ... STARTLIST MEN ELITE") sig
# fast paa den sidste rytters holdnavn.
CHROME = re.compile(
    r"^(nr|naam|nom|uci\s*id|nat|team|ploeg|club|uci\s*rank|rank)$"
    r"|start\s*-?\s*list|startlijst|\d{1,2}/\d{1,2}/\d{4}"
    # Superprestige saetter loebsnavnet paa sin egen linje over "STARTLIST";
    # uden dette blev "SUPERPRESTIGE DRUIVENCROSS OVERIJSE" en del af sidste
    # rytters klubnavn (Overijse 2026-10-25).
    r"|^(superprestige|x2o|hg\s*cross)\b"
    # X2O-sidefoden slutter med "Page 1 of 1" (Koppenbergcross 2026).
    r"|^page\s+\d+\s+of\s+\d+$", re.I)

NUM = re.compile(r"^\d{1,3}$")
UCI_ID = re.compile(r"^\d{8,12}$")
NAT = re.compile(r"^[A-Z]{3}$")

# PDF'en bruger UCI's tre-bogstavskoder, resten af databasen to-bogstavs
# ISO-koder. Frontendens flagEmoji() returnerer tom streng ved alt andet end
# to tegn, saa uden oversaettelsen ville ingen cross-rytter faa et flag.
ISO3_TIL_ISO2 = {
    "BEL": "BE", "NED": "NL", "NLD": "NL", "FRA": "FR", "ITA": "IT",
    "ESP": "ES", "GBR": "GB", "GER": "DE", "DEU": "DE", "SUI": "CH",
    "CHE": "CH", "CZE": "CZ", "DEN": "DK", "DNK": "DK", "USA": "US",
    "AUT": "AT", "POL": "PL", "LUX": "LU", "SVK": "SK", "SLO": "SI",
    "SVN": "SI", "HUN": "HU", "NOR": "NO", "SWE": "SE", "IRL": "IE",
    "POR": "PT", "PRT": "PT", "CAN": "CA", "AUS": "AU", "NZL": "NZ",
    "JPN": "JP", "RSA": "ZA", "ZAF": "ZA", "UKR": "UA", "ROU": "RO",
    "CRO": "HR", "HRV": "HR", "EST": "EE", "LAT": "LV", "LTU": "LT",
    "FIN": "FI", "BLR": "BY", "KAZ": "KZ", "COL": "CO", "BRA": "BR",
}


def iso2(kode: str | None) -> str | None:
    """Tre-bogstavskoden oversat. Ukendte koder droppes frem for at blive
    gemt raa — et felt paa tre tegn giver hverken flag eller mening, og en
    tom vaerdi er aerligere end en forkert."""
    if not kode:
        return None
    k = kode.strip().upper()
    if len(k) == 2:
        return k
    return ISO3_TIL_ISO2.get(k)


def hent(url: str):
    try:
        return requests.get(url, headers={"User-Agent": UA}, timeout=45)
    except requests.RequestException as exc:
        print(f"    [hentefejl] {url[:70]} — {type(exc).__name__}")
        return None


# ── Databasen ────────────────────────────────────────────────────────────────

def sb_get(table: str, params: str) -> list:
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}?{params}",
                     headers=AUTH, timeout=45)
    return r.json() if r.ok else []


def sb_upsert(table: str, rows: list, conflict: str) -> bool:
    if not rows:
        return True
    r = requests.post(f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={conflict}",
                      json=rows, headers=WRITE, timeout=60)
    if not r.ok:
        print(f"    [DB-fejl] {table}: {r.status_code} {r.text[:200]}")
    return r.ok


def cross_loeb(slug: str | None) -> list[dict]:
    flt = f"&slug=eq.{slug}" if slug else ""
    return sb_get("races", "select=id,slug,name,category,start_date,race_type,country_code"
                           f"&race_type=eq.cyclocross&order=start_date{flt}")


# ── Find arrangoerens loebsside ──────────────────────────────────────────────

def find_loebsside(race: dict) -> tuple[str | None, list[str]]:
    """Arrangoerens side for netop dette loeb, fundet ved at sammenholde
    sidens startliste-PDF'er med loebets navn.

    Sidens URL kan IKKE udledes af vores slug: vores
    `hg-cross-heerderstrand-2026` hedder `/heerde/` hos arrangoeren. Derfor
    gaetter vi ikke — vi henter forsidens interne links og lader PDF-navnet
    afgoere, hvilken side der hoerer til hvilket loeb."""
    base = SERIE_SITES.get(race.get("category") or "")
    if not base:
        return None, []

    forside = hent(base + "/")
    if forside is None or not forside.ok:
        return None, []

    sider = sorted({u for u in re.findall(
        rf'href="({re.escape(base)}/[a-z0-9\-]+/)"', forside.text, re.I)
        if not IKKE_LOEB.search(u)})

    # Loebets navn uden serienavn: "HG Cross Meulebeke - Berencross" → tokens
    # meulebeke, berencross. Et af dem staar i PDF-navnet.
    navn = (race.get("name") or "").lower()
    for serie in SERIE_SITES:
        navn = navn.replace(serie.lower(), " ")
    tokens = {t for t in re.split(r"[^a-z]+", navn) if len(t) > 3}

    for side in sider:
        r = hent(side)
        if r is None or not r.ok:
            continue
        pdfs = sorted(set(re.findall(r'href="([^"]+\.pdf)"', r.text, re.I)))
        if not pdfs:
            continue
        if any(t in " ".join(pdfs).lower() for t in tokens):
            return side, pdfs
        # Heerdes PDF'er hed bare "ELITE-MANNEN-Startlijst-22-10-2026.pdf"
        # (2026-10-22), saa adressen maa ogsaa tælle: /heerde/ ↔ heerderstrand.
        by = side.rstrip("/").rsplit("/", 1)[1].lower()
        if len(by) > 3 and any(by in t or t in by for t in tokens):
            return side, pdfs
    return None, []


# ── KNWU (hollandske loeb) ───────────────────────────────────────────────────
# mijn.knwu.nl ser tom ud — hver URL svarer med den samme skal — men siden
# henter sine data fra et AABENT API uden login. De to headere er KNWU's
# foederations-id; uden dem svarer API'et "Entity Race ... was not found".
#
# Det daekker kun hollandske loeb (KNWU er det hollandske forbund), altsaa ét
# af vores 24 cross-loeb. Men det ét er struktureret JSON i stedet for en PDF.
FOYS = "https://api.foys.io/cycling/public-api/v1"
KNWU_ID = "2e38d9ea-84bb-452a-b58b-669352b0a2c6"
FOYS_H = {"User-Agent": UA, "Accept": "application/json",
          "x-federationid": KNWU_ID, "x-organisationid": KNWU_ID,
          "Referer": "https://mijn.knwu.nl/"}


def _foys(sti: str, **params) -> list:
    """Altid en liste tilbage. API'et svarer snart med {"items": [...]},
    snart med en bar liste — og et .get() paa en liste vaeltede agenten."""
    try:
        r = requests.get(f"{FOYS}/{sti}", params=params, headers=FOYS_H, timeout=45)
        if not r.ok:
            return []
        d = r.json()
    except (requests.RequestException, ValueError):
        return []
    if isinstance(d, dict):
        return d.get("items") or []
    return d if isinstance(d, list) else []


def hent_fra_knwu(race: dict) -> tuple[list[dict], str | None]:
    """Startlisten fra KNWU, fundet paa loebsDATOen.

    Vi gemmer intet KNWU-id: arrangementet slaas op paa datoen, og derefter
    vaelges ELITE MEN-loebet inde i det. Saa virker det ogsaa for naeste
    saesons loeb uden en manuel kobling."""
    events = _foys("events", skipCount=0, maxResultCount=200,
                   isRaceResult="false", isHistoric="false", sorting="startDate")
    dag = race["start_date"]
    traef = [e for e in events if str(e.get("startDate") or "")[:10] == dag]
    if not traef:
        return [], None

    for ev in traef:
        for sub in _foys("races/lookup", eventId=ev.get("id")):
            navn = (sub.get("name") or "").upper()
            if "ELITE" not in navn or "MEN" not in navn or "WOMEN" in navn:
                continue
            items = _foys("races/race-participants",
                          raceId=sub.get("id"), maxResultCount=999)
            ryttere = [{
                "bib": p.get("bib") or 0,
                "navn": (p.get("personName") or "").strip(),
                "nat": p.get("personNationality"),
                "hold": p.get("raceTeamName") or p.get("personLicenseOrganisationName"),
                "uci_rank": None,
            } for p in items if (p.get("personName") or "").strip()
                and (p.get("status") or "").lower() != "rejected"]
            if ryttere:
                return ryttere, f"https://mijn.knwu.nl/calendar/races/{sub.get('id')}"
    return [], None


# ── Superprestige ────────────────────────────────────────────────────────────
# Startlisten ligger paa loebets side under "participants" pr. kategori
# (ejeren pegede paa den 2026-10-24, Overijse). PDF-navnet er bare et
# loebenummer (/storage/programs/file_participants/439/439.pdf), saa
# kategorien og datoen laeses i PDF'ens sidefod: "STARTLIST MEN ELITE
# 25/10/2026". Linkene forsvinder fra siden igen, naar loebet er koert.
SP_BASE = "https://www.superprestigecyclocross.be"
SP_SIDEFOD = re.compile(r"STARTLIST\s+(.+?)\s+(\d{2})/(\d{2})/(\d{4})")


def hent_fra_superprestige(race: dict) -> tuple[bytes | None, str | None, str]:
    """(pdf, url, besked). Loebets side findes paa kalenderen ud fra byen i
    navnet — "Superprestige Middelkerke - Noordzeecross" → /middelkerke."""
    aar = int(race["start_date"][:4])
    md = int(race["start_date"][5:7])
    saeson = f"{aar}-{aar + 1}" if md >= 7 else f"{aar - 1}-{aar}"
    kal = hent(f"{SP_BASE}/en/calendar")
    if kal is None or not kal.ok:
        return None, None, "kalenderen svarede ikke"
    navn = (race.get("name") or "").lower().replace("superprestige", " ")
    tokens = {t for t in re.split(r"[^a-z]+", navn) if len(t) > 3}
    sider = sorted({u for u in re.findall(
        rf'href="({re.escape(SP_BASE)}/en/calendar/{saeson}/[^"/]+)"', kal.text)
        if any(t in u.rsplit("/", 1)[1].lower() for t in tokens)})
    if not sider:
        return None, None, f"loebet staar ikke paa kalenderen for {saeson}"

    r = hent(sider[0])
    if r is None or not r.ok:
        return None, None, f"{sider[0]} svarede ikke"
    pdfs = sorted(set(re.findall(r'href="([^"]*file_participants/[^"]+?\.pdf)[^"]*"', r.text)))
    if not pdfs:
        return None, None, "ingen startlister paa loebets side endnu — kommer typisk i loebsugen"

    for url in pdfs:
        url = url if url.startswith("http") else SP_BASE + url
        p = hent(url)
        if p is None or not p.ok:
            continue
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        with fitz.open(stream=p.content, filetype="pdf") as doc:
            m = SP_SIDEFOD.search(" ".join(side.get_text() for side in doc))
        if not m:
            continue
        kat, dag = m.group(1).upper(), f"{m.group(4)}-{m.group(3)}-{m.group(2)}"
        if re.search(r"\bMEN ELITE\b|\bELITE MEN\b", kat) and "WOMEN" not in kat:
            if dag != race["start_date"]:
                return None, None, f"herre-elite-PDF'en er dateret {dag}, ikke {race['start_date']}"
            return p.content, url, f"{kat} {dag}"
    return None, None, f"{len(pdfs)} startlister, men ingen for herre-elite endnu"


# ── X2O Trofee ───────────────────────────────────────────────────────────────
# Hvert X2O-loeb har sit eget site (koppenbergcross.be, bollekescross.be ...),
# og x2otrofee.be's forside linker til dem alle. Startlisterne ligger paa
# sitets /renners/ som "Koppenbergcross-Startlist-Men-Elite.pdf" (ejeren pegede
# paa den 2026-10-31). Filnavnet har ingen dato, saa datoen laeses i PDF'ens
# sidefod ("KOPPENBERGCROSS-OUDENAARDE 1/11/2026") — en PDF fra sidste saeson
# maa ikke blive denne saesons startliste.
X2O_BASE = "https://x2otrofee.be"
X2O_IKKE_SITE = re.compile(r"x2otrofee|golazo|sporza|eurosport|nieuwsblad|coca-cola", re.I)
DATO = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")


def hent_fra_x2o(race: dict) -> tuple[bytes | None, str | None, str]:
    """(pdf, url, besked). Loebets site findes ud fra navnet: "X2O Trofee
    Hamme-Zogge - Bollekescross" → bollekescross.be."""
    forside = hent(X2O_BASE + "/")
    if forside is None or not forside.ok:
        return None, None, "x2otrofee.be svarede ikke"
    sites = sorted({u.rstrip("/") for u in re.findall(
        r'href="(https?://(?:www\.)?[a-z0-9\-]+\.be)/?"', forside.text, re.I)
        if not X2O_IKKE_SITE.search(u)})

    # "cross" staar i alle domaenerne og kan ikke skelne loebene fra hinanden.
    navn = (race.get("name") or "").lower().replace("x2o trofee", " ")
    tokens = {t for t in re.split(r"[^a-z]+", navn) if len(t) > 3} - {"cross"}
    traef = [s for s in sites if any(
        t in re.sub(r"^https?://(www\.)?", "", s).split(".")[0] for t in tokens)]
    if len(traef) != 1:
        return None, None, f"loebets site ikke entydigt fundet ({len(traef)} kandidater)"

    side = traef[0] + "/renners/"
    r = hent(side)
    if r is None or not r.ok:
        # Bollekescross (Hamme-Zogge) ligger ikke paa X2O's platform og har
        # ingen /renners/ — 404 dér er "anden opbygning", ikke en nedetid.
        return None, None, f"{side} svarede {r.status_code if r is not None else 'ikke'}"
    pdf = vaelg_elite_pdf(sorted(set(re.findall(r'href="([^"]+\.pdf)"', r.text, re.I))))
    if not pdf:
        return None, None, f"ingen herre-elite-startliste paa {side} endnu"
    p = hent(pdf)
    if p is None or not p.ok:
        return None, None, f"kunne ikke hente {pdf}"

    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    with fitz.open(stream=p.content, filetype="pdf") as doc:
        tekst = " ".join(s.get_text() for s in doc)
    datoer = {f"{a}-{int(m):02d}-{int(d):02d}" for d, m, a in DATO.findall(tekst)}
    if race["start_date"] not in datoer:
        return None, None, (f"PDF'en er dateret {', '.join(sorted(datoer)) or 'intet'}, "
                            f"ikke {race['start_date']}")
    return p.content, pdf, f"{side} ({race['start_date']})"


def vaelg_elite_pdf(pdfs: list[str]) -> str | None:
    for moenster in ELITE_MOENSTRE:
        for p in pdfs:
            if re.search(r"startli[sj]t", p, re.I) and moenster.search(p):
                return p
    return None


# ── PDF-laesning ─────────────────────────────────────────────────────────────

def laes_startliste(pdf_bytes: bytes) -> list[dict]:
    """Rytterne ud af arrangoerens PDF.

    Teksten kommer ud som én kolonnevaerdi pr. linje. En raekke genkendes paa,
    at et startnummer efterfoelges af navn, et 8-12-cifret UCI-ID og en
    tre-bogstavs nation — tre former, der ikke falder sammen ved et tilfaelde.
    Alt mellem nationen og naeste raekke er holdnavnet, og et tal til sidst er
    UCI-rankingen, som ikke alle ryttere har."""
    try:
        # Pakken hed `fitz` indtil PyMuPDF 1.24 og advarer nu om, at navnet
        # fjernes. Vi beder om det nye navn foerst og falder tilbage, saa
        # agenten virker baade foer og efter den oprydning.
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
    except ImportError as exc:
        # Et manglende bibliotek er en MILJOEFEJL, ikke "ingen startliste
        # endnu". Returnerede vi bare en tom liste, meldte jobbet "OK" og
        # ejeren fik en besked, der saa ud som om kilden var tom — praecis
        # den tavse fejl, run_validator blev bygget for at fange. Meulebeke
        # 2026-10-17: agenten fandt fem PDF'er og kunne ikke aabne én.
        raise RuntimeError(
            "PyMuPDF mangler i miljoeet — tilfoej 'pymupdf' til "
            "requirements.txt og byg workeren igen") from exc

    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        linjer = [x.strip() for side in doc for x in side.get_text().splitlines()
                  if x.strip() and not CHROME.search(x.strip())]

    ryttere: list[dict] = []
    i = 0
    while i < len(linjer) - 3:
        if not (NUM.match(linjer[i]) and UCI_ID.match(linjer[i + 2])
                and NAT.match(linjer[i + 3])):
            i += 1
            continue
        bib, navn, _uci_id, nat = linjer[i:i + 4]
        j = i + 4
        rest: list[str] = []
        while j < len(linjer) and not (
                NUM.match(linjer[j]) and j + 3 < len(linjer)
                and UCI_ID.match(linjer[j + 2]) and NAT.match(linjer[j + 3])):
            rest.append(linjer[j])
            j += 1
        # Et tal til sidst er rankingen — ogsaa naar rytteren ingen klub har.
        # Med "len(rest) > 1" blev Dean Harveys ranking (145) hans holdnavn.
        rank = rest.pop() if rest and NUM.match(rest[-1]) else None
        ryttere.append({
            "bib": int(bib), "navn": navn, "nat": nat,
            "hold": " ".join(rest).strip() or None,
            "uci_rank": int(rank) if rank else None,
        })
        i = j
    return ryttere


# ── Skrivning ────────────────────────────────────────────────────────────────

def find_hold(navn: str | None, cache: dict) -> str | None:
    """Holdet, hvis vi kender det. Vi OPRETTER aldrig et cross-hold: feltet
    "Individueel" og klubnavne som "GMS CYCLING TEAM GLABBEEK" er ikke
    WorldTour-hold, og de ville forurene holdsiderne."""
    if not navn or navn.lower() in ("individueel", "individual", "-"):
        return None
    if navn in cache:
        return cache[navn]
    rows = sb_get("teams", f"slug=eq.{slugify(navn)}&select=id&limit=1")
    cache[navn] = rows[0]["id"] if rows else None
    return cache[navn]


def omvendt_navn(navn: str) -> str:
    """"VAN DE PUTTE Victor" → "Victor VAN DE PUTTE". Efternavnet er ordene
    med store bogstaver; et simpelt split ved første mellemrum ville give
    "DE PUTTE Victor VAN"."""
    ord_ = navn.split()
    efter = [o for o in ord_ if o.isupper() and len(o) > 1]
    for_ = [o for o in ord_ if o not in efter]
    return " ".join(for_ + efter) if efter and for_ else navn


def navne_rotationer(navn: str) -> list[str]:
    """Alle ordstillinger, der bevarer raekkefoelgen: "Mats Vanden Eynde" →
    "Vanden Eynde Mats", "Eynde Mats Vanden". Arrangoer-PDF'erne skriver
    "EFTERNAVN Fornavn", KNWU og PCS "Fornavn Efternavn" — og store bogstaver
    kan ikke bruges til at finde efternavnet ("senn bossaerts" fra KNWU)."""
    ord_ = navn.split()
    return [" ".join(ord_[i:] + ord_[:i]) for i in range(len(ord_))]


def find_eller_opret_rytter(r: dict, kilde: str, toer: bool) -> str | None:
    """Rytteren. PDF'en skriver "EFTERNAVN Fornavn" — samme form som PCS og som
    vores egen database, saa slug'en bliver den samme."""
    slug = slugify(r["navn"])
    # Alle ordstillinger: KNWU skrev "Joran Wyseure", HG Cross-PDF'en
    # "WYSEURE Joran", og med kun ét opslag fik 18 ryttere en dublet
    # (lagt sammen 2026-10-29).
    for s in [slugify(n) for n in navne_rotationer(r["navn"])]:
        rows = sb_get("riders", f"slug=eq.{s}&select=id&limit=1")
        if rows:
            return rows[0]["id"]
    if toer:
        return None
    ny = {"name": r["navn"], "slug": slug, "nationality": iso2(r["nat"]),
          "uci_ranking": r["uci_rank"], "source_url": kilde}
    if not sb_upsert("riders", [ny], conflict="slug"):
        return None
    rows = sb_get("riders", f"slug=eq.{slug}&select=id&limit=1")
    return rows[0]["id"] if rows else None


def markér_kilde_fundet(race: dict, antal: int, kilde: str) -> None:
    """Fortael kataloget, at kilden findes.

    Uden dette blev loebet ved med at staa som "mangler startliste" i
    morgenbeskeden, selv om vi netop havde hentet 57 ryttere — research-agenten
    proever foerst igen efter sin spaerretid. Hente-agenten ved det bedre og med
    det samme, saa den skriver det selv."""
    rows = sb_get("race_data_sources",
                  f"race_id=eq.{race['id']}&data_type=eq.startlist&select=id&limit=1")
    felter = {
        "status": "found", "source_name": "organiser", "url": kilde,
        "verification": {"ryttere": antal, "via": "arrangoer-pdf"},
        "last_attempt_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
    }
    if rows:
        requests.patch(f"{SUPABASE_URL}/rest/v1/race_data_sources?id=eq.{rows[0]['id']}",
                       json=felter, headers=WRITE, timeout=45)
    else:
        sb_upsert("race_data_sources",
                  [{"race_id": race["id"], "data_type": "startlist", **felter}],
                  conflict="race_id,data_type")


def gem(race: dict, ryttere: list[dict], kilde: str, toer: bool) -> int:
    holdcache: dict = {}
    raekker = []
    nye = 0
    for r in ryttere:
        rid = find_eller_opret_rytter(r, kilde, toer)
        if not rid:
            # I en toer koersel oprettes ingen ryttere, saa de ukendte giver
            # None. Tael dem, saa "0 raekker" ikke laeses som en fejl.
            nye += 1
            continue
        raekker.append({
            "race_id": race["id"], "rider_id": rid,
            "team_id": find_hold(r["hold"], holdcache),
            # Navnet gemmes ALTID, ogsaa naar holdet findes i teams: et
            # cross-felt er klubber og smaahold, og uden teksten stod 55 af
            # 57 ryttere som "Ukendt hold".
            "team_name": r["hold"],
            # Cross-rankingen hoerer til startlisten, ikke til rytteren:
            # riders.uci_ranking er landevejsrankingen, og Thibau Nys stod som
            # 666 paa Koppenbergcross 2026, hvor PDF'en sagde 3.
            "uci_rank": r["uci_rank"],
            "bib_number": r["bib"], "status": "active", "source_url": kilde,
        })
    if toer:
        print(f"      {len(raekker)} ryttere kendes allerede, {nye} ville blive oprettet")
        return len(raekker) + nye
    if not raekker:
        return 0
    # Samme loeb kan hentes igen, naar arrangoeren opdaterer PDF'en.
    requests.delete(f"{SUPABASE_URL}/rest/v1/startlists?race_id=eq.{race['id']}",
                    headers=WRITE, timeout=45)
    return len(raekker) if sb_upsert("startlists", raekker, conflict="id") else 0


# ── Hovedloekke ──────────────────────────────────────────────────────────────

def behandl(race: dict, toer: bool) -> bool:
    print(f"\n[{race['slug']}]  {race['start_date']}  ({race.get('category')})")

    # KNWU foerst for de hollandske loeb: struktureret JSON slaar en PDF.
    if (race.get("country_code") or "").upper() == "NL":
        ryttere, kilde = hent_fra_knwu(race)
        if ryttere:
            print(f"    {len(ryttere)} ryttere fra KNWU ({kilde})")
            n = gem(race, ryttere, kilde or "knwu", toer)
            print(f"    {'(toer) ' if toer else ''}{n} startliste-raekker")
            if n and not toer:
                markér_kilde_fundet(race, n, kilde or "knwu")
            return n > 0
        print("    KNWU har ingen startliste endnu — proever arrangoeren")

    if race.get("category") == "Superprestige":
        indhold, pdf, besked = hent_fra_superprestige(race)
        print(f"    superprestige: {besked}")
        if not indhold:
            return False
        return _gem_pdf(race, indhold, pdf, toer)

    if race.get("category") == "X2O Trofee":
        indhold, pdf, besked = hent_fra_x2o(race)
        print(f"    x2o: {besked}")
        if not indhold:
            return False
        return _gem_pdf(race, indhold, pdf, toer)

    side, pdfs = find_loebsside(race)
    if not side:
        kendt = SERIE_SITES.get(race.get("category") or "")
        print("    ingen arrangoerside fundet" if kendt else
              f"    serien '{race.get('category')}' har ingen kendt arrangoerside")
        return False
    print(f"    side: {side}  ({len(pdfs)} pdf)")

    pdf = vaelg_elite_pdf(pdfs)
    if not pdf:
        print("    ingen herre-elite-startliste endnu — kommer typisk i loebsugen")
        return False

    r = hent(pdf)
    if r is None or not r.ok or "pdf" not in (r.headers.get("content-type") or ""):
        print(f"    kunne ikke hente {pdf[:70]}")
        return False
    return _gem_pdf(race, r.content, pdf, toer)


def _gem_pdf(race: dict, indhold: bytes, pdf: str, toer: bool) -> bool:
    ryttere = laes_startliste(indhold)
    if not ryttere:
        print("    PDF'en kunne ikke laeses som en startliste")
        return False
    med_rank = sum(1 for x in ryttere if x["uci_rank"])
    print(f"    {len(ryttere)} ryttere laest ({med_rank} med UCI-ranking)")
    for x in ryttere[:3]:
        print(f"      {x['bib']:>3}  {x['navn']:<28} {x['nat']}  {x['hold'] or '-'}")

    n = gem(race, ryttere, pdf, toer)
    print(f"    {'(toer) ' if toer else ''}{n} startliste-raekker")
    if n and not toer:
        markér_kilde_fundet(race, n, pdf)
    return n > 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--race", help="vores DB-slug")
    ap.add_argument("--alle", action="store_true", help="alle cross-loeb")
    ap.add_argument("--dry-run", action="store_true", dest="toer")
    args = ap.parse_args()

    if not (args.race or args.alle):
        ap.error("vaelg --race <slug> eller --alle")
    if not SUPABASE_URL or not SUPABASE_KEY:
        sys.exit("SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY mangler")

    loeb = cross_loeb(args.race)
    if not loeb:
        # IKKE en fejl. Agenten indgaar i det faelles "startliste"-job, som
        # ogsaa koerer paa landevejsloeb — og dér er der intet at lave. Et
        # exit != 0 ville melde hele jobbet fejlet og sende en Telegram-alarm.
        print(f"{args.race or 'ingen'} er ikke et cykelcross-loeb — springer over")
        return
    print(f"cross_startlist_agent — {len(loeb)} loeb")

    ok = 0
    miljoefejl: str | None = None
    for race in loeb:
        try:
            ok += bool(behandl(race, args.toer))
        except RuntimeError as exc:
            # Miljoefejl rammer ALLE loeb, ikke bare dette. Den skal give en
            # fejlet koersel, saa Telegram-alarmen gaar — ellers ser en
            # manglende afhaengighed ud som "ingen startliste endnu".
            miljoefejl = str(exc)
            print(f"    [MILJOEFEJL] {exc}")
            break
        except Exception as exc:                      # noqa: BLE001
            # Ét loeb maa ikke vaelte hele koerslen — samme grund som i
            # stage_recap_agent efter RES-010.
            print(f"    [fejl] {type(exc).__name__}: {exc}")
    print(f"\nFaerdig: {ok} af {len(loeb)} loeb fik en startliste")
    if miljoefejl:
        sys.exit(f"Afbrudt: {miljoefejl}")


if __name__ == "__main__":
    main()
