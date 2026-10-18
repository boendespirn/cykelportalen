"""
results_agent.py
Scraper etaperesultater og GC-klassement fra PCS for igangvaerende loeb.
Gemmer i startlists-tabellen (status, dnf_stage_number) og opdaterer
gc_position / gc_time_gap i en separat klassementer-tabel hvis den eksisterer.

Korer: python results_agent.py
       python results_agent.py --race giro-d-italia-2026
       python results_agent.py --race giro-d-italia-2026 --stage 15
"""

import os
import re
import sys
import time
import argparse
import requests
from datetime import date
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
# Ovenstående alene virker ikke, da stdouts encoding allerede er låst ved
# interpreter-opstart — samme fix som resten af agents/-scripts bruger.
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
DB   = {**AUTH, "Content-Type": "application/json", "Prefer": "return=minimal"}

DELAY = 1.5


# ── Supabase helpers ──────────────────────────────────────────────────────────

def get_ongoing_races() -> list[dict]:
    today = date.today().isoformat()
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races"
        f"?start_date=lte.{today}&end_date=gte.{today}"
        f"&select=id,name,slug,pcs_url"
        f"&order=start_date.desc&limit=5",
        headers=AUTH,
    )
    return res.json() if res.ok else []


def get_race(slug: str) -> dict | None:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?slug=eq.{slug}&select=id,name,slug,pcs_url,race_type&limit=1",
        headers=AUTH,
    )
    data = res.json()
    return data[0] if res.ok and data else None


def get_latest_finished_stage(race_id: str) -> dict | None:
    today = date.today().isoformat()
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages"
        f"?race_id=eq.{race_id}&date=lte.{today}"
        f"&select=id,stage_number,pcs_stage_url,date"
        f"&order=stage_number.desc&limit=1",
        headers=AUTH,
    )
    data = res.json()
    return data[0] if res.ok and data else None


def get_final_stage_number(race_id: str) -> int | None:
    """Højeste stage_number for løbet — bruges til at afgøre, om en etape er
    den afsluttende, hvilket alene åbner for løbs-niveau-fallback på
    klassementerne (se _fetch_classification_table())."""
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages"
        f"?race_id=eq.{race_id}&select=stage_number"
        f"&order=stage_number.desc&limit=1",
        headers=AUTH,
    )
    data = res.json() if res.ok else []
    return data[0]["stage_number"] if data else None


def get_all_stages(race_id: str) -> list[dict]:
    """Alle etaper for et løb, ældste først — til historisk backfill (--all-stages),
    hvor vi vil have resultater for samtlige etaper, ikke kun den seneste."""
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages"
        f"?race_id=eq.{race_id}"
        f"&select=id,stage_number,pcs_stage_url,source_url,date"
        f"&order=stage_number.asc",
        headers=AUTH,
    )
    return res.json() if res.ok else []


def get_rider_id_by_slug(slug: str) -> str | None:
    # Prøv direkte slug
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/riders?slug=eq.{slug}&select=id&limit=1",
        headers=AUTH,
    )
    data = res.json()
    if res.ok and data:
        return data[0]["id"]
    # PCS bruger firstname-[middlename-]lastname, DB bruger lastname-[middlename-]firstname
    # Flyt første ord til slutningen: "ben-o-connor" → "o-connor-ben"
    parts = slug.split("-")
    if len(parts) >= 2:
        db_slug = "-".join(parts[1:] + [parts[0]])
        res2 = requests.get(
            f"{SUPABASE_URL}/rest/v1/riders?slug=eq.{db_slug}&select=id&limit=1",
            headers=AUTH,
        )
        data2 = res2.json()
        if res2.ok and data2:
            return data2[0]["id"]
    return None


def get_rider_id_by_name(name: str) -> str | None:
    clean = name.strip().upper()
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/riders?name=ilike.{requests.utils.quote(clean)}&select=id&limit=1",
        headers=AUTH,
    )
    data = res.json()
    return data[0]["id"] if res.ok and data else None


