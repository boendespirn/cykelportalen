"""
stage_recap_agent.py
Skriver et kort, dansk referat af HVORDAN en etape forløb ("stage_recap") ud fra
ProCyclingStats' LiveStats-tidslinje — den løbende kommentering, der ligger på
…/race/<løb>/<år>/stage-N/live.

Hvorfor: etapesiden viser i forvejen etaperesultat og klassement, men ikke
hvordan løbet udviklede sig. En bruger, der googler "vuelta etape 14 hvad skete
der", skal kunne lande på vores etapeside og få svaret med det samme — det gør
landingssiden komplet (CLAUDE.md §1).

Kilde og copyright (CLAUDE.md §7):
  PCS' kommentarer bruges UDELUKKENDE som faktagrundlag. Referatet skrives om
  til original dansk tekst — kommentarlinjer kopieres aldrig direkte, og
  kildeteksten gemmes ikke i databasen.

Sådan hentes hele tidslinjen ("load more"):
  Live-siden viser kun de ~30 nyeste hændelser. Knappen "view more events"
  (a.ViewFullTimeline med data-last_seqnr) kalder
  POST /rce/livestats_viewmore5b.php {action:timeline, race:<id>, seqnr:<n>},
  som svarer med resten af tidslinjen som rå <li>-HTML. Vi kalder samme
  endpoint direkte i stedet for at klikke i en browser — samme data, ingen
  Playwright, og siden kan hentes med almindelig requests.

Støjfiltrering:
  Tidslinjen er ~80% PCS-statistik-widgets (grafer, tabeller, spilreklame) og
  ~20% faktisk løbsreferat. De to typer kan skelnes strukturelt: statistik-
  indslag indeholder altid en <table>, en div.chartCont, en div.bar-cont eller
  en div.infoSnippet. Rene løbshændelser ("Split in peloton", "The break is
  caught by the peloton") indeholder kun tekst. Enkelte tabel-indslag ER
  relevante (feltets sammensætning, mellemspurt, resultatlisten) og hentes
  via en eksplicit whitelist.

Krav:
  - ANTHROPIC_API_KEY i .env

Kør:
  python agents/stage_recap_agent.py --race la-vuelta-ciclista-a-espana-2026 --stage 16
  python agents/stage_recap_agent.py --race la-vuelta-ciclista-a-espana-2026 --stages 1-16
  python agents/stage_recap_agent.py --race la-vuelta-ciclista-a-espana-2026 --all-stages --force
  python agents/stage_recap_agent.py --race ... --stage 16 --dry-run   (skriver ikke til DB)

Re-run er sikkert: uden --force springes etaper med et eksisterende referat over.
"""

import os
import sys
import io
import re
import time
import argparse
import requests
from bs4 import BeautifulSoup
from anthropic import Anthropic
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL  = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY  = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")

READ_HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
DB_HEADERS   = {**READ_HEADERS, "Content-Type": "application/json", "Prefer": "return=minimal"}

PCS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}
VIEWMORE_URL = "https://www.procyclingstats.com/rce/livestats_viewmore5b.php"

MODEL = "claude-sonnet-5"   # referatet er sidens redaktionelle indhold — kvalitet før pris
# Rigeligt loft: modellen kan indlede med en thinking-blok, og et for lavt loft
# afhugger referatet midt i en sætning (set på E12 og E15 ved 900 tokens).
MAX_TOKENS = 2500
DELAY = 1.0                 # sekunder mellem etaper (skåner PCS)

# Mindste antal reelle løbshændelser, før vi overhovedet skriver et referat.
# Under dette har feedet ikke nok at fortælle, og vi lader hellere feltet stå
# tomt end at digte (CLAUDE.md §6).
MIN_EVENTS = 12


# ── PCS: hent hele LiveStats-tidslinjen ───────────────────────────────────────

