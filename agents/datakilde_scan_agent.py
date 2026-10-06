"""
datakilde_scan_agent.py
Er der kommet data, vi endnu ikke henter?

Hvorfor agenten findes:
  `data_sources.py` svarer på "hvad KAN hentes for dette løb?" — men den læser
  kun VORES EGEN konfiguration. Står et løb ikke i CYCLINGSTAGE_GPX_PAGES,
  melder dashboardet "ingen GPX-kilde", uanset om cyclingstage udgav ruten i
  mellemtiden. Manglen står der så for evigt, og ingen opdager, at den er
  forsvundet.

  Det skete konkret: ARKITEKTUR.md erklærede 2026-07-21 Il Lombardia for helt
  udækket på cyclingstage. 2026-09-25 lagde de ruten op — under CDN-navnet
  "tour-of-lombardy", ikke "il-lombardia", og på løbets egen rute-underside i
  stedet for på den fælles årgangs-index. Begge ting gjorde, at hverken
  konfigurationen eller den oprindelige verifikation kunne finde den. Fire dage
  før løbet stod etapen stadig med distance 0 km.

  Denne agent spørger derfor OPSTRØMS i stedet for i vores egen config.

Den tjekker to ting:

  1. GPX (cyclingstage.com)
     Konfigureret løb  — svarer siden stadig med en GPX? Ellers er kilden rådnet.
     Ukonfigureret løb — findes der en GPX alligevel? Søges via cyclingstages
                         egen søgning, fordi deres slug ofte er et andet end
                         vores ("tour-of-lombardy" vs. "il-lombardia").
     Et fund VERIFICERES: GPX'ens egen længde holdes op mod den officielle
     distance. Uden det ville agenten foreslå en rute, der kunne være et andet
     løb eller en forældet variant — præcis den slags stille fejl, CLAUDE.md §6
     forbyder.

  2. PCS-rutedata
     Har PCS nu distance/start/mål for et løb, hvor vores egen række er tom
     eller UENIG med PCS? Det er dét, der afgør, om "Ræsinfo" er værd at køre.

Agenten SKRIVER INTET — hverken til databasen eller til konfigurationen. Den
rapporterer, og mennesket beslutter. En ny GPX-kilde er en kodeændring, der skal
igennem review (DATA-003, CLAUDE.md §7), og en distance, der bare blev skrevet,
ville ingen kunne spore bagefter.

Køres fra admin-dashboardet ("Datakilde-scan") eller direkte:
    python datakilde_scan_agent.py [--season 2026] [--only il-lombardia-2026]
    python datakilde_scan_agent.py --hele-saesonen
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import sys
import time
from datetime import date, timedelta
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import climb_profile_generator as cpg

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0"
UA_H = {"User-Agent": UA}

CS_BASE = "https://www.cyclingstage.com"

# Hvor langt tilbage et afsluttet løb stadig er værd at scanne. Et løb, der er
# kørt, kan stadig have brug for en rute til sine landingssider, men hele
# historikken ville gøre scanningen langsom uden at flytte noget.
TILBAGE_DAGE = 60

# Højst hvor stor en afvigelse mellem GPX'ens egen længde og den officielle
# distance, før et fund regnes som usikkert. Samme størrelsesorden som
# distancevagten i stage_profile_generator.py (STG-025).
DIST_TOLERANCE_PCT = 6.0

# Pause mellem kald til cyclingstage. Scanningen henter en del sider i serie, og
# vi har ingen grund til at presse en kilde, vi er afhængige af.
PAUSE_SEK = 0.6


# ── Databasen ────────────────────────────────────────────────────────────────

def sb_get(table: str, params: str) -> list:
    res = requests.get(f"{SUPABASE_URL}/rest/v1/{table}?{params}",
                       headers=HEADERS, timeout=30)
    return res.json() if res.ok and isinstance(res.json(), list) else []


def hent_loeb(season: int, hele_saesonen: bool, only: str | None) -> list[dict]:
    """Løbene i scanningens omfang, med deres etaperækker."""
    felter = "id,name,slug,race_type,start_date,end_date,pcs_url"
    if only:
        races = sb_get("races", f"slug=eq.{only}&select={felter}")
    else:
        frm = date(season, 1, 1).isoformat()
        til = date(season, 12, 31).isoformat()
        races = sb_get("races", f"end_date=gte.{frm}&start_date=lte.{til}"
                       f"&select={felter}&order=start_date.asc")
        if not hele_saesonen:
            graense = (date.today() - timedelta(days=TILBAGE_DAGE)).isoformat()
            races = [r for r in races
                     if (r.get("end_date") or r["start_date"]) >= graense]

    for race in races:
        race["stages"] = sb_get(
            "stages", f"race_id=eq.{race['id']}&select=stage_number,distance_km,"
            "start_location,finish_location&order=stage_number.asc")
    return races


def er_endagsloeb(race: dict) -> bool:
    """Begge stavemåder findes i kolonnen ("oneday" fra 2026, "one_day" før)."""
    return (race.get("race_type") or "").startswith("one")


# ── GPX opstrøms ─────────────────────────────────────────────────────────────

def _gpx_links(url: str) -> list[str]:
    """Alle GPX-links på en side, som absolutte URL'er."""
    try:
        res = requests.get(url, headers=UA_H, timeout=25)
    except requests.RequestException:
        return []
    if not res.ok:
        return []
    out = []
    for a in BeautifulSoup(res.text, "html.parser").find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().endswith(".gpx"):
            out.append(href if href.startswith("http")
                       else urljoin("https://cdn.cyclingstage.com", href))
    return out


