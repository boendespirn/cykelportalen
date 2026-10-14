"""
datakilde_research_agent.py — finder og registrerer datakilder pr. loeb (DATA-011).

Svarer paa "har dette loeb de kilder, vi skal bruge — og hvis ikke, findes de?"
Modstykket til `datakilde_scan_agent.py`, som kun tjekker to kildetyper mod vores
egen konfiguration og aldrig skriver. Denne vedligeholder en tilstand i
`race_data_sources`, som er baade katalog OG forsoegslog. Det er forsoegsloggen,
der goer prioriteringen mulig: aldrig-forsoegte huller foerst, derefter dem med
aeldst forsoeg.

PRISMODELLEN ER ARKITEKTUREN. Trin 1-3 og 5-6 i standardproceduren
(docs/datakilde-research-plan.md) er ren HTTP uden LLM og koster ingenting.
Claude kaldes KUN, naar de deterministiske probes har givet op — og kun inden
for lofterne i LIMITS. To ting holder prisen nede:

  * Systemprompten holdes lille med vilje. Prompt-caching er derfor hverken
    brugt eller noedvendig (under modellens minimumspraefiks goer den alligevel
    ingenting, og en lille prompt sparer mere end en cachet stor ville).
  * Raa sider gaar ALDRIG ind i en prompt. Guangxis JS-bundle var 776 KB;
    API-vaerten findes med et regex her i Python, og Claude ser kun resultatet.

Brug:
    py agents/datakilde_research_agent.py --seed --write      # opret raekker
    py agents/datakilde_research_agent.py --run --write       # koeen, uden LLM
    py agents/datakilde_research_agent.py --run --write --use-llm
    py agents/datakilde_research_agent.py --status            # hvad mangler hvor

Uden --write skrives intet; agenten viser kun, hvad den ville gemme.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from difflib import SequenceMatcher
from urllib.parse import quote

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SB = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129 Safari/537.36")

# ── Lofter ───────────────────────────────────────────────────────────────────
# Spaerretiden er den egentlige begraensning (ét forsoeg pr. maaned pr. hul);
# lofterne her er en ekstra sikring, saa en loekke ikke kan aede budgettet paa
# én nat. Daglig koersel x MAX_LLM_CALLS_PER_RUN er det absolutte maanedsloft.
LIMITS = {
    "MAX_RACES_PER_RUN": 40,         # hvor mange loeb koeen maa roere pr. koersel
    "MAX_PROBES_PER_RUN": 120,       # gratis HTTP-probes
    "MAX_LLM_CALLS_PER_RUN": 10,     # ~0,05 USD stykket
    "MAX_SEARCHES_PER_LLM_CALL": 3,  # 0,01 USD pr. soegning
    "MAX_LLM_CALLS_PER_MONTH": 150,  # ~7,50 USD/md. absolut loft
    "HTTP_TIMEOUT": 25,
}

MODEL_TRIAGE = "claude-haiku-4-5"

SOURCE_LABEL = "https://cykelkalenderen.dk"

# ── Datatyper ────────────────────────────────────────────────────────────────
# Ingen CHECK-constraint i databasen paa disse (en CHECK paa agent_runs.trigger
# kostede en tavs fejl i commit 8776e0d) — listen haandhaeves her.
DATA_TYPES = {
    "stage_info": {"label": "Etapeinfo", "races": ("stage_race", "oneday", "cyclocross")},
    "route_gpx": {"label": "Rute (GPX)", "races": ("stage_race", "oneday", "cyclocross")},
    "climbs": {"label": "Stigninger", "races": ("stage_race", "oneday", "cyclocross")},
    "startlist": {"label": "Startliste", "races": ("stage_race", "oneday", "cyclocross")},
    "teams": {"label": "Holdlister", "races": ("stage_race", "oneday", "cyclocross")},
    "results": {"label": "Resultater", "races": ("stage_race", "oneday", "cyclocross")},
    "live_text": {"label": "Skriftlig kommentering", "races": ("stage_race", "oneday", "cyclocross")},
    "streaming": {"label": "Streaming", "races": ("stage_race", "oneday", "cyclocross")},
}

STATUS_FOUND = "found"
STATUS_MISSING = "missing"
STATUS_NA = "not_applicable"

_GPX_CACHE: set[str] | None = None


def now() -> datetime:
    return datetime.now(timezone.utc)


# ── Supabase ─────────────────────────────────────────────────────────────────

def sb(method: str, path: str, _tries: int = 4, **kw):
    """Supabase svarer af og til 5xx gennem Cloudflare (set: 520 midt i en
    seed-koersel). En worker, der doer af det, efterlader tilstanden halvt
    skrevet — derfor et par forsoeg med voksende pause."""
    delay = 1.0
    for attempt in range(_tries):
        res = requests.request(
            method, f"{SUPABASE_URL}/rest/v1/{path}",
            headers={**SB, "Content-Type": "application/json",
                     "Prefer": "return=representation"},
            timeout=60, **kw)
        if res.status_code < 500:
            res.raise_for_status()
            return res.json() if res.text else []
        if attempt == _tries - 1:
            res.raise_for_status()
        time.sleep(delay)
        delay *= 2
    return []


def races_in_scope(season: int | None, slug: str | None = None) -> list[dict]:
    """--race er til lige efter, at et loeb er tilfoejet: saet workeren paa
    netop det, i stedet for at vente paa at koeen naar frem til det."""
    if slug:
        flt = f"&slug=eq.{slug}"
    else:
        flt = (f"&start_date=gte.{season}-01-01&start_date=lte.{season}-12-31"
               if season else "")
    return sb("GET", "races?select=id,slug,name,race_type,start_date,end_date,"
                     f"pcs_url,source_url&order=start_date{flt}")


# ── Hvad HAR vi allerede? ────────────────────────────────────────────────────

def _gpx_configured() -> set[str]:
    """DB-slugs vi allerede har en GPX-kilde til. Laeses fra koden, ikke
    hardkodet her — to kilder til sandhed ville komme ud af trit."""
    global _GPX_CACHE
    if _GPX_CACHE is None:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from climb_profile_generator import CYCLINGSTAGE_GPX_PAGES
            _GPX_CACHE = set(CYCLINGSTAGE_GPX_PAGES)
        except Exception:                      # noqa: BLE001
            _GPX_CACHE = set()
    return _GPX_CACHE


def _any(path: str) -> bool:
    try:
        return len(sb("GET", path + "&limit=1")) > 0
    except requests.HTTPError:
        return False


def current_status(race: dict, stage_ids: list[str],
                   stages: list[dict]) -> dict[str, tuple[str, str | None]]:
    """Udleder status for hver datatype af det, der faktisk staar i databasen."""
    rid = race["id"]
    out: dict[str, tuple[str, str | None]] = {}

    # Et cross-loeb er 5-8 omgange paa en bane paa 2-3 km. Rute og stigninger
    # giver ingen mening, og uden denne undtagelse ville hvert cross-loeb staa
    # som to permanente huller i koeen og i race_completeness.
    is_cx = race.get("race_type") == "cyclocross"

    has_distance = any((s.get("distance_km") or 0) > 0 for s in stages)

    out["stage_info"] = (STATUS_FOUND, "pcs") if has_distance else (STATUS_MISSING, None)

    # GPX: route_points er naesten altid tom, selv for loeb VI HAR en kilde til —
    # ruten hentes on demand, ikke gemt pr. etape. Den autoritative liste er
    # CYCLINGSTAGE_GPX_PAGES. Uden dette opslag ville 33 af 36 loeb staa som
    # "mangler GPX", og workeren ville bruge et LLM-kald paa hvert af dem.
    if is_cx:
        out["route_gpx"] = (STATUS_NA, None)
    elif race["slug"] in _gpx_configured():
        out["route_gpx"] = (STATUS_FOUND, "cyclingstage")
    elif any(s.get("route_points") for s in stages):
        out["route_gpx"] = (STATUS_FOUND, "db")
    else:
        out["route_gpx"] = (STATUS_MISSING, None)

    climbs = False
    if stage_ids:
        climbs = _any(f"stage_climbs?stage_id=in.({','.join(stage_ids[:40])})&select=id")
    if is_cx:
        out["climbs"] = (STATUS_NA, None)
    else:
        out["climbs"] = (STATUS_FOUND, "pcs") if climbs else (STATUS_MISSING, None)

    out["startlist"] = ((STATUS_FOUND, "pcs")
                        if _any(f"startlists?race_id=eq.{rid}&select=id")
                        else (STATUS_MISSING, None))
    out["results"] = ((STATUS_FOUND, "pcs")
                      if _any(f"results?race_id=eq.{rid}&select=id")
                      else (STATUS_MISSING, None))
    out["streaming"] = ((STATUS_FOUND, "broadcast")
                        if _any(f"broadcast_schedule?race_id=eq.{rid}&select=id")
                        else (STATUS_MISSING, None))

    # Holdlister er globale, ikke pr. loeb — de kan ikke mangle for ét loeb.
    out["teams"] = (STATUS_NA, None)

    # Skriftlig kommentering findes kun for etapeloeb: endagsloebs live-sider
    # svarer 403 (afproevet 2026-09-09, se data_sources.py).
    out["live_text"] = ((STATUS_MISSING, None)
                        if race.get("race_type") == "stage_race"
                        else (STATUS_NA, None))
    if is_cx:
        out["stage_info"] = ((STATUS_FOUND, "cykelkalenderen")
                             if stages else (STATUS_MISSING, None))
    return out


# ── Spaerretid ───────────────────────────────────────────────────────────────

def is_due(row: dict, race: dict, force: bool = False) -> tuple[bool, str]:
    """Ejerens regler: 1/md. normalt, 1/uge under en maaned til start,
    1/dag den sidste uge.

    `force` springer KUN kadencen over — altsaa "er der gaaet laenge nok siden
    sidste forsoeg". De to oevrige regler staar fast: en raekke, der ikke er et
    hul, og en tidsbunden type paa et koert loeb, springes stadig over. Flaget
    er til, naar ejeren beder om en soegning NU og ikke vil vente paa, at koen
    naar frem af sig selv."""
    if row["status"] != STATUS_MISSING:
        return False, "ikke et hul"

    days_to_start = None
    if race.get("start_date"):
        try:
            d = datetime.fromisoformat(race["start_date"]).replace(tzinfo=timezone.utc)
            days_to_start = (d - now()).days
        except ValueError:
            pass

    # Et koert loeb er ikke uinteressant: dets landingsside lever videre, og
    # rute, stigninger og startliste goer den staerkere. Kun de tidsbundne
    # typer giver ingen mening bagefter.
    if (days_to_start is not None and days_to_start < -14
            and row["data_type"] in ("streaming", "live_text")):
        return False, "loebet er koert (tidsbunden type)"

    if force:
        return True, "tvunget (--force)"

    last = row.get("last_attempt_at")
    if not last:
        return True, "aldrig forsoegt"
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
    except ValueError:
        return True, "ulaeselig dato"

    if days_to_start is not None and 0 <= days_to_start <= 7:
        window = timedelta(days=1)
    elif days_to_start is not None and 0 <= days_to_start <= 30:
        window = timedelta(days=7)
    else:
        window = timedelta(days=30)

    age = now() - last_dt
    if age >= window:
        return True, f"sidst forsoegt for {age.days} dage siden"
    return False, f"spaerret {(window - age).days + 1} dage endnu"


# ── Deterministiske probes (gratis) ──────────────────────────────────────────

def fetch(url: str):
    try:
        return requests.get(url, headers={"User-Agent": UA},
                            timeout=LIMITS["HTTP_TIMEOUT"])
    except requests.RequestException:
        return None


SPA_HOST_RE = re.compile(r'https?://(?:[a-z0-9-]+\.)+[a-z]{2,}(?=["\'])', re.I)
SKIP_HOSTS = ("w3.org", "github.com", "mozilla.org", "jquery", "googleapis",
              "gstatic", "schema.org", "facebook", "twitter", "instagram",
              "cloudflare", "jsdelivr", "unpkg")


def find_api_host(html: str, root: str) -> list[str]:
    """Naar arrangoerens side er en JavaScript-app, staar indholdet ikke i
    HTML'en — men API-vaerten staar i bundlen. Det var saadan Guangxi blev
    knaekket (cycling.edgecycling.cn stod i umi.js). Bundlen gaar ALDRIG ind i
    en prompt; den laeses her."""
    hosts: list[str] = []
    for m in re.finditer(r'src=["\']([^"\']+\.js)["\']', html, re.I):
        src = m.group(1)
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = root.rstrip("/") + src
        elif not src.startswith("http"):
            continue
        res = fetch(src)
        if not res or res.status_code != 200 or len(res.text) > 4_000_000:
            continue
        for h in SPA_HOST_RE.findall(res.text):
            if any(s in h.lower() for s in SKIP_HOSTS) or root.startswith(h):
                continue
            if h not in hosts:
                hosts.append(h)
        if len(hosts) >= 8:
            break
    return hosts[:8]


ORG_PATHS = {
    "route_gpx": ("/route", "/parcours", "/stages", "/percorso"),
    "stage_info": ("/route", "/stages", "/etapes", "/percorso"),
    # Stigningsprofilerne ligger normalt paa rutesiden, ikke paa en egen side —
    # uden denne linje kunne proben pr. definition aldrig finde dem, og hvert
    # loeb ville koste et LLM-kald for ingenting (fundet paa Veneto Classic).
    "climbs": ("/percorso", "/route", "/climbs", "/salite", "/stages"),
    "startlist": ("/startlist", "/riders", "/start-list"),
    "teams": ("/teams", "/squadre", "/equipes"),
    "streaming": ("/tv", "/live", "/broadcast"),
    "live_text": ("/live", "/livetracking", "/live-tracking"),
}



# ── Streaming: spoerg den kilde, vi allerede har ─────────────────────────────
# Den foerste udgave proevede arrangoerens /tv og /live og gik saa til Claude,
# som fandt en side om GIRO DEL VENETO til VENETO CLASSIC. Forkert sted at
# lede: `tv_agent.py` laeser i forvejen danske tv-tider (HBO Max, Eurosport,
# TV 2 Sport, Discovery+) fra cykelkalenderen.dk, og den kilde skelner
# eksplicit mellem loeb MED og UDEN dansk tv.
#
# Vi genbruger tv_agents egen udtraekskode frem for at skrive den af — og
# matcher paa LOEST navn i stedet for dens haandholdte RACE_KEYWORDS, saa et
# nyt loeb ikke kraever en kodeaendring. (RACE_KEYWORDS er bevidst uroert: den
# agent henter tv-tider for Tour de France, og den aendring skal godkendes.)
#
# Siden svarer HTTP 454 paa et almindeligt kald, saa den KRAEVER browser.
# Derfor hentes den hoejst én gang pr. koersel og caches.


# tv_agents EXTRACT_JS kraever et .race-title-element og kasserer alt andet:
#
#     const titleEl = tbody.querySelector('.race-title');
#     if (!timeEl || !titleEl) return;
#
# Men .race-title findes KUN, naar cykelkalenderen selv har koblet udsendelsen
# til sin egen loebsdatabase. Har den ikke det, staar programmet med tv-kanalens
# egen titel i ren tekst — og ryger ud. Tour of Guangxi sendes paa HBO Max
# kl. 07:40, men staar som "Tour of Guangxi | 2. etape" uden .race-title og
# blev derfor meldt som "ikke paa dansk tv" (fundet 2026-10-14).
#
# Her er udtrakket derfor tolerant: titlen tages fra .race-title naar den
# findes, ellers fra raekkens egen tekst med klokkeslaettet og etape-suffikset
# klippet af. LOGO_MAP genbruges fra tv_agent — kanalkortet skal kun ét sted.
#
# SAMME FEJL SIDDER I tv_agent.py. Den er bevidst uroert her: den henter
# tv-tider for Tour de France, og rettelsen skal godkendes foerst.
PERMISSIVE_JS = r"""(LOGO_MAP) => {
    const out = [];
    document.querySelectorAll('tbody').forEach(tb => {
        const timeEl = tb.querySelector('.tv-from b');
        if (!timeEl) return;
        const logos = [...tb.querySelectorAll('.tv-logo')].map(el => {
            const m = (el.style.backgroundImage || '').match(/tv-logos\/([^"')\s]+)/);
            return m ? m[1] : null;
        }).filter(Boolean);
        const titleEl = tb.querySelector('.race-title');
        let title;
        if (titleEl) {
            title = titleEl.innerText;
        } else {
            title = (tb.innerText || '')
                .replace(/\s+/g, ' ')
                .replace(timeEl.innerText.trim(), '')
                .split('|')[0];
        }
        title = (title || '').replace(/\s+/g, ' ').trim();
        if (!title) return;
        // Datoen staar i en overskrift FOER raekken ("I dag", "Loerdag d. 17/10").
        // Uden den kunne et loeb matches til en udsendelse paa en anden dag.
        let dateStr = null;
        let node = tb.closest('table') || tb;
        while (node && !dateStr) {
            let prev = node.previousElementSibling;
            while (prev && !dateStr) {
                const txt = (prev.innerText || '').trim();
                if (/^(i dag|i morgen)/i.test(txt) || /d\. ?\d{1,2}\/\d{1,2}/.test(txt)) {
                    dateStr = txt.split(String.fromCharCode(10))[0].trim().slice(0, 40);
                }
                prev = prev.previousElementSibling;
            }
            node = node.parentElement;
        }
        out.push({
            date: dateStr,
            time: timeEl.innerText.trim(),
            race: title,
            channels: logos.map(l => LOGO_MAP[l] || l),
            linked: !!titleEl
        });
    });
    return out;
}"""

_TV_CACHE: list | None = None


def _tv_programmes() -> list:
    global _TV_CACHE
    if _TV_CACHE is not None:
        return _TV_CACHE
    _TV_CACHE = []
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import tv_agent
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 Klassementet/1.0"})
            page.goto(tv_agent.SOURCE_URL, wait_until="networkidle", timeout=30_000)
            time.sleep(2)
            _TV_CACHE = page.evaluate(PERMISSIVE_JS, tv_agent.LOGO_MAP) or []
            browser.close()
    except Exception as exc:                      # noqa: BLE001
        print(f"    (kunne ikke hente tv-oversigten: {exc})")
    return _TV_CACHE


def probe_streaming(race: dict) -> dict:
    """Fundet kraever BAADE et navnematch OG en aflaest kanal. Staar loebet paa
    oversigten uden kanal, hoerer det til under "Danskernes loeb uden dansk tv"
    — og saa er svaret et aerligt nej, ikke et gaet."""
    progs = _tv_programmes()
    if not progs:
        return {"found": False, "tried": [SOURCE_LABEL],
                "failure": "tv-oversigten kunne ikke hentes"}
    name = race["name"].lower()
    # Rensningen genbruges fra tv_agent, saa de to agenter ikke kan naa
    # modsatte svar paa det samme program. Den fjerner ogsaa disciplin-
    # praefikset ("Cyklecross:") og parentes-tilfoejelser ("(tidl. Exact
    # Cross)") — uden dem faldt hvert cross-loeb ud med navnematch 0,66 og
    # blev meldt som "ikke paa dansk tv", selv om HBO Max sender det.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from tv_agent import parse_date, rens_programtitel

    # DATOEN er den haarde betingelse, navnet kun den bloede. Loeb i samme
    # serie hedder naesten det samme ("HG Cross Meulebeke - Berencross" mod
    # "HG Cross Lokeren - Rapencross" gav 0,77), saa navnematch alene
    # udnaevnte Meulebekes udsendelse 17/10 til dokumentation for Lokeren
    # 21/11 og Mol 17/12. En udsendelse paa en anden dato end loebet kan
    # ikke dokumentere loebet — uanset hvor ens navnene er.
    start = race.get("start_date")
    slut = race.get("end_date") or start

    def paa_loebsdagen(prog) -> bool:
        if not start:
            return True
        d = parse_date(str(prog.get("date") or ""))
        return bool(d and start <= d.isoformat() <= slut)

    best, best_ratio = None, 0.0
    for prog in progs:
        raa = str(prog.get("race") or "")
        # [K] er kvindeloebet. Databasen rummer kun herreloeb, og de to
        # programmer har samme navn — uden dette ville kvindernes kanal og
        # klokkeslaet kunne ende som dokumentation paa herreloebet.
        if re.search(r"\[\s*k\s*\]", raa, re.IGNORECASE):
            continue
        if not paa_loebsdagen(prog):
            continue
        title = rens_programtitel(raa.lower())
        if not title:
            continue
        ratio = SequenceMatcher(None, name, title).ratio()
        if ratio > best_ratio:
            best, best_ratio = prog, ratio
    if not best or best_ratio < 0.72:
        return {"found": False, "tried": [SOURCE_LABEL],
                "failure": f"ikke paa dansk tv-oversigt (bedste navnematch "
                           f"{best_ratio:.2f})"}
    channels = [c for c in (best.get("channels") or []) if c]
    if not channels:
        return {"found": False, "tried": [SOURCE_LABEL],
                "failure": f"staar som '{best.get('race')}' uden dansk kanal "
                           "— sendes formentlig ikke i Danmark"}
    return {"found": True, "url": SOURCE_LABEL, "source_name": "cykelkalenderen",
            "verification": {"kanaler": channels, "tid": best.get("time"),
                             "dato": best.get("date"), "titel": best.get("race"),
                             "navnematch": round(best_ratio, 2)},
            "tried": [SOURCE_LABEL]}


def pcs_side_mangler(res) -> bool:
    """PCS svarer 200 OK paa et loeb, der ikke findes, og skriver "Page not
    found" i selve siden. Maalt 2026-10-14: 23 af vores 24 cross-slugs gav
    HTTP 200 med praecis 12476 bytes og den tekst. Et tjek paa statuskode og
    laengde kan altsaa ikke staa alene — uden dette ville hver af dem blive
    gemt som en gyldig PCS-kilde."""
    if res is None:
        return True
    head = res.text[:4000].lower()
    return "page not found" in head or "<title>404" in head


def pcs_url_for_cross(slug: str) -> str:
    """PCS' cross-loeb ligger paa /race/<slug> med aarstallet INDE i slug'en —
    ikke /race/<slug>/<aar>, som landevejsloebene bruger (PCS_URL_MOENSTER i
    pcs_source.py). Og slug'en er den samme som vores egen: PCS kalder
    24/10-loebet "hg-cross-heerderstrand-2026", praecis som vi goer.

    PCS opretter foerst siden taet paa loebsdagen — 2026-10-14 fandtes kun ét
    af vores 24. Derfor er dette en probe, der skal koere igen og igen, ikke
    en engangsudfyldning."""
    return f"https://www.procyclingstats.com/race/{slug}"


def probe(row: dict, race: dict) -> dict:
    """Trin 1-3 + 5. Skriver intet. `found` saettes KUN, naar en URL er hentet
    og kontrolleret."""
    dt = row["data_type"]
    tried: list[str] = []

    if dt == "streaming":
        return probe_streaming(race)

    # Trin 1: kilder vi allerede kender.
    if dt in ("results", "stage_info", "startlist") and race.get("pcs_url"):
        res = fetch(race["pcs_url"])
        tried.append(race["pcs_url"])
        if (res is not None and res.status_code == 200
                and len(res.text) > 2000 and not pcs_side_mangler(res)):
            return {"found": True, "url": race["pcs_url"], "source_name": "procyclingstats",
                    "verification": {"http": 200, "bytes": len(res.text)}, "tried": tried}

    # Trin 1b: cykelcross har intet pcs_url, men PCS bruger vores egen slug.
    if dt in ("results", "stage_info", "startlist") and race.get("race_type") == "cyclocross":
        url = pcs_url_for_cross(race["slug"])
        res = fetch(url)
        tried.append(url)
        if (res is not None and res.status_code == 200
                and len(res.text) > 2000 and not pcs_side_mangler(res)):
            return {"found": True, "url": url, "source_name": "procyclingstats",
                    "verification": {"http": 200, "bytes": len(res.text),
                                     "moenster": "cross: /race/<slug>"},
                    "tried": tried}

    # Trin 2-3: arrangoerens eget site.
    base = race.get("source_url") or ""
    if base.startswith("http"):
        root_m = re.match(r"(https?://[^/]+)", base)
        root = root_m.group(1) if root_m else base
        res = fetch(root)
        tried.append(root)
        if res is not None and res.status_code == 200:
            for p in ORG_PATHS.get(dt, ()):
                url = root + p
                r2 = fetch(url)
                tried.append(url)
                if r2 is not None and r2.status_code == 200 and len(r2.text) > 1500:
                    return {"found": True, "url": url, "source_name": "organiser",
                            "verification": {"http": 200, "bytes": len(r2.text)},
                            "tried": tried}
            hosts = find_api_host(res.text, root)
            if hosts:
                return {"found": False, "tried": tried, "api_hosts": hosts,
                        "failure": "arrangoerens side er en JS-app; mulige API-vaerter: "
                                   + ", ".join(hosts)}

    return {"found": False, "tried": tried,
            "failure": "ingen kendt kilde svarede for denne datatype"}


# ── Claude-trinnet (kun naar probes gav op) ──────────────────────────────────

SYSTEM = (
    "Du finder officielle datakilder til cykelloeb. Svar KUN med JSON: "
    '{"url": "<direkte url eller null>", "source_name": "<kort navn>", '
    '"note": "<kort begrundelse>"}. '
    "Angiv kun en URL, du faktisk har set i soegeresultaterne. Gaet aldrig."
)


def ask_claude(row: dict, race: dict, probe_result: dict) -> dict | None:
    """Trin 4. Lille prompt med vilje — ingen caching, ingen raa sider."""
    try:
        import anthropic
    except ImportError:
        print("    (anthropic-pakken mangler — springer LLM-trinnet over)")
        return None
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("    (ANTHROPIC_API_KEY mangler — springer LLM-trinnet over)")
        return None

    hint = ""
    if probe_result.get("api_hosts"):
        hint = (" Arrangoerens site er en JavaScript-app; disse API-vaerter stod "
                "i bundlen: " + ", ".join(probe_result["api_hosts"]) + ".")
    year = (race.get("start_date") or "")[:4]
    prompt = (f"Loeb: {race['name']} {year}. Mangler: "
              f"{DATA_TYPES[row['data_type']]['label']}.{hint} "
              "Find en officiel eller paalidelig offentlig kilde.")

    try:
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=MODEL_TRIAGE,
            max_tokens=600,
            system=SYSTEM,
            tools=[{"type": "web_search_20250305", "name": "web_search",
                    "max_uses": LIMITS["MAX_SEARCHES_PER_LLM_CALL"]}],
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:                      # noqa: BLE001 - maa aldrig vaelte koerslen
        print(f"    (Claude-kaldet fejlede: {exc})")
        return None

    text = "".join(b.text for b in msg.content if b.type == "text")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def verify_url(url: str, race: dict) -> dict | None:
    """Trin 5. Et forslag fra Claude er ikke et fund, foer siden er hentet.
    Seks konstruerede, plausible URL'er gav alle 404 i juli 2026 — derfor."""
    if not isinstance(url, str) or not url.startswith("http"):
        return None
    res = fetch(url)
    if res is None or res.status_code != 200 or len(res.text) < 400:
        return None
    # PCS svarer 200 OK med "Page not found" paa et loeb, der ikke findes.
    # Navneord-tjekket nedenfor fanger det som regel, men ikke altid: en side,
    # hvis navigation tilfaeldigvis rummer loebets ord, ville slippe igennem.
    if pcs_side_mangler(res):
        return None
    # To fejl boede i den foerste udgave, og begge lod en forkert side slippe
    # igennem som Veneto Classics streamingkilde (fanget 2026-10-14):
    #  1. der blev matchet mod RAA HTML, saa WordPress-klassen
    #     "classic-theme-styles" taltes som et traef paa ordet "classic";
    #  2. der blev matchet paa substring, saa "classica" ogsaa gav traef.
    # Nu matches der paa ordgraenser i den SYNLIGE tekst.
    visible = re.sub(r"<(?:script|style)[^>]*>.*?</(?:script|style)>", " ",
                     res.text, flags=re.S | re.I)
    visible = re.sub(r"<[^>]+>", " ", visible).lower()
    # Hele ord, ikke substrings: en ordmaengde i stedet for et regex pr. ord
    # (og dermed heller ingen escape-faelder).
    tokens = set(re.split(r"[^a-z0-9]+", visible))
    words = [w for w in re.split(r"[^a-zA-Z]+", race["name"].lower()) if len(w) > 3]
    hits = sum(1 for w in words if w in tokens)
    ratio = hits / len(words) if words else 0.0
    year = (race.get("start_date") or "")[:4]
    # Mindst 3/4 af navneordene OG aarstallet. Den foerste udgave kraevede kun
    # ÉT navneord, og Claudes forslag til Veneto Classics streaming var derfor
    # en side om Giro del Veneto — samme arrangoer, andet loeb, og ordet
    # "veneto" alene var nok til at slippe igennem (fanget 2026-10-14).
    return {"http": res.status_code, "bytes": len(res.text),
            "navneord_fundet": hits, "navneord_i_alt": len(words),
            "andel": round(ratio, 2),
            "aar_paa_siden": year in visible,
            "godkendt": ratio >= 0.75 and year in res.text}


# ── Kommandoer ───────────────────────────────────────────────────────────────

def cmd_seed(season: int | None, write: bool, slug: str | None = None) -> None:
    races = races_in_scope(season, slug)
    print(f"{len(races)} loeb i omfang\n")
    created = updated = 0
    for race in races:
        stages = sb("GET", f"stages?race_id=eq.{race['id']}"
                           "&select=id,distance_km,route_points")
        status = current_status(race, [s["id"] for s in stages], stages)
        existing = {r["data_type"]: r for r in sb(
            "GET", f"race_data_sources?race_id=eq.{race['id']}"
                   "&is_backup=eq.false&select=*")}
        for dt, meta in DATA_TYPES.items():
            if race.get("race_type") not in meta["races"]:
                continue
            new_status, source = status.get(dt, (STATUS_MISSING, None))
            old = existing.get(dt)
            if old and old["status"] == new_status:
                continue
            payload = {"race_id": race["id"], "data_type": dt, "status": new_status,
                       "source_name": source, "updated_at": now().isoformat()}
            if new_status == STATUS_FOUND:
                payload["verified_at"] = now().isoformat()
            if write:
                if old:
                    sb("PATCH", f"race_data_sources?id=eq.{old['id']}", json=payload)
                else:
                    sb("POST", "race_data_sources", json=payload)
            if old:
                updated += 1
            else:
                created += 1
    print(f"{'skrev' if write else 'ville skrive'}: {created} nye, {updated} opdaterede")


def cmd_status(season: int | None, slug: str | None = None) -> None:
    races = {r["id"]: r for r in races_in_scope(season, slug)}
    rows = [r for r in sb("GET", "race_data_sources?is_backup=eq.false&select=*")
            if r["race_id"] in races]
    by_type: dict[str, dict[str, int]] = {}
    for r in rows:
        by_type.setdefault(r["data_type"], {})
        by_type[r["data_type"]][r["status"]] = by_type[r["data_type"]].get(r["status"], 0) + 1
    print(f"{'Datatype':<24}{'fundet':>8}{'mangler':>9}{'n/a':>6}")
    for dt, meta in DATA_TYPES.items():
        c = by_type.get(dt, {})
        print(f"{meta['label']:<24}{c.get(STATUS_FOUND, 0):>8}"
              f"{c.get(STATUS_MISSING, 0):>9}{c.get(STATUS_NA, 0):>6}")
    gaps = [r for r in rows if r["status"] == STATUS_MISSING]
    never = [r for r in gaps if not r["last_attempt_at"]]
    print(f"\n{len(gaps)} huller, heraf {len(never)} aldrig forsoegt")


def llm_calls_this_month() -> int:
    start = now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # "+00:00" skal kodes: et raat + i en query-streng betyder mellemrum, og
    # PostgREST svarer 400 paa den dato.
    stamp = quote(start.isoformat(), safe="")
    return len(sb("GET", f"race_data_sources?select=id&last_llm_attempt_at=gte.{stamp}"))


def cmd_run(season: int | None, write: bool, use_llm: bool,
            slug: str | None = None, force: bool = False) -> None:
    races = {r["id"]: r for r in races_in_scope(season, slug)}
    rows = [r for r in sb("GET", f"race_data_sources?status=eq.{STATUS_MISSING}"
                                 "&is_backup=eq.false&select=*"
                                 "&order=last_attempt_at.asc.nullsfirst")
            if r["race_id"] in races]

    budget_llm = 0
    if use_llm:
        used = llm_calls_this_month()
        budget_llm = max(0, min(LIMITS["MAX_LLM_CALLS_PER_RUN"],
                                LIMITS["MAX_LLM_CALLS_PER_MONTH"] - used))
        print(f"LLM-budget: {budget_llm} kald (brugt {used}/"
              f"{LIMITS['MAX_LLM_CALLS_PER_MONTH']} denne maaned)")

    probes = llm_used = found = 0
    seen: set[str] = set()

    for row in rows:
        if probes >= LIMITS["MAX_PROBES_PER_RUN"]:
            print("\n(probe-loft naaet)")
            break
        if len(seen) >= LIMITS["MAX_RACES_PER_RUN"] and row["race_id"] not in seen:
            print("\n(loebs-loft naaet)")
            break
        race = races[row["race_id"]]
        due, why = is_due(row, race, force)
        if not due:
            continue
        seen.add(row["race_id"])
        print(f"\n{race['slug']} — {DATA_TYPES[row['data_type']]['label']}  ({why})")

        probes += 1
        result = probe(row, race)
        via = "probe"

        if not result["found"] and use_llm and llm_used < budget_llm:
            llm_used += 1
            print("    probe gav op — spoerger Claude")
            s = ask_claude(row, race, result)
            if s and s.get("url"):
                ver = verify_url(s["url"], race)
                result.setdefault("tried", []).append(s["url"])
                if ver and ver.get("godkendt"):
                    result = {"found": True, "url": s["url"],
                              "source_name": s.get("source_name") or "ukendt",
                              "verification": {**ver, "via": "claude"},
                              "tried": result["tried"]}
                    via = "claude"
                else:
                    result["failure"] = (f"Claude foreslog {s['url']}, "
                                         "men siden kunne ikke verificeres")

        payload = {
            "last_attempt_at": now().isoformat(),
            "attempt_count": (row.get("attempt_count") or 0) + 1,
            "attempted_paths": result.get("tried", [])[:20],
            "updated_at": now().isoformat(),
        }
        if use_llm and llm_used:
            payload["last_llm_attempt_at"] = now().isoformat()

        if result["found"]:
            found += 1
            payload.update({"status": STATUS_FOUND, "url": result["url"],
                            "source_name": result["source_name"],
                            "verified_at": now().isoformat(),
                            "verification": result.get("verification", {}),
                            "last_failure": None})
            print(f"    FUNDET ({via}): {result['url']}")
        else:
            payload["last_failure"] = (result.get("failure") or "ukendt")[:500]
            print(f"    ikke fundet: {payload['last_failure'][:110]}")

        if write:
            sb("PATCH", f"race_data_sources?id=eq.{row['id']}", json=payload)

    print(f"\n{probes} probes, {llm_used} LLM-kald (~{llm_used * 0.05:.2f} USD), "
          f"{found} nye kilder"
          f"{'' if write else ' — intet gemt, koer med --write'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", action="store_true", help="opret/opdater raekker fra DB-status")
    ap.add_argument("--run", action="store_true", help="arbejd koeen")
    ap.add_argument("--status", action="store_true", help="vis hvad der mangler")
    ap.add_argument("--use-llm", action="store_true", help="tillad Claude-trinnet (koster)")
    ap.add_argument("--season", type=int, default=None)
    ap.add_argument("--race", default=None, help="kun dette DB-slug")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="se bort fra spaerretiden og proev hullerne nu")
    args = ap.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        sys.exit("✗ SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY mangler")

    if args.seed:
        cmd_seed(args.season, args.write, args.race)
    elif args.run:
        cmd_run(args.season, args.write, args.use_llm, args.race, args.force)
    elif args.status:
        cmd_status(args.season, args.race)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