def live_url(pcs_stage_url: str) -> str:
    """'…/stage-16' eller '…/stage-16/result' → '…/stage-16/live'."""
    base = pcs_stage_url.rstrip("/")
    for suffix in ("/result", "/live"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return base + "/live"


def fetch_timeline_html(url: str) -> list[str]:
    """
    Returnerer HTML-fragmenter, der tilsammen udgør HELE tidslinjen:
    live-sidens egen <ul class="timeline3"> plus alle "view more events"-batches.
    """
    r = requests.get(url, headers=PCS_HEADERS, timeout=40)
    r.raise_for_status()
    page = r.text
    fragments = [page]

    race_id = re.search(r"var id = (\d+);", page)
    if not race_id:
        return fragments
    race_id = race_id.group(1)

    seqnr = re.search(r'data-last_seqnr="(\d+)"', page)
    # Maks. 10 batches — endpointet leverer i praksis resten i ét svar, men et
    # loft forhindrer en uendelig løkke, hvis PCS ændrer paginering.
    for _ in range(10):
        if not seqnr:
            break
        resp = requests.post(
            VIEWMORE_URL,
            data={"action": "timeline", "race": race_id, "seqnr": seqnr.group(1)},
            headers={**PCS_HEADERS, "X-Requested-With": "XMLHttpRequest", "Referer": url},
            timeout=40,
        )
        if not resp.ok or not resp.text.strip():
            break
        fragments.append(resp.text)
        seqnr = re.search(r'data-last_seqnr="(\d+)"', resp.text)

    return fragments


# ── Parsing og støjfiltrering ─────────────────────────────────────────────────

# Tabel-indslag der ER en del af løbsreferatet (alt andet tabel-indhold er
# PCS-statistik og kasseres).
# Bevidst snæver: PCS har snesevis af tabeller om "riders in break" (karriere-
# point, udtale af navne, sæsonresultater), som intet fortæller om løbets gang.
# Kun sammensætningen af en gruppe, spurtresultater og de to resultatlister.
TABLE_WHITELIST = re.compile(
    r"^composition of|^results of |^preliminary results|"
    r"^general classification after|^results (top|of the)",
    re.I,
)

# Tekst-indslag uden graf/tabel, der alligevel er reklame eller trivia.
TEXT_DENYLIST = [
    re.compile(p, re.I) for p in (
        r"pcs game", r"pcs pro", r"membership", r"procyclingstats",
        r"^welcome at", r"thanks for following",
        r"we will be back", r"^on this day in", r"can score (his|her)",
        r"^it is the \d+", r"has won at least", r"has \d+ career wins",
        r"^from the \d+ races", r"^out of \d+ results", r"^\d+(\.\d+)?% of",
        r"world championships", r"points per stage accumulation",
        r"^number of ", r"^the number of ", r"^the average (speed|number) in|^the percentage of",
        r"^temperature during the stage", r"^the profile of the",
        r"has won \d+% of", r"^average age of", r"^\d+ kilometers out of",
        r"vertical meters today",
        # Andre løb, der slutter samtidig — intet med denne etape at gøre
        r"has just finished", r"^happy birthday",
    )
]

# Vejr-indslag ligger i en infoSnippet (ellers støj), men er reel farve til et
# referat — især i en Vuelta med 40 grader.
WEATHER_KEEP = re.compile(r"(temperature is|wind speed is)", re.I)


def _has(el, selector: str) -> bool:
    return el.select_one(selector) is not None


def parse_events(fragments: list[str]) -> list[dict]:
    """
    Samler alle <li class="event"> på tværs af fragmenter, fjerner dubletter på
    data-seqnr og returnerer dem kronologisk (ældst først — PCS viser nyest
    først, og et referat læses forlæns).
    """
    seen: dict[int, dict] = {}
    for frag in fragments:
        soup = BeautifulSoup(frag, "html.parser")
        for li in soup.find_all("li", class_="event"):
            seq = li.get("data-seqnr")
            if seq is None or not seq.isdigit():
                continue
            cont = li.find("div", class_="cont")
            text_el = li.find("div", class_="textCont")
            if cont is None or text_el is None:
                continue
            text = text_el.get_text(" ", strip=True)
            if not text:
                continue

            marker_el = li.find("div", class_="bol")
            marker = marker_el.get_text(strip=True) if marker_el else ""

            is_stat_widget = (
                _has(cont, "table") or _has(cont, "div.chartCont")
                or _has(cont, "div.bar-cont") or _has(cont, "div.infoSnippet")
            )
            keep, extra = _classify(cont, text, is_stat_widget)
            if not keep:
                continue

            seen[int(seq)] = {"marker": marker, "text": text, "extra": extra}

    return [seen[k] for k in sorted(seen)]


def _classify(cont, text: str, is_stat_widget: bool) -> tuple[bool, str]:
    """Afgør om et indslag er løbsreferat, og hent evt. et kompakt tabeluddrag."""
    if is_stat_widget:
        if _has(cont, "table") and TABLE_WHITELIST.search(text):
            return True, _table_excerpt(cont)
        if _has(cont, "div.infoSnippet") and WEATHER_KEEP.search(text):
            return True, ""
        return False, ""
    if any(p.search(text) for p in TEXT_DENYLIST):
        return False, ""
    return True, ""


def _table_excerpt(cont, max_rows: int = 10) -> str:
    """Kompakt gengivelse af de første rækker i et whitelistet tabel-indslag."""
    table = cont.select_one("table")
    if table is None:
        return ""
    rows = []
    for tr in table.find_all("tr")[:max_rows]:
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if cells:
            rows.append(" · ".join(cells[:5]))
    return "\n".join(rows)


def format_feed(events: list[dict], max_chars: int = 14000) -> str:
    """Tidslinjen som ren tekst med km-til-mål-markør foran hver hændelse."""
    lines = []
    for e in events:
        marker = e["marker"] or "-"
        lines.append(f"[{marker}] {e['text']}")
        if e["extra"]:
            lines.append("   " + e["extra"].replace("\n", "\n   "))
    feed = "\n".join(lines)
    return feed[:max_chars]


# ── Database ──────────────────────────────────────────────────────────────────

def get_race(slug: str) -> dict | None:
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?slug=eq.{slug}&select=id,name,slug&limit=1",
        headers=READ_HEADERS,
    )
    data = r.json() if r.ok else []
    return data[0] if data else None