def get_rider_id(slug: str, name: str) -> str | None:
    """Prøv slug-opslag først, fallback til navn."""
    return get_rider_id_by_slug(slug) or get_rider_id_by_name(name)


def mark_dnf(race_id: str, rider: dict, stage_number: int) -> None:
    rid = get_rider_id(rider["slug"], rider["name"])
    if not rid:
        return
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/startlists?race_id=eq.{race_id}&rider_id=eq.{rid}",
        json={"status": "DNF", "dnf_stage_number": stage_number},
        headers=DB,
    )


def mark_stage_data_status(stage_id: str, status: str | None) -> None:
    """Markerer, at en etape af faktiske grunde aldrig får fuldstændige data
    (fx aflyst). Læses af race_completeness.py, så admin-dashboardet viser
    "ikke muligt" i stedet for "mangler"."""
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/stages?id=eq.{stage_id}",
        json={"data_status": status},
        headers=DB,
    )


def upsert_stage_results(race_id: str, stage_id: str, top10: list[dict]) -> None:
    """Gemmer etaperesultater (top10) i results-tabellen."""
    rows = []
    last_gap = 0
    for entry in top10:
        rid = get_rider_id(entry["slug"], entry["name"])
        if not rid:
            continue
        pos = entry.get("position")
        time_str = entry.get("time", "")
        secs = parse_time_to_seconds(time_str) if time_str else None
        gap = _resolve_gap(pos == 1, time_str, last_gap)
        last_gap = gap
        rows.append({
            "race_id":          race_id,
            "stage_id":         stage_id,
            "rider_id":         rid,
            "position":         pos,
            "time_seconds":     secs if pos == 1 else None,
            "time_gap_seconds": gap,
        })
    if rows:
        # PostgREST's "resolution="-direktiv virker KUN sammen med on_conflict.
        # Uden den svarer et gensendt resultat 409 og HELE batchen ryger — så en
        # genkørsel kunne aldrig tilføje en manglende eller rette en forkert
        # placering (Vuelta 2026 E5 blev hængende på 9 rækker af netop den grund).
        # merge-duplicates gør det til en ægte upsert: eksisterende rækker
        # opdateres, når PCS retter et resultat efter en nedrykning.
        res = requests.post(
            f"{SUPABASE_URL}/rest/v1/results?on_conflict=race_id,stage_id,rider_id",
            json=rows,
            headers={**DB, "Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        if not res.ok:
            print(f"    [DB FEJL etaperesultat] {res.status_code}: {res.text[:200]}")


def upsert_classification(race_id: str, stage_number: int, classif_type: str, standings: list[dict]) -> None:
    """Gemmer klassement i classifications-tabellen (gc, points, mountains, youth)."""
    requests.delete(
        f"{SUPABASE_URL}/rest/v1/classifications"
        f"?race_id=eq.{race_id}&after_stage_number=eq.{stage_number}&classification_type=eq.{classif_type}",
        headers=DB,
    )
    rows = []
    for entry in standings:
        rid = get_rider_id(entry["slug"], entry["name"])
        if not rid:
            continue
        row = {
            "race_id":             race_id,
            "after_stage_number":  stage_number,
            "classification_type": classif_type,
            "rider_id":            rid,
            "position":            entry.get("position"),
        }
        if "time_gap_seconds" in entry:
            row["time_gap_seconds"] = entry["time_gap_seconds"]
        if "points" in entry:
            row["points"] = entry["points"]
        rows.append(row)
    if rows:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/classifications",
            json=rows,
            headers={**DB, "Prefer": "resolution=ignore-duplicates,return=minimal"},
        )


# ── PCS scraping ──────────────────────────────────────────────────────────────

def parse_time_to_seconds(s: str) -> int | None:
    """'1:23:45' eller '+0:45' → sekunder."""
    s = s.strip().lstrip("+")
    parts = s.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        pass
    return None


def _resolve_gap(is_leader: bool, time_str: str, last_gap: int) -> int:
    """
    PCS udelader (blank celle eller "0:00") tiden for en rytter, der har samme
    tid som rytteren lige før i ranglisten — det betyder IKKE at rytteren har
    samme tid som lederen. Falder derfor tilbage til forrige rækkes gap i
    stedet for at antage 0, når feltet er tomt/uparsérbart.
    """
    if is_leader:
        return 0
    secs = parse_time_to_seconds(time_str) if time_str else None
    return secs if secs else last_gap



def _columns(table) -> dict[str, int]:
    """
    Kolonneindeks pr. `data-code` fra tabellens `<thead>` ({'rnk': 0, 'rider': 7,
    'timelag': 12, …}).

    Læses fra headeren frem for at hardkode indekser: PCS slår kolonner til og
    fra pr. løb (`hide_td*`-klasserne på tabellen), så et fast indeks ville
    pege på et andet felt, så snart en kolonne forsvandt.
    """
    head = table.find("thead")
    if head is None:
        return {}
    return {
        th.get("data-code"): i
        for i, th in enumerate(head.find_all("th"))
        if th.get("data-code")
    }


def _parse_row(row, cols: dict[str, int]) -> dict | None:
    """
    Én tabelrække → {rank, slug, name, time, points}.

    `rank` er rå tekst, fordi feltet rummer både placeringer ("1") og udgange
    ("DNF") — kalderen skelner. Tidsfeltet kan være PCS' ",,", der betyder
    "samme tid som rytteren ovenfor"; det oversættes ikke her, men af
    `_resolve_gap()`, som allerede falder tilbage til forrige rækkes gap.
    """
    tds = row.find_all("td", recursive=False)
    i_rnk = cols.get("rnk")
    i_rider = cols.get("rider")
    if i_rnk is None or i_rider is None or len(tds) <= max(i_rnk, i_rider):
        return None
    link = tds[i_rider].find("a", href=True)
    if not link:
        return None

    def felt(kode: str) -> str:
        i = cols.get(kode)
        return tds[i].get_text(strip=True) if i is not None and len(tds) > i else ""

    # Pointkolonnen heder 'res_pnt' paa PCS i dag; 'pnt' er den gamle kode og
    # beholdes som faldskaerm. Da kolonnen blev omdoebt, blev point laest som 0
    # UDEN at noget fejlede: Tour of Guangxis pointklassement fik 13 ryttere
    # med nul point hver, og rangordenen var dermed vilkaarlig (2026-10-18).
    # 'pnt_won' er dagens udbytte ("+15"), ikke den samlede stilling, og maa
    # aldrig bruges her.
    try:
        point = int(felt("res_pnt") or felt("pnt"))
    except ValueError:
        point = 0
    return {
        "rank":   tds[i_rnk].get_text(strip=True),
        "slug":   link["href"].replace("rider/", "").strip("/"),
        "name":   link.get_text(separator=" ", strip=True).upper(),
        "time":   felt("timelag"),
        "points": point,
    }


def _parse_result_table(table) -> dict:
    """
    Top 10 og udgåede ryttere fra en resultattabel.

    Rækker uden et tal i Rnk er udgange: kun "DNF" rapporteres videre, fordi
    `mark_dnf()` skriver status "DNF", og en DNS/DSQ dermed ville blive gemt
    som noget andet, end den var (CLAUDE.md §6).

    Der læses videre, indtil der er 10 GYLDIGE placeringer — ikke bare de 10
    første rækker. PCS indsætter rækker, der ikke er en placering (nedrykkede
    eller diskvalificerede ryttere), og et fast vindue på 10 rækker koster så
    en rigtig rytter i bunden: Vuelta 2026 E5 fik kun 9, fordi en nedrykning
    skubbede Wout van Aert ud af vinduet.
    """
    cols = _columns(table)
    top10: list[dict] = []
    dnf: list[dict] = []
    for row in (table.find("tbody") or table).find_all("tr"):
        parsed = _parse_row(row, cols)
        if not parsed:
            continue
        rank = parsed["rank"]
        if rank.isdigit():
            if len(top10) < 10:
                top10.append({
                    "position": int(rank),
                    "slug":     parsed["slug"],
                    "name":     parsed["name"],
                    "time":     parsed["time"],
                })
        elif rank.upper() == "DNF":
            dnf.append({"slug": parsed["slug"], "name": parsed["name"]})
    return {"top10": top10, "dnf": dnf}


def _parse_classification(table, med_point: bool) -> list[dict]:
    """
    Top 20 af ét klassement. `med_point` skelner point-/bjergklassementet
    (rangordnet efter point) fra GC og ungdom (rangordnet efter tid).
    """
    cols = _columns(table)
    ud: list[dict] = []
    last_gap = 0
    for row in (table.find("tbody") or table).find_all("tr"):
        if len(ud) >= 20:
            break
        parsed = _parse_row(row, cols)
        if not parsed or not parsed["rank"].isdigit():
            continue
        pos = int(parsed["rank"])
        post = {"position": pos, "slug": parsed["slug"], "name": parsed["name"]}
        if med_point:
            post["points"] = parsed["points"]
        else:
            gap = _resolve_gap(pos == 1, parsed["time"], last_gap)
            last_gap = gap
            post["time_gap_seconds"] = gap
        ud.append(post)
    return ud


def _find_first_visible_table(soup: BeautifulSoup):
    """
    Den rangliste, PCS reelt VISER for den URL, vi har hentet.

    Siden rummer alle fanebladenes tabeller på én gang — etaperesultat, GC,
    point, bjerge, ungdom — men kun den aktive fanes `div.resultCont` står
    UDEN klassen `hide`. Den regel er det eneste pålidelige kendetegn: PCS'
    overskrifter over tabellerne er generiske ("Today", "View full results")
    og indeholder aldrig ordet "gc", mens "point"/"kom" lige så ofte rammer
    dagens mellemspurt som det samlede klassement (RES-004).

    Derfor må klassementerne stadig hentes fra hver sin URL: det er URL'en,
    der afgør hvilken fane der er aktiv, og dermed hvad tabellen betyder.
    """
    for cont in soup.find_all("div", class_="resultCont"):
        if "hide" in (cont.get("class") or []):
            continue
        for table in cont.find_all("table"):
            if table.find("thead") is None:
                continue
            if len(table.find_all("tr")) < 5:
                continue
            return table
    return None


def _fetch_soup(browser, headers: dict, url: str) -> BeautifulSoup:
    """
    Åbner en FRISK page pr. URL (i stedet for at genbruge én page på tværs af
    goto()-kald). PCS' faneblade er client-side navigation på samme
    side-skabelon, og en baggrunds-JS-proces derfra ser ud til aldrig at gå i
    ro igen efter første goto — genbrug af page fik `wait_until="networkidle"`
    til at time ud på alle efterfølgende navigationer (verificeret ved fejl).

    Ventestrategien er `domcontentloaded` + et kort ophold — IKKE `networkidle`.
    PCS' sider holder forbindelser åbne (annoncer og statistik-widgets), så
    "netværket i ro" indtræffer sent eller aldrig: målt hjemmefra tog den
    **24,5 sekunder** mod 4,0 for `domcontentloaded`, altså et halvt sekund
    fra loftet på 25. Fra Railway lå den over, og så timede HVER eneste
    resultathentning ud — Tour of Guangxis etape 1 fik fem forsøg i træk, der
    alle meldte "ingen etaperesultat fundet (muligvis ikke koert endnu)",
    mens resultatet stod på siden hele tiden (2026-10-13).

    Indholdet er det samme med begge strategier (verificeret: 152 rækker).
    """
    page = browser.new_page()
    page.set_extra_http_headers(headers)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=25_000)
        # Tabellerne står i det leverede HTML; opholdet er alene for de få
        # felter, PCS udfylder med JavaScript lige efter indlæsning.
        time.sleep(2)
        return BeautifulSoup(page.content(), "html.parser")
    finally:
        page.close()