def verificer_konfigureret(race: dict) -> tuple[str, str]:
    """Svarer den konfigurerede side stadig med en GPX for løbet?

    Bruger get_gpx_url_for_stage(), altså præcis det opslag agenterne selv
    laver — så en "ok" her betyder, at pipelinen faktisk kan hente ruten, og
    ikke blot at siden findes.
    """
    etaper = [s["stage_number"] for s in race["stages"] if s.get("stage_number")]
    proever = [1] if er_endagsloeb(race) or not etaper else etaper[:2]
    for nr in proever:
        try:
            url = cpg.get_gpx_url_for_stage(race["slug"], nr)
        except Exception as e:
            return "FEJL", f"opslaget fejlede: {type(e).__name__}: {e}"
        time.sleep(PAUSE_SEK)
        if url:
            return "OK", url
    return "ROT", ("konfigureret, men siden svarer ikke længere med en GPX "
                   f"(prøvede etape {', '.join(str(n) for n in proever)})")


def _soegeord(race: dict) -> list[str]:
    """Søgeord til cyclingstages egen søgning.

    Deres navne ligner ofte ikke vores: vi kalder løbet "il-lombardia", de
    kalder det "tour-of-lombardy". Derfor søger vi på ord fra navnet frem for på
    slug'en, og lader deres søgemaskine finde siden.
    """
    navn = re.sub(r"\(.*?\)", " ", race["name"])
    ord_ = [o for o in re.split(r"[^\wÀ-ÿ]+", navn) if len(o) > 3]
    if not ord_:
        return []
    # Sponsornavne står først ("ADAC Cyclassics"), så det sidste betydende ord
    # er oftere løbets egentlige navn end det første.
    kandidater = [ord_[-1]]
    if len(ord_) > 1 and ord_[0].lower() != ord_[-1].lower():
        kandidater.append(ord_[0])
    return kandidater


# Ord, der optraeder i snesevis af loebsnavne og derfor intet identificerer.
# Uden dem ville "Tour de Pologne" matche "tour-of-lombardy".
GENERISKE_ORD = {
    "tour", "race", "grand", "prix", "cycliste", "classic", "classica",
    "trophy", "trofeo", "ronde", "giro", "vuelta", "circuit", "cycling",
    "international", "challenge", "cup", "criterium", "women", "men",
}

# Hvor meget to ord skal ligne hinanden. 0,72 rummer sprogvarianter som
# "lombardia"/"lombardy" (0,82) og "milano"/"milan" (0,91) uden at lade
# tilfaeldige ord passere.
NAVN_LIGHED = 0.72


def _ord(tekst: str) -> list[str]:
    return [o.lower() for o in re.split(r"[^\wÀ-ÿ]+", tekst)
            if len(o) > 3 and o.lower() not in GENERISKE_ORD]