def get_stages(race_id: str, stage_numbers: list[int] | None, force: bool) -> list[dict]:
    recap_filter = "" if force or stage_numbers else "&stage_recap=is.null"
    stage_filter = ""
    if stage_numbers:
        stage_filter = "&stage_number=in.(" + ",".join(str(n) for n in stage_numbers) + ")"
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages"
        f"?race_id=eq.{race_id}"
        f"&select=id,stage_number,date,distance_km,stage_type,start_location,"
        f"finish_location,elevation_gain_m,pcs_stage_url,source_url,stage_recap"
        f"{recap_filter}{stage_filter}&order=stage_number.asc&limit=100",
        headers=READ_HEADERS,
    )
    r.raise_for_status()
    return r.json()


def get_stage_top5(stage_id: str) -> list[dict]:
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/results"
        f"?stage_id=eq.{stage_id}&select=position,time_gap_seconds,riders(name)"
        f"&order=position.asc&limit=5",
        headers=READ_HEADERS,
    )
    return r.json() if r.ok and isinstance(r.json(), list) else []


def get_gc_top3(race_id: str, stage_number: int) -> list[dict]:
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/classifications"
        f"?race_id=eq.{race_id}&after_stage_number=eq.{stage_number}"
        f"&classification_type=eq.gc&select=position,time_gap_seconds,riders(name)"
        f"&order=position.asc&limit=3",
        headers=READ_HEADERS,
    )
    return r.json() if r.ok and isinstance(r.json(), list) else []


def patch_recap(stage_id: str, recap: str) -> bool:
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/stages?id=eq.{stage_id}",
        json={"stage_recap": recap},
        headers=DB_HEADERS,
    )
    if not r.ok:
        print(f"    [DB FEJL] {r.status_code}: {r.text[:200]}")
    return r.ok


# ── Claude ────────────────────────────────────────────────────────────────────

SYSTEM = (
    "Du skriver etapereferater til klassementet.dk, en dansk cykelportal. "
    "Du skriver i datid, i nøgternt dansk cykelkommentator-sprog — ingen clickbait, "
    "ingen superlativer uden dækning, ingen tomme fyldsætninger. "
    "Du funderer dig UDELUKKENDE i de oplyste fakta. Opfind aldrig navne, tal, "
    "angreb eller hændelser, der ikke fremgår af kilden — er du i tvivl, udelad det. "
    "Kilden er en engelsk live-kommentering skrevet af andre: gengiv fakta, men "
    "formulér alt på ny på dansk. Kopiér aldrig sætninger. "
    "Rytternavne skrives 'Fornavn Efternavn' (kilden skriver 'EFTERNAVN Fornavn'). "
    "Svar KUN med referatteksten i almindelig prosa — ingen overskrift, ingen "
    "markdown, ingen indledning som 'Her er referatet'."
)