def _race_level_url(base_url: str) -> str | None:
    """
    '…/race/tour-de-france/2026/stage-21' → '…/race/tour-de-france/2026'.

    Returnerer None for URL'er uden et /stage-N-led (fx endagsløb), så kalderen
    ikke får en løbs-URL, der peger et helt andet sted hen.
    """
    m = re.match(r"^(.*/race/[^/]+/[^/]+)/stage-[^/]+$", base_url)
    return m.group(1) if m else None


# Fanens navn paa PCS for hvert af de klassementer, vi henter. Bruges til at
# BEKRAEFTE, at en hentet side faktisk viser det klassement, vi tror — se
# _aktiv_fane().
FANE_NAVN = {"gc": "gc", "points": "points", "kom": "kom", "youth": "youth"}


def _aktiv_fane(soup) -> str | None:
    """Hvilket klassement siden selv siger, den viser.

    PCS markerer den valgte fane i sin egen navigation, og det er den eneste
    kilde paa siden, der utvetydigt navngiver tabellen. Etaperesultatsiden har
    ingen klassementsfane aktiv og giver derfor None — praecis den forskel, der
    skal til for at afvise den som klassement.

    Returnerer fanens navn i smaa bogstaver ("gc", "points", "kom", "youth"),
    eller None hvis ingen klassementsfane er aktiv.
    """
    kendte = set(FANE_NAVN.values())
    for a in soup.select("li.cur a, a.cur, .pageSelectNav .cur a"):
        navn = a.get_text(strip=True).lower().rstrip("▼").strip()
        if navn in kendte:
            return navn
    return None