def _navne_match(race_navn: str, kandidat_slug: str) -> bool:
    """Ligner kandidat-slug'en overhovedet dette loeb?

    Noedvendigt, fordi cyclingstages soegeresultatside ogsaa indeholder
    navigation og sidebar: et raat "tag alle /<noget>-2026/-links"-greb
    returnerede Omloop Het Nieuwsblad, da vi soegte paa "Lombardia"
    (verificeret 2026-10-06). Distancekontrollen laengere nede ville have
    afvist fundet, men en forkert kandidat koster kald og goer rapporten
    forvirrende at laese.

    Sammenlignes loest, for deres navn er ofte en anden sprogvariant af vores
    ("lombardia" vs. "lombardy"). Derfor difflib frem for en substring-test,
    som ville afvise netop det rigtige svar.
    """
    vores = _ord(race_navn)
    deres = _ord(kandidat_slug.replace("-", " "))
    for a in vores:
        for b in deres:
            if a == b:
                return True
            if len(a) >= 6 and len(b) >= 6 and a[:6] == b[:6]:
                return True
            if difflib.SequenceMatcher(None, a, b).ratio() >= NAVN_LIGHED:
                return True
    return False


def _race_sider(query: str, season: int, race_navn: str) -> list[str]:
    """Kandidat-løbssider fra cyclingstages søgning."""
    try:
        res = requests.get(f"{CS_BASE}/?s={quote_plus(query)}",
                           headers=UA_H, timeout=25)
    except requests.RequestException:
        return []
    if not res.ok:
        return []
    fundet: list[str] = []
    moenster = re.compile(r"^(?:https://www\.cyclingstage\.com)?/([a-z0-9-]+-%d)/?$"
                          % season)
    for href in re.findall(r'href="([^"]+)"', res.text):
        m = moenster.match(href.strip())
        if m and m.group(1) not in fundet and _navne_match(race_navn, m.group(1)):
            fundet.append(m.group(1))
    return [f"{CS_BASE}/{s}/" for s in fundet[:2]]


def _rute_undersider(race_side: str) -> list[str]:
    """Undersider med "route" i stien — der lå Il Lombardias GPX."""
    try:
        res = requests.get(race_side, headers=UA_H, timeout=25)
    except requests.RequestException:
        return []
    if not res.ok:
        return []
    sti = race_side.rstrip("/").split("/")[-1]
    ud: list[str] = []
    for href in re.findall(r'href="([^"]+)"', res.text):
        href = href.strip()
        if sti not in href or "route" not in href.lower():
            continue
        fuld = (href if href.startswith("http") else urljoin(CS_BASE, href)).rstrip("/") + "/"
        if fuld != race_side.rstrip("/") + "/" and fuld not in ud:
            ud.append(fuld)
    return ud[:3]


def find_gpx_opstroems(race: dict, season: int) -> tuple[str, str] | None:
    """Leder efter en GPX for et løb, vi ikke har konfigureret.

    Returnerer (sidens URL, GPX-URL) — sidens URL er den, der skal i
    CYCLINGSTAGE_GPX_PAGES, for det er en side og ikke en fil, agenterne slår op
    i. Filen bruges kun til at verificere fundet.
    """
    for query in _soegeord(race):
        for race_side in _race_sider(query, season, race["name"]):
            time.sleep(PAUSE_SEK)
            for under in [*_rute_undersider(race_side), race_side]:
                time.sleep(PAUSE_SEK)
                for gpx in _gpx_links(under):
                    # Rigtig årgang, og ikke kvindernes parallelløb.
                    if f"/{season}/" not in gpx or "women" in gpx.lower():
                        continue
                    return under, gpx
    return None


def gpx_fakta(url: str) -> tuple[float, float] | None:
    """(længde i km, højdemeter) regnet ud af GPX'ens egne punkter."""
    try:
        res = requests.get(url, headers=UA_H, timeout=60)
    except requests.RequestException:
        return None
    if not res.ok:
        return None
    punkter = cpg.parse_gpx_with_elevation(res.text)
    if len(punkter) < 50:
        return None
    km = cpg.cumulative_distances_km(punkter)[-1]
    stigning = sum(max(0.0, punkter[i + 1][2] - punkter[i][2])
                   for i in range(len(punkter) - 1))
    return km, stigning


# ── PCS opstrøms ─────────────────────────────────────────────────────────────