def build_prompt(race_name: str, stage: dict, top5: list[dict],
                 gc_top3: list[dict], feed: str) -> str:
    def standings(rows: list[dict]) -> str:
        out = []
        for row in rows:
            rider = (row.get("riders") or {}).get("name", "?")
            gap = row.get("time_gap_seconds")
            gap_txt = "vinder/fører" if not gap else f"+{gap} sek."
            out.append(f"  {row.get('position')}. {rider} ({gap_txt})")
        return "\n".join(out) if out else "  (ikke tilgængeligt)"

    return f"""Skriv et referat af, hvordan denne etape forløb.

Løb: {race_name}
Etape {stage.get('stage_number')}: {stage.get('start_location', '?')} → {stage.get('finish_location', '?')}
Dato: {stage.get('date', '?')} | Distance: {stage.get('distance_km', '?')} km | \
Type: {stage.get('stage_type', '?')} | Højdemeter: {stage.get('elevation_gain_m', '?')}

Etapens top 5 (vores egen verificerede database — brug PRÆCIS disse navne og placeringer):
{standings(top5) if top5 else
 "  INTET OFFICIELT RESULTAT. Etapen har ingen rangliste i vores database — "
 "typisk fordi den blev aflyst, afbrudt eller neutraliseret. Nævn ALDRIG en "
 "etapevinder, og skriv i stedet hvad kilden fortæller om, hvorfor etapen ikke "
 "blev afgjort."}

Samlet klassement efter etapen (vores egen verificerede database):
{standings(gc_top3)}

Løbende kommentering fra etapen (engelsk kilde, kronologisk). Sådan læses den:
- Markøren i kantet parentes forrest på linjen er KM TIL MÅL på det tidspunkt.
  "P" betyder før start, "F" efter målstregen, og "45m"/"3h" er tid til start.
- Et tal i parentes EFTER navnet på en spurt eller stigning — fx
  "Sprint | Tivenys (114.7 km)" — er punktets afstand fra STARTEN, ikke til mål.
  Forveksl aldrig de to.
- Regn ikke afstande, tidsforskelle eller hastigheder ud selv. Brug kun tal, der
  står direkte i kilden, og udelad tallet, hvis det ikke gør det.

{feed}

Skriv 3-4 afsnit på dansk:
1) hvordan etapen blev åbnet, og hvem der kom med i udbruddet
2) hvordan løbet udviklede sig undervejs (styring i feltet, tidsforskelle,
   styrt, mellemspurt, afgørende stigninger — kun det, kilden faktisk nævner)
3) hvordan finalen og afgørelsen forløb
4) hvad etapen betød for det samlede klassement (kun hvis kilden eller
   klassementet ovenfor giver belæg for det)

Nævn km-til-mål, hvor det gør referatet konkret. Hold det stramt: cirka
200-300 ord i alt. Start direkte med referatet."""