def _nav_klassement_urls(stage_soup, base_url: str) -> dict[str, str]:
    """Klassements-URL'erne, som etapesidens EGEN fanenavigation peger paa.

    Hvorfor vi laeser dem frem for at bygge dem: PCS bruger to forskellige
    URL-former. Tour de France og Giro svarer paa '…/2026/stage-10-kom', mens
    Tour of Guangxi kun svarer paa
    '…/tour-of-guangxi-2026-gc-stage-1-general-classification'. Den byggede
    form gav ingen tabel for Guangxi, og loebet stod derfor med ét eneste
    klassement ud af seks etaper — GC paa sidste etape, som kom ind gennem
    loebs-niveau-faldet (opdaget 2026-10-18).

    Linkene tages kun med, naar href'en utvetydigt navngiver klassementet.
    Fanens TEKST bruges ikke som noegle: Giros GC-fane peger paa en href med
    'points-classification-stage' i, og et opslag paa tekst ville dermed
    skrive den forkerte tabel ind. Hvilket klassement vi faktisk fik, afgoeres
    alene af _aktiv_fane() paa den hentede side.
    """
    moenstre = {
        "gc":     ("general-classification",),
        "points": ("points-classification",),
        "kom":    ("kom-classification", "mountains-classification"),
        "youth":  ("youth-classification",),
    }
    rod = base_url.split("/race/")[0]
    fundet: dict[str, str] = {}
    for a in stage_soup.find_all("a", href=True):
        href = a["href"]
        # 'day-classification' og '-stage' er DAGENS tabel, ikke den
        # akkumulerede stilling. De maa aldrig forveksles med klassementet.
        if "day-classification" in href or href.endswith("-stage"):
            continue
        for noegle, nøgleord in moenstre.items():
            if noegle in fundet:
                continue
            if any(k in href for k in nøgleord):
                fundet[noegle] = href if href.startswith("http")                                  else f"{rod}/{href.lstrip('/')}"
    return fundet