def pcs_fakta(pcs_url: str) -> dict | None:
    """Distance, højdemeter og start/mål fra PCS' løbsside.

    Læses med requests og ikke Playwright: tal- og bypar står i den rene HTML
    (verificeret 2026-10-06 på Il Lombardia 2026), og en scanning over hele
    sæsonen må ikke koste en browser pr. løb.
    """
    try:
        res = requests.get(pcs_url, headers=UA_H, timeout=25)
    except requests.RequestException:
        return None
    if not res.ok:
        return None

    flad = re.sub(r"<[^>]+>", "|", res.text)
    flad = re.sub(r"[ \t\r\n]+", " ", flad)
    flad = re.sub(r"(\|\s*)+", "|", flad)

    def vaerdi(label: str) -> str | None:
        m = re.search(re.escape(label) + r":\s*\|\s*([^|]{1,60})", flad)
        return m.group(1).strip() if m else None

    def tal(label: str) -> float | None:
        raa = vaerdi(label)
        if not raa:
            return None
        m = re.search(r"[\d.]+", raa.replace(",", "."))
        return float(m.group()) if m else None

    return {
        "distance_km": tal("Distance"),
        "elevation_gain_m": tal("Vertical meters"),
        "start_location": vaerdi("Departure"),
        "finish_location": vaerdi("Arrival"),
    }


def _samme_by(a: str | None, b: str | None) -> bool:
    """Er det den samme by? Sammenlignes løst — PCS og vi staver ikke ens
    ("Como" vs. "Como (Lombardia)", "Montreal" vs. "Montréal")."""
    if not a or not b:
        return True
    tegn = {"é": "e", "è": "e", "ü": "u", "ö": "o", "à": "a", "á": "a", "ô": "o"}

    def norm(s: str) -> str:
        s = s.lower()
        for fra, til in tegn.items():
            s = s.replace(fra, til)
        return re.sub(r"[^a-z]", "", s)

    na, nb = norm(a), norm(b)
    return bool(na) and bool(nb) and (na in nb or nb in na)


def tjek_pcs(race: dict) -> list[str]:
    """Hvad PCS har, som vi ikke har — eller er uenige med.

    Kun endagsløb: for etapeløb står rutedata på etapesiderne og ikke på
    forsiden, og dem henter "Ræsinfo" allerede pr. etape.
    """
    if not race.get("pcs_url") or not er_endagsloeb(race):
        return []
    fakta = pcs_fakta(race["pcs_url"])
    if not fakta:
        return []

    etape = race["stages"][0] if race["stages"] else None
    fund: list[str] = []

    vores_dist = float(etape["distance_km"]) if etape and etape.get("distance_km") else 0.0
    if fakta["distance_km"] and vores_dist <= 0:
        fund.append(f"PCS har distance {fakta['distance_km']:g} km — vi har "
                    + ("0 km" if etape else "ingen etaperække"))
    elif fakta["distance_km"] and abs(fakta["distance_km"] - vores_dist) > 1.0:
        fund.append(f"distance UENIG: vi {vores_dist:g} km, "
                    f"PCS {fakta['distance_km']:g} km")

    if etape:
        for felt, label in (("start_location", "start"), ("finish_location", "mål")):
            vores, deres = etape.get(felt), fakta.get(felt)
            if deres and not vores:
                fund.append(f"PCS har {label} '{deres}' — vi har ingen")
            elif deres and vores and not _samme_by(vores, deres):
                fund.append(f"{label} UENIG: vi '{vores}', PCS '{deres}'")
    return fund


# ── Rapport ──────────────────────────────────────────────────────────────────