def clean(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```\w*\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1]
    return text.strip()


def call_claude(client: Anthropic, race_name: str, stage: dict, top5: list[dict],
                gc_top3: list[dict], feed: str) -> str | None:
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM,
            # Ingen temperature: parameteren er udfaset for Claude 5-modellerne
            # og giver HTTP 400.
            messages=[{"role": "user",
                       "content": build_prompt(race_name, stage, top5, gc_top3, feed)}],
        )
        # Et afhugget svar er et halvt referat midt i en sætning — det må
        # aldrig nå databasen (CLAUDE.md §6: hellere tomt end forkert).
        if resp.stop_reason == "max_tokens":
            print("    [AFHUGGET] svaret nåede token-loftet — intet skrevet")
            return None
        # Svaret kan indledes med en thinking-blok; teksten ligger i den
        # første text-blok, ikke nødvendigvis i content[0].
        text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "")
        return clean(text) or None
    except Exception as e:
        print(f"    [API FEJL] {e}")
        return None


# ── Hoved ─────────────────────────────────────────────────────────────────────

def run(race_slug: str, stage_numbers: list[int] | None, force: bool,
        dry_run: bool, dump_dir: str | None) -> None:
    if not dry_run and not ANTHROPIC_KEY:
        print("FEJL: ANTHROPIC_API_KEY mangler i .env")
        sys.exit(1)

    race = get_race(race_slug)
    if not race:
        print(f"FEJL: løb '{race_slug}' ikke fundet i databasen")
        sys.exit(1)

    stages = get_stages(race["id"], stage_numbers, force)
    print(f"stage_recap_agent.py — {race['name']}")
    print(f"{len(stages)} etape(r) at behandle\n")
    if not stages:
        print("Ingen etaper mangler et referat.")
        return

    client = Anthropic(api_key=ANTHROPIC_KEY) if ANTHROPIC_KEY else None
    ok = skipped = failed = 0

    for stage in stages:
        n = stage["stage_number"]
        print(f"[E{n}] {stage.get('start_location')} → {stage.get('finish_location')}")

        if stage.get("stage_recap") and not force:
            print("    Har allerede et referat — springes over")
            skipped += 1
            continue

        pcs_url = stage.get("pcs_stage_url") or stage.get("source_url")
        if not pcs_url:
            print("    Ingen PCS-URL — springes over")
            skipped += 1
            continue

        url = live_url(pcs_url)
        try:
            fragments = fetch_timeline_html(url)
        except requests.RequestException as e:
            print(f"    [HENT FEJL] {type(e).__name__}: {e}")
            failed += 1
            continue

        events = parse_events(fragments)
        print(f"    {len(events)} løbshændelser fra {url}")

        if dump_dir:
            os.makedirs(dump_dir, exist_ok=True)
            with open(os.path.join(dump_dir, f"stage-{n:02d}-feed.txt"), "w", encoding="utf-8") as f:
                f.write(format_feed(events, max_chars=10**9))

        if len(events) < MIN_EVENTS:
            print(f"    For få hændelser (<{MIN_EVENTS}) — intet referat skrevet")
            skipped += 1
            continue

        # Et manglende etaperesultat er ikke altid en fejl: en aflyst eller
        # neutraliseret etape (fx Vuelta 2026 E3, afbrudt i uvejr) har ingen
        # rangliste, men har stadig en tidslinje, der forklarer hvorfor — og
        # det er præcis dét, en bruger søger efter. Vi skriver derfor referatet
        # alligevel og gør modellen eksplicit opmærksom på, at der intet
        # klassificeret resultat er, så den ikke opfinder en vinder.
        top5 = get_stage_top5(stage["id"])
        if not top5:
            print("    Intet etaperesultat i DB — skriver referat uden resultatliste")

        gc_top3 = get_gc_top3(race["id"], n)
        feed = format_feed(events)

        if dry_run:
            print(f"    [DRY-RUN] feed = {len(feed)} tegn — intet kald, intet skrevet")
            continue

        recap = call_claude(client, race["name"], stage, top5, gc_top3, feed)
        if not recap:
            failed += 1
            continue

        if patch_recap(stage["id"], recap):
            print(f"    OK ({len(recap)} tegn)")
            ok += 1
        else:
            failed += 1

        time.sleep(DELAY)

    print(f"\nFærdig: {ok} skrevet, {skipped} sprunget over, {failed} fejl")


def parse_stage_arg(stage: int | None, stages: str | None, all_stages: bool) -> list[int] | None:
    if all_stages:
        return None
    if stage:
        return [stage]
    if stages:
        m = re.fullmatch(r"(\d+)-(\d+)", stages.strip())
        if m:
            return list(range(int(m.group(1)), int(m.group(2)) + 1))
        return [int(x) for x in stages.split(",") if x.strip()]
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--race", required=True, help="DB-slug, fx la-vuelta-ciclista-a-espana-2026")
    parser.add_argument("--stage", type=int, default=None, help="Kun denne etape")
    parser.add_argument("--stages", default=None, help="Interval eller liste, fx 1-16 eller 3,7,9")
    parser.add_argument("--all-stages", dest="all_stages", action="store_true",
                        help="Alle etaper uden referat")
    parser.add_argument("--force", action="store_true", help="Overskriv eksisterende referater")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true",
                        help="Hent og filtrér tidslinjen, men kald ikke Claude og skriv ikke til DB")
    parser.add_argument("--dump-dir", dest="dump_dir", default=None,
                        help="Gem den filtrerede tidslinje pr. etape som tekstfil (fejlsøgning)")
    args = parser.parse_args()

    if not (args.stage or args.stages or args.all_stages):
        print("FEJL: angiv --stage N, --stages 1-16 eller --all-stages")
        sys.exit(1)

    run(args.race, parse_stage_arg(args.stage, args.stages, args.all_stages),
        args.force, args.dry_run, args.dump_dir)