def _fetch_classification_table(browser, headers: dict, base_url: str,
                                suffix: str, is_final_stage: bool,
                                nav_urls: dict[str, str] | None = None):
    """
    Henter tabellen for ét klassement (gc/points/kom/youth).

    PCS' per-etape-URL (…/stage-21-gc) svarer **HTTP 500** for den AFSLUTTENDE
    etape i et etapeløb — der ligger det endelige klassement i stedet på
    løbs-niveau (…/2026/gc). Vi prøver derfor per-etape-URL'en først og falder
    kun tilbage til løbs-URL'en, når dette faktisk ER sidste etape (se RES-005).

    Fallbacken må ALDRIG gælde en vilkårlig etape: løbs-URL'en indeholder det
    ENDELIGE klassement, så en forbigående timeout på fx etape 10 ville ellers
    skrive slutstillingen ind som "efter etape 10" — en tavs datafejl af præcis
    samme slags som den, denne funktion blev skrevet for at fjerne.

    Hver kandidat BEKRAEFTES mod sidens egen aktive fane, foer tabellen
    godtages. Det er det, der goer det forsvarligt at proeve flere URL-former:
    rammer en kandidat en side, der viser noget andet end det bestilte
    klassement, bliver den afvist frem for skrevet i databasen.

    Returnerer None hvis ingen af URL'erne gav en bekraeftet tabel. Kalderen
    skal så lade klassementet stå tomt — aldrig substituere en anden tabel.
    """
    urls = [f"{base_url}-{suffix}"]
    # Etapesidens egen navigation. Staar efter den byggede form, saa de loeb,
    # der virker i dag, henter uaendret fra samme URL som hidtil.
    if nav_urls and suffix in nav_urls:
        urls.append(nav_urls[suffix])
    if is_final_stage:
        race_url = _race_level_url(base_url)
        if race_url:
            urls.append(f"{race_url}/{suffix}")

    ventet = FANE_NAVN.get(suffix)
    for url in urls:
        try:
            soup = _fetch_soup(browser, headers, url)
        except Exception as e:
            print(f"    [{suffix}: {url} fejlede — {type(e).__name__}]")
            continue
        table = _find_first_visible_table(soup)
        if table is None:
            print(f"    [{suffix}: ingen tabel på {url}]")
            continue
        fane = _aktiv_fane(soup)
        # Loebs-niveau-siden (sidste etape) har ikke etapefanerne og giver
        # derfor None. Den er allerede snaevert afgraenset til is_final_stage,
        # saa dér er URL'en selv beviset.
        if ventet and fane is not None and fane != ventet:
            print(f"    [{suffix}: {url} viser '{fane}', ikke '{ventet}' — afvist]")
            continue
        return table
    return None