def _gpx_afsnit(races: list[dict], season: int) -> tuple[list, list]:
    nye: list[tuple[str, str, str]] = []
    raadne: list[tuple[str, str]] = []
    konfigureret = cpg.CYCLINGSTAGE_GPX_PAGES

    for race in races:
        slug = race["slug"]
        if slug in konfigureret:
            dom, detalje = verificer_konfigureret(race)
            if dom == "OK":
                print(f"  ok     {slug}")
            else:
                print(f"  {dom:<6} {slug} — {detalje}")
                if dom == "ROT":
                    raadne.append((slug, detalje))
            continue

        fund = find_gpx_opstroems(race, season)
        if not fund:
            print(f"  -      {slug} — ingen GPX fundet opstrøms")
            continue

        side, gpx = fund
        fakta = gpx_fakta(gpx)
        if not fakta:
            print(f"  ?      {slug} — GPX fundet, men kunne ikke læses: {gpx}")
            continue
        km, stigning = fakta

        # Den officielle distance er kontrollen. Vores egen række er førstevalg;
        # er den tom (netop tilfældet, når et løb mangler data), spørges PCS.
        officiel = None
        if race["stages"] and race["stages"][0].get("distance_km"):
            officiel = float(race["stages"][0]["distance_km"]) or None
        if officiel is None and race.get("pcs_url"):
            officiel = (pcs_fakta(race["pcs_url"]) or {}).get("distance_km")

        if officiel:
            afvig = abs(km - officiel) / officiel * 100
            if afvig > DIST_TOLERANCE_PCT:
                print(f"  ?      {slug} — GPX fundet, men længden passer ikke: "
                      f"{km:.1f} km mod officielle {officiel:g} km "
                      f"({afvig:.1f}% afvigelse) — se {gpx}")
                continue
            tjek = f"{km:.1f} km mod officielle {officiel:g} km ({afvig:.1f}% afvigelse)"
        else:
            tjek = f"{km:.1f} km — ingen officiel distance at kontrollere mod"

        print(f"  NY     {slug}")
        print(f"         side:  {side}")
        print(f"         fil:   {gpx}")
        print(f"         tjek:  {tjek}, +{stigning:.0f} højdemeter")
        nye.append((slug, side, tjek))

    return nye, raadne


def main() -> int:
    p = argparse.ArgumentParser(description="Scanner datakilderne for nyt materiale")
    p.add_argument("--season", type=int, default=date.today().year)
    p.add_argument("--only", default=None, help="Kun dette løbs-slug")
    p.add_argument("--hele-saesonen", action="store_true",
                   help=f"Medtag også løb afsluttet for mere end {TILBAGE_DAGE} dage siden")
    args = p.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("FEJL: SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY mangler i .env")
        return 1

    races = hent_loeb(args.season, args.hele_saesonen, args.only)
    if not races:
        print("Ingen løb i omfanget — intet at scanne.")
        return 0

    print("=" * 70)
    print(f"DATAKILDE-SCAN · sæson {args.season} · {date.today().isoformat()}")
    print(f"{len(races)} løb i omfanget"
          + ("" if args.hele_saesonen or args.only
             else f" (afsluttet inden for {TILBAGE_DAGE} dage og frem)"))
    print("=" * 70)

    print("\nGPX (cyclingstage.com)")
    print("-" * 70)
    nye, raadne = _gpx_afsnit(races, args.season)

    print("\nPCS-rutedata (endagsløb)")
    print("-" * 70)
    pcs_nyt: list[tuple[str, list[str]]] = []
    for race in races:
        fund = tjek_pcs(race)
        if fund:
            print(f"  NYT    {race['slug']}")
            for f in fund:
                print(f"         - {f}")
            pcs_nyt.append((race["slug"], fund))
    if not pcs_nyt:
        print("  (intet nyt — vores rækker stemmer med PCS)")

    print("\n" + "=" * 70)
    print("OPSUMMERING")
    print(f"  {len(nye)} ny(e) GPX-kilde(r) · {len(raadne)} rådnet · "
          f"{len(pcs_nyt)} løb med nye PCS-data")

    if nye:
        print("\n  Næste skridt — tilføj i agents/climb_profile_generator.py "
              "(CYCLINGSTAGE_GPX_PAGES):")
        for slug, side, _ in nye:
            print(f'      "{slug}": "{side}",')
        print("  Kræver en kodeændring og et deploy — agenten skriver det ikke selv.")
    if raadne:
        print("\n  Rådne kilder skal rettes, ellers springer pipelinen trinnet "
              "stille over:")
        for slug, detalje in raadne:
            print(f"      {slug}: {detalje}")
    if pcs_nyt:
        print('\n  Kør "Ræsinfo" på disse løb for at hente det ind:')
        for slug, _ in pcs_nyt:
            print(f"      {slug}")
    if not (nye or raadne or pcs_nyt):
        print("  Intet nyt. Alle konfigurerede kilder svarer, og intet løb "
              "mangler data, som kilderne kan dække.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