def scrape_stage_result(pcs_stage_url: str, is_final_stage: bool = False) -> dict:
    """
    Scraper etaperesultat + alle 4 klassementer fra PCS med BeautifulSoup.
    Returnerer: {top10, dnf, gc, points, mountains, youth}

    `is_final_stage` aktiverer løbs-niveau-fallback for klassementerne — se
    _fetch_classification_table().
    """
    result = {"top10": [], "dnf": [], "gc": [], "points": [], "mountains": [],
              "youth": [], "cancelled": False}
    base_url = pcs_stage_url[: -len("/result")] if pcs_stage_url.endswith("/result") else pcs_stage_url
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            soup = _fetch_soup(browser, headers, pcs_stage_url)

            # En aflyst etape har ingen rangliste og får den aldrig. Uden dette
            # ville den for evigt stå som "mangler resultat" i admin-dashboardet
            # — en advarsel, man lærer at ignorere. PCS skriver det ordret på
            # siden (Vuelta 2026 E3: "Race/stage is cancelled." efter at etapen
            # blev afbrudt i hagl på Col de Mont-Louis).
            page_text = soup.get_text(" ", strip=True)
            result["cancelled"] = "stage is cancelled" in page_text.lower()

            stage_table = _find_first_visible_table(soup)

            # ── Endagsløb ────────────────────────────────────────────────────
            # Et endagsløb har ingen klassementer. Uden denne afkortning ville
            # de fire klassementskald gå mod "…/2026-gc" — en URL, der ikke
            # findes, og som kun kan give fire tomme opslag at læse i loggen.
            if "/stage-" not in base_url:
                browser.close()
                if stage_table is not None:
                    parsed = _parse_result_table(stage_table)
                    result["top10"] = parsed["top10"]
                    result["dnf"] = parsed["dnf"]
                return result

            # Et manglende etaperesultat stopper os IKKE her: på en
            # holdenkeltstart er den aktive fane en HOLD-rangliste uden
            # rytterkolonne, og en aflyst etape har slet ingen. Klassementet
            # efter etapen findes i begge tilfælde, og uden dette hoppede vi
            # over det og efterlod et hul i klassementshistorikken (Dauphiné
            # 2026 E3, opdaget 2026-10-13).
            if stage_table is None:
                print("    [intet rytter-resultat på siden — henter kun klassementerne]")

            # Klassementerne hentes hver fra deres egen dedikerede PCS-side
            # (samme URL'er som faneblade-navigationen selv peger på), da
            # klassementstypen ikke pålideligt kan skelnes på samme side som
            # etaperesultatet — se _find_first_visible_table().
            #
            # Tidligere faldt gc_table tilbage på `stage_table`, når GC-siden
            # ikke kunne parses. Det skrev ETAPERESULTATET ind som GC-klassement
            # — TdF 2026 E21 fik således Van der Poel som samlet vinder i stedet
            # for Pogačar (RES-005). Ingen af de fire klassementer må nogensinde
            # substitueres med en anden tabel: hellere tomt end forkert
            # (CLAUDE.md §6 — kan data ikke verificeres, publicér det ikke).
            # Etapesidens fanenavigation er den anden kilde til URL'erne —
            # noedvendig for de loeb, hvor den byggede form ikke svarer, og
            # samtidig den liste, der fortaeller hvilke klassementer loebet
            # OVERHOVEDET har. Tour of Guangxi har fx GC, point og ungdom,
            # men intet bjergklassement; dér skal 'kom' blive tom.
            nav_urls = _nav_klassement_urls(soup, base_url)
            if nav_urls:
                print(f"    [navigation: {', '.join(sorted(nav_urls))}]")

            gc_table        = _fetch_classification_table(browser, headers, base_url, "gc", is_final_stage, nav_urls)
            points_table    = _fetch_classification_table(browser, headers, base_url, "points", is_final_stage, nav_urls)
            mountains_table = _fetch_classification_table(browser, headers, base_url, "kom", is_final_stage, nav_urls)
            youth_table     = _fetch_classification_table(browser, headers, base_url, "youth", is_final_stage, nav_urls)

            browser.close()

        # ── Etaperesultat og udgåede ryttere ─────────────────────────────────
        if stage_table is not None:
            etape = _parse_result_table(stage_table)
            result["top10"] = etape["top10"]
            result["dnf"] = etape["dnf"]

        # ── De fire klassementer ─────────────────────────────────────────────
        # Point- og bjergklassementet rangordnes efter point, GC og ungdom
        # efter tid — derfor `med_point`.
        for nøgle, tabel, med_point in (
            ("gc",        gc_table,        False),
            ("points",    points_table,    True),
            ("mountains", mountains_table, True),
            ("youth",     youth_table,     False),
        ):
            if tabel is not None:
                result[nøgle] = _parse_classification(tabel, med_point)

    except Exception as e:
        print(f"  [Scrape fejl: {e}]")

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def process(race_slug: str | None, stage_number: int | None, all_stages: bool = False) -> None:
    if race_slug:
        races = [get_race(race_slug)]
        races = [r for r in races if r]
    else:
        races = get_ongoing_races()

    print(f"results_agent.py — {date.today().isoformat()}")
    print(f"Behandler {len(races)} loeb\n")

    for race in races:
        print(f"[{race['name']}]")
        race_id  = race["id"]
        pcs_base = race.get("pcs_url", "")

        if stage_number:
            # Hent specifik etapes URL fra DB
            res = requests.get(
                f"{SUPABASE_URL}/rest/v1/stages"
                f"?race_id=eq.{race_id}&stage_number=eq.{stage_number}"
                f"&select=id,stage_number,pcs_stage_url,source_url,date&limit=1",
                headers=AUTH,
            )
            stages = res.json() if res.ok else []
        elif all_stages:
            stages = get_all_stages(race_id)
        else:
            stage = get_latest_finished_stage(race_id)
            stages = [stage] if stage else []

        if not stages:
            print("  Ingen etaper at opdatere")
            continue

        final_sn = get_final_stage_number(race_id)

        # Et endagsløb har ingen /stage-N-URL'er: løbets forside ER etapen.
        # Uden dette byggede nødfaldet nedenfor "…/2026/stage-1/result", som
        # ikke findes, og resultatet blev meldt som "ikke kørt endnu".
        er_endagsloeb = (race.get("race_type") or "").startswith("one")

        for stage in stages:
            sn       = stage["stage_number"]
            # `source_url` er med, fordi de fleste endagsløb har TOM
            # races.pcs_url OG tom stages.pcs_stage_url — den eneste PCS-URL,
            # vi har for dem, står i source_url (samme nødfald som
            # stage_recap_agent.py allerede brugte). Uden den kunne 6 af
            # 2026-sæsonens 21 endagsløb ikke hentes overhovedet.
            pcs_url  = stage.get("pcs_stage_url") or stage.get("source_url")

            if not pcs_url:
                # Byg URL fra race-URL
                if pcs_base:
                    pcs_url = pcs_base.rstrip("/") if er_endagsloeb \
                              else f"{pcs_base.rstrip('/')}/stage-{sn}/result"
                else:
                    print(f"  E{sn}: Ingen PCS-URL")
                    continue

            # Tilfoej /result hvis ikke allerede der
            if not pcs_url.endswith("/result"):
                pcs_url = pcs_url.rstrip("/") + "/result"

            is_final = final_sn is not None and sn == final_sn
            print(f"  E{sn}: Scraper {pcs_url}" + (" (sidste etape)" if is_final else ""))
            data = scrape_stage_result(pcs_url, is_final_stage=is_final)

            if data["cancelled"]:
                print("  -> AFLYST etape ifoelge PCS — markeret, saa den ikke tael"
                      "ler som manglende data")
                mark_stage_data_status(stage["id"], "cancelled")

            if data["top10"]:
                print(f"  -> Top 3: " + " | ".join(
                    f"{r['position']}. {r['name'].split()[-1]}" for r in data["top10"][:3]
                ))
                upsert_stage_results(race_id, stage["id"], data["top10"])
            elif not data["cancelled"]:
                print("  -> Ingen etaperesultat fundet (muligvis ikke koert endnu)")

            if data["dnf"]:
                print(f"  -> DNF: {', '.join(r['name'] for r in data['dnf'][:5])}")
                for rider in data["dnf"]:
                    mark_dnf(race_id, rider, sn)

            if data["gc"]:
                print(f"  -> GC top3: " + " | ".join(
                    f"{r['position']}. {r['name'].split()[-1]}" for r in data["gc"][:3]
                ))
                upsert_classification(race_id, sn, "gc", data["gc"])

            if data["points"]:
                print(f"  -> Points top3: " + " | ".join(
                    f"{r['position']}. {r['name'].split()[-1]}" for r in data["points"][:3]
                ))
                upsert_classification(race_id, sn, "points", data["points"])

            if data["mountains"]:
                print(f"  -> Bjerge top3: " + " | ".join(
                    f"{r['position']}. {r['name'].split()[-1]}" for r in data["mountains"][:3]
                ))
                upsert_classification(race_id, sn, "mountains", data["mountains"])

            if data["youth"]:
                print(f"  -> Ungdom top3: " + " | ".join(
                    f"{r['position']}. {r['name'].split()[-1]}" for r in data["youth"][:3]
                ))
                upsert_classification(race_id, sn, "youth", data["youth"])

            time.sleep(DELAY)

    print("\nFaerdig.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--race",  help="Loeb-slug (default: alle igangvaerende)", default=None)
    parser.add_argument("--stage", type=int, help="Specifik etape (default: seneste afsluttede)", default=None)
    parser.add_argument("--all-stages", action="store_true", help="Alle etaper for løbet (til historisk backfill) i stedet for kun den seneste")
    args = parser.parse_args()
    process(args.race, args.stage, args.all_stages)
