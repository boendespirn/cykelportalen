"""
giro_results_agent.py
Scraper til Giro d'Italia etaperesultater og klassementer fra PCS.

Henter:
  - Etaperesultater (position, tid, point)
  - GC-klassement efter seneste etape
  - Opdaterer startlist-status for DNF/DNS/DSQ-ryttere

Brug:
  python giro_results_agent.py              # henter alle faerdige etaper
  python giro_results_agent.py --stages 1 2 3  # specifikke etaper
  python giro_results_agent.py --gc-only    # kun GC (ingen etaperesultater)

Re-run er sikkert: eksisterende resultater overskrives (upsert).
"""

import os, re, sys, io, asyncio, argparse, requests, unicodedata
from datetime import date, datetime
from playwright.async_api import async_playwright
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

CF_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

HEADERS = lambda: {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

# ---------- helpers --------------------------------------------------------

def sb_get(path: str, params: str = "") -> list:
    url = f"{SUPABASE_URL}/rest/v1/{path}{params}"
    r = requests.get(url, headers=HEADERS())
    r.raise_for_status()
    return r.json()

def sb_upsert(table: str, rows: list, on_conflict: str) -> None:
    if not rows:
        return
    url = f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={on_conflict}"
    h = {**HEADERS(), "Prefer": "resolution=merge-duplicates,return=minimal"}
    r = requests.post(url, json=rows, headers=h)
    if r.status_code not in (200, 201, 204):
        print(f"  !! upsert {table} fejl {r.status_code}: {r.text[:200]}")

def sb_patch(table: str, row_id: str, data: dict) -> None:
    url = f"{SUPABASE_URL}/rest/v1/{table}?id=eq.{row_id}"
    r = requests.patch(url, json=data, headers=HEADERS())
    if r.status_code not in (200, 204):
        print(f"  !! patch {table}/{row_id} fejl {r.status_code}")


def parse_gap(s: str) -> int:
    """'+H:MM:SS' / '+M:SS' / '0:00' → sekunder. Returnerer 0 for leder."""
    if not s:
        return 0
    s = s.strip().lstrip("+")
    if s in ("0:00", ",,", ""):
        return 0
    parts = s.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        pass
    return 0


def parse_time(s: str) -> int | None:
    """'H:MM:SS' → sekunder. Returnerer None for ',,' (gruppetid)."""
    if not s or s.strip() == ",,":
        return None
    s = s.strip()
    parts = s.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        pass
    return None


# ---------- JS-ekstraktion -------------------------------------------------

_EXTRACT_STAGE_JS = r"""() => {
    // Find den store resultattabel (min. 50 rækker)
    const tables = document.querySelectorAll('table');
    let tbl = null;
    for (const t of tables) {
        if (t.querySelectorAll('tbody tr').length > 50) { tbl = t; break; }
    }
    if (!tbl) return { rows: [], headers: [] };

    const headers = Array.from(tbl.querySelectorAll('th'))
        .map(th => th.innerText.trim().toLowerCase());

    const idxRnk     = headers.indexOf('rnk');
    const idxGC      = headers.indexOf('gc');
    const idxTimelag = headers.indexOf('timelag');
    const idxBIB     = headers.indexOf('bib');
    const idxRider   = headers.indexOf('rider');
    const idxPnt     = headers.indexOf('pnt');
    const idxTime    = headers.lastIndexOf('time');
    const idxBonus   = idxPnt >= 0 ? idxPnt + 1 : -1;

    const rows = [];
    for (const tr of tbl.querySelectorAll('tbody tr')) {
        const cells = Array.from(tr.querySelectorAll('td')).map(c => c.innerText.trim());
        if (cells.length < 4) continue;

        // PCS-slug fra link (ikke altid til stede i headless mode)
        const link    = tr.querySelector('a[href*="/rider/"]');
        const pcsSlug = link ? link.href.split('/rider/')[1] : null;
        const bib     = idxBIB    >= 0 ? (parseInt(cells[idxBIB])    || null) : null;
        const name    = idxRider  >= 0 ? cells[idxRider]              : null;

        const bonusStr = idxBonus >= 0 ? cells[idxBonus] : '';
        const bonusMatch = bonusStr ? bonusStr.match(/(\d+)/) : null;
        const bonusSec = bonusMatch ? parseInt(bonusMatch[1]) : 0;

        rows.push({
            stage_pos : parseInt(cells[idxRnk])     || null,
            gc_pos    : parseInt(cells[idxGC])       || null,
            gc_gap    : idxTimelag >= 0 ? cells[idxTimelag] : null,
            pnt       : parseInt(cells[idxPnt])      || 0,
            bonus_sec : bonusSec,
            time_str  : idxTime   >= 0 ? cells[idxTime]    : null,
            pcs_slug  : pcsSlug,
            bib       : bib,
            rider_name: name,
        });
    }
    return { rows, headers };
}"""


_EXTRACT_CLASSIF_JS = r"""(classifType) => {
    const tables = document.querySelectorAll('table');
    let tbl = null;
    for (const t of tables) {
        if (t.querySelectorAll('tbody tr').length > 10) { tbl = t; break; }
    }
    if (!tbl) return [];

    const headers = Array.from(tbl.querySelectorAll('th'))
        .map(th => th.innerText.trim().toLowerCase());
    const idxRnk    = headers.indexOf('rnk');
    const idxBIB    = headers.indexOf('bib');
    const idxRider  = headers.indexOf('rider');
    const idxTime   = headers.lastIndexOf('time');
    const idxPnt    = headers.indexOf('pnt');
    const idxGap    = headers.indexOf('gap');

    const rows = [];
    for (const tr of tbl.querySelectorAll('tbody tr')) {
        const cells  = Array.from(tr.querySelectorAll('td')).map(c => c.innerText.trim());
        if (cells.length < 3) continue;
        const link    = tr.querySelector('a[href*="/rider/"]');
        const pcsSlug = link ? link.href.split('/rider/')[1] : null;
        const bib     = idxBIB   >= 0 ? (parseInt(cells[idxBIB])   || null) : null;
        const name    = idxRider >= 0 ? cells[idxRider]             : null;
        rows.push({
            pos      : parseInt(cells[idxRnk]) || null,
            time_str : idxTime >= 0 ? cells[idxTime] : null,
            gap_str  : idxGap  >= 0 ? cells[idxGap]  : null,
            pnt      : idxPnt  >= 0 ? (parseInt(cells[idxPnt]) || 0) : 0,
            pcs_slug : pcsSlug,
            bib      : bib,
            rider_name: name,
        });
    }
    return rows;
}"""


# ---------- database lookups -----------------------------------------------

def build_slug_map() -> dict[str, str]:
    """PCS-slug → rider_id"""
    riders = sb_get("riders", "?select=id,source_url&source_url=not.is.null")
    m = {}
    for r in riders:
        if r.get("source_url"):
            slug = r["source_url"].rstrip("/").split("/rider/")[-1]
            m[slug] = r["id"]
    return m


def build_bib_map(race_id: str) -> dict[int, str]:
    """BIB-nummer → rider_id (fra startliste)"""
    sl = sb_get("startlists", f"?race_id=eq.{race_id}&select=bib_number,rider_id&bib_number=not.is.null")
    return {row["bib_number"]: row["rider_id"] for row in sl if row.get("bib_number")}


def resolve_rider(row: dict, slug_map: dict, bib_map: dict) -> str | None:
    """Find rider_id fra PCS-slug eller BIB-nummer."""
    if row.get("pcs_slug"):
        rid = slug_map.get(row["pcs_slug"])
        if rid:
            return rid
    if row.get("bib"):
        return bib_map.get(row["bib"])
    return None


def get_race(db_slug: str) -> dict:
    data = sb_get("races", f"?select=id,name,slug&slug=eq.{db_slug}&limit=1")
    if not data:
        raise ValueError(f"Løb '{db_slug}' ikke fundet i DB")
    return data[0]


def get_stages(race_id: str) -> dict[int, dict]:
    """stage_number → stage-dict"""
    stages = sb_get(
        "stages",
        f"?race_id=eq.{race_id}&select=id,stage_number,date&order=stage_number.asc"
    )
    return {s["stage_number"]: s for s in stages}


def get_startlist_map(race_id: str) -> dict[str, dict]:
    """rider_id → startlist-row"""
    sl = sb_get(
        "startlists",
        f"?race_id=eq.{race_id}&select=id,rider_id,status,bib_number"
    )
    return {row["rider_id"]: row for row in sl}


# ---------- scraping -------------------------------------------------------

_COOKIES_ACCEPTED = False


async def accept_cookies(page):
    global _COOKIES_ACCEPTED
    if _COOKIES_ACCEPTED:
        return
    try:
        await page.wait_for_selector("text=Accepter alle", timeout=5000)
        await page.click("text=Accepter alle")
        await page.wait_for_timeout(3000)
        _COOKIES_ACCEPTED = True
    except Exception:
        pass


async def load_page(page, url: str):
    """Load page og vent til indholdet er klar."""
    await page.goto(url, wait_until="load", timeout=45000)
    await page.wait_for_timeout(1500)
    await accept_cookies(page)
    await page.wait_for_timeout(3000)


async def scrape_stage(page, stage_num: int) -> list[dict]:
    url = f"{PCS_BASE}/stage-{stage_num}"
    print(f"  → {url}")
    await load_page(page, url)

    # Retry op til 3 gange hvis ingen data
    for attempt in range(3):
        data = await page.evaluate(_EXTRACT_STAGE_JS)
        if data["rows"]:
            print(f"    {len(data['rows'])} ryttere fundet (forsøg {attempt+1})")
            return data["rows"]
        if attempt < 2:
            print(f"    Ingen data endnu, venter 3s... (forsøg {attempt+1})")
            await page.wait_for_timeout(3000)

    print(f"    0 ryttere fundet (headers: {data.get('headers', [])})")
    return []


async def scrape_classification(page, classif: str) -> list[dict]:
    url = f"{PCS_BASE}/{classif}"
    print(f"  → {url}")
    await load_page(page, url)
    rows = await page.evaluate(_EXTRACT_CLASSIF_JS, classif)
    print(f"    {len(rows)} ryttere fundet")
    return rows


# ---------- storing --------------------------------------------------------

def store_stage_results(
    rows: list[dict],
    race_id: str,
    stage_id: str,
    stage_num: int,
    slug_map: dict,
    bib_map: dict,
    startlist: dict,
) -> int:
    today = date.today().isoformat()
    records = []
    winner_time = None

    # Find winner's time
    for row in rows:
        if row.get("stage_pos") == 1 and row.get("time_str") and row["time_str"] != ",,":
            winner_time = parse_time(row["time_str"])
            break

    for row in rows:
        rider_id = resolve_rider(row, slug_map, bib_map)
        if not rider_id:
            continue

        pos = row.get("stage_pos")
        time_s = None
        gap_s = 0

        if pos == 1:
            time_s = winner_time
            gap_s = 0
        else:
            gap_str = row.get("gc_gap") or ""
            gap_s = parse_gap(gap_str)
            time_s = (winner_time + gap_s) if winner_time else None

        records.append({
            "race_id"         : race_id,
            "stage_id"        : stage_id,
            "rider_id"        : rider_id,
            "position"        : pos,
            "time_seconds"    : time_s,
            "time_gap_seconds": gap_s,
            "points"          : row.get("pnt", 0) or 0,
            "dnf"             : False,
            "dns"             : False,
            "dsq"             : False,
        })

    sb_upsert("results", records, "race_id,stage_id,rider_id")
    return len(records)


def store_gc_from_stage(
    rows: list[dict],
    race_id: str,
    stage_num: int,
    slug_map: dict,
    bib_map: dict,
) -> int:
    """Bygger GC-klassement ud fra stage-resultaters GC-kolonne."""
    gc_rows = [r for r in rows if r.get("gc_pos")]
    gc_rows.sort(key=lambda r: r["gc_pos"])

    records = []
    leader_time = None

    for row in gc_rows:
        rider_id = resolve_rider(row, slug_map, bib_map)
        if not rider_id:
            continue

        gap_s = parse_gap(row.get("gc_gap") or "")
        if row["gc_pos"] == 1:
            leader_time = None  # vi kender lederens absolutte tid fra stage-siden

        records.append({
            "race_id"              : race_id,
            "after_stage_number"   : stage_num,
            "classification_type"  : "gc",
            "rider_id"             : rider_id,
            "position"             : row["gc_pos"],
            "time_gap_seconds"     : gap_s,
            "points"               : 0,
            "dnf"                  : False,
        })

    sb_upsert("classifications", records, "race_id,after_stage_number,classification_type,rider_id")
    return len(records)


def store_classification(
    rows: list[dict],
    race_id: str,
    stage_num: int,
    classif_type: str,
    slug_map: dict,
    bib_map: dict,
) -> int:
    records = []
    for row in rows:
        rider_id = resolve_rider(row, slug_map, bib_map)
        if not rider_id:
            continue

        gap_s = parse_gap(row.get("gap_str") or "")
        records.append({
            "race_id"             : race_id,
            "after_stage_number"  : stage_num,
            "classification_type" : classif_type,
            "rider_id"            : rider_id,
            "position"            : row.get("pos"),
            "time_gap_seconds"    : gap_s,
            "points"              : row.get("pnt", 0) or 0,
            "dnf"                 : False,
        })

    sb_upsert("classifications", records, "race_id,after_stage_number,classification_type,rider_id")
    return len(records)


def mark_dnfs(
    stage_rows: list[dict],
    race_id: str,
    stage_num: int,
    slug_map: dict,
    startlist: dict,
) -> None:
    """Marker ryttere der IKKE er i resultaterne som potentielle DNF."""
    finishers = {slug_map[r["pcs_slug"]] for r in stage_rows if r.get("pcs_slug") and slug_map.get(r["pcs_slug"])}
    for rider_id, sl_row in startlist.items():
        if sl_row["status"] == "active" and rider_id not in finishers:
            # Kun marker hvis de ikke allerede er markeret
            pass  # Kræver bekræftelse fra PCS DNF-liste; springer over for nu


# ---------- official giro classifications ----------------------------------

# Mappe fra klassifikationstype til jersey-label i giro-sidens body-tekst
_JERSEY_LABELS = {
    "points"   : ["CICLAMINO"],
    "mountains": ["AZZURRA"],
    "youth"    : ["BIANCA"],
    "gc"       : ["ROSA"],
}


def _parse_giro_text(lines: list[str], ctype: str) -> list[dict]:
    """
    Find den korrekte MAGLIA-sektion for ctype og parse én-værdi-per-linje-formatet.

    Point-klassementer (points, mountains): 5 linjer per post
      pos / fornavn / EFTERNAVN / hold / point
    Tidsklassementer (gc, youth): 6 linjer per post
      pos / fornavn / EFTERNAVN / hold / samlet-tid / tidsgab
    """
    jersey_labels = _JERSEY_LABELS.get(ctype, [])

    # Søg efter "MAGLIA\n[LABEL]\nRider\nTeam" der matcher vores ctype
    start_idx = None
    has_gap_col = False
    for i in range(len(lines) - 4):
        if lines[i] == "MAGLIA" and lines[i + 1] in jersey_labels:
            if i + 3 < len(lines) and lines[i + 2] == "Rider" and lines[i + 3] == "Team":
                # Tjek om der er en "Gap"-kolonne (tidsbaseret) eller ej
                has_gap_col = (i + 5 < len(lines) and lines[i + 5] == "Gap")
                header_cols = 2 if has_gap_col else 1  # Time+Gap eller Points
                start_idx = i + 4 + header_cols
                break

    if start_idx is None:
        return []

    lines_per_entry = 6 if has_gap_col else 5
    rows = []
    i = start_idx
    while i < len(lines) - (lines_per_entry - 1):
        if lines[i] == "LOAD MORE":
            break
        if lines[i].isdigit() and 1 <= int(lines[i]) <= 300:
            pos = int(lines[i])
            firstname = lines[i + 1]
            lastname  = lines[i + 2]
            # i+3 = hold, i+4 = samlet-tid (tids) eller point, i+5 = gap (tids)
            val = lines[i + 5] if has_gap_col else lines[i + 4]
            if val and i + (lines_per_entry - 1) < len(lines):
                val = val if val != "LOAD MORE" else None
            if re.search(r'[A-Za-z]', firstname) and re.search(r'[A-Za-z]', lastname):
                rows.append({"pos": pos, "name": f"{firstname} {lastname}", "val": val})
            i += lines_per_entry
        else:
            i += 1
    return rows


async def scrape_official_classification(page, param: str, ctype: str, year: int) -> list[dict]:
    url = f"https://www.giroditalia.it/en/classifiche/?classifica={param}"
    print(f"  → {url}")
    try:
        await page.goto(url, wait_until="networkidle", timeout=45000)
    except Exception:
        pass
    await page.wait_for_timeout(5000)

    content = await page.inner_text("body")
    lines = [l.strip() for l in content.splitlines() if l.strip()]

    rows = _parse_giro_text(lines, ctype)

    # Fallback: udtræk jersey-leder fra summary-sektion (giver kun position 1)
    if not rows:
        labels = _JERSEY_LABELS.get(ctype, [])
        for i, line in enumerate(lines):
            if line in labels:
                for j in range(i + 1, min(i + 4, len(lines))):
                    candidate = lines[j]
                    if re.search(r'[A-Z]', candidate) and re.search(r'[a-z]', candidate) and len(candidate) > 4:
                        rows.append({"pos": 1, "name": candidate, "val": None})
                        break
                break

    print(f"    {len(rows)} rækker fundet")
    return rows


def normalize_accent(s: str) -> str:
    """Strip accents og lowercase: EULÀLIO → eulalio"""
    return unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('ASCII').lower()


def store_official_classification(
    rows: list[dict],
    race_id: str,
    stage_num: int,
    ctype: str,
) -> int:
    all_riders = sb_get("riders", "?select=id,name&limit=2000")
    name_map: dict[str, str] = {}
    for r in all_riders:
        raw = r["name"].strip()
        parts = raw.split()
        norm = normalize_accent(raw)
        name_map[norm] = r["id"]
        if len(parts) >= 2:
            # Omvendt rækkefølge: "Afonso Eulàlio" → "eulalio afonso"
            name_map[normalize_accent(" ".join(reversed(parts)))] = r["id"]
            # Efternavn alene
            name_map[normalize_accent(parts[-1])] = r["id"]
            # Fornavn alene
            name_map[normalize_accent(parts[0])] = r["id"]

    records = []
    for row in rows:
        if not row.get("name") or not row.get("pos"):
            continue

        name_norm = normalize_accent(row["name"])
        rider_id = name_map.get(name_norm)

        if not rider_id:
            # Prøv omvendt rækkefølge
            rev = " ".join(reversed(name_norm.split()))
            rider_id = name_map.get(rev)

        if not rider_id:
            for p in name_norm.split():
                if len(p) > 3:
                    rider_id = name_map.get(p)
                    if rider_id:
                        break

        if not rider_id:
            # Fuzzy: mindst 2 ord til fælles
            scraped_words = set(name_norm.split())
            for db_norm, db_id in name_map.items():
                if len(scraped_words & set(db_norm.split())) >= 2:
                    rider_id = db_id
                    break

        if not rider_id:
            print(f"    ! Rytter ikke fundet: {row['name']}")
            continue

        val = row.get("val") or ""
        pts = 0
        time_gap = 0
        if ctype in ("points", "mountains"):
            try:
                pts = int(str(val).replace(".", "").replace(",", ""))
            except Exception:
                pts = 0
        else:
            # Tidsbaseret klassement (youth, gc): val er tidsgab som "03:17"
            time_gap = parse_gap(str(val)) if val else 0

        records.append({
            "race_id"             : race_id,
            "after_stage_number"  : stage_num,
            "classification_type" : ctype,
            "rider_id"            : rider_id,
            "position"            : row["pos"],
            "time_gap_seconds"    : time_gap,
            "points"              : pts,
            "dnf"                 : False,
        })

    sb_upsert("classifications", records, "race_id,after_stage_number,classification_type,rider_id")
    return len(records)


# ---------- main -----------------------------------------------------------

async def main(stages_to_scrape: list[int], gc_only: bool, db_slug: str, pcs_slug: str, year: int):
    global PCS_BASE
    PCS_BASE = f"https://www.procyclingstats.com/race/{pcs_slug}/{year}"

    race   = get_race(db_slug)
    stages = get_stages(race["id"])

    print(f"\nLøb: {race['name']} ({race['id']})")
    print(f"Etaper i DB: {len(stages)}")

    today = date.today()

    # Bestem hvilke etaper der er faerdige (dato < i dag)
    done_stages = sorted([
        n for n, s in stages.items()
        if s["date"] and s["date"] < today.isoformat()
    ])

    if stages_to_scrape:
        targets = [n for n in stages_to_scrape if n in stages]
    else:
        targets = done_stages

    if not targets and not gc_only:
        print("Ingen faerdige etaper at hente endnu.")
        return

    print(f"Henter etaper: {targets}")

    slug_map   = build_slug_map()
    bib_map    = build_bib_map(race["id"])
    startlist  = get_startlist_map(race["id"])
    latest_stage_rows = []
    print(f"Slug-map: {len(slug_map)} ryttere, BIB-map: {len(bib_map)} ryttere")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=CF_UA, locale="da-DK")
        page = await ctx.new_page()

        if not gc_only:
            for stage_num in targets:
                stage = stages[stage_num]
                print(f"\nEtape {stage_num} ({stage['date']}):")
                rows = await scrape_stage(page, stage_num)
                if not rows:
                    print("  Ingen data — springer over.")
                    continue

                n = store_stage_results(rows, race["id"], stage["id"], stage_num, slug_map, bib_map, startlist)
                print(f"  Gemt {n} etaperesultater")

                gc_n = store_gc_from_stage(rows, race["id"], stage_num, slug_map, bib_map)
                print(f"  Gemt {gc_n} GC-poster (fra etapeside)")

                latest_stage_rows = rows

        # Hent klassementer fra officiel Giro-side
        last_stage = max(targets) if targets else max(done_stages) if done_stages else None
        if last_stage:
            print(f"\nHenter klassementer efter etape {last_stage} (giroditalia.it):")
            for param, ctype in [
                ("CLPUNGEN", "points"),
                ("CLGPMGEN", "mountains"),
                ("CLBIANC",  "youth"),
            ]:
                try:
                    c_rows = await scrape_official_classification(page, param, ctype, year)
                    if c_rows:
                        n = store_official_classification(c_rows, race["id"], last_stage, ctype)
                        print(f"  Gemt {n} {ctype}-poster")
                    else:
                        print(f"  Ingen data for {ctype}")
                except Exception as e:
                    print(f"  Fejl ved {ctype}: {e}")

        await browser.close()

    print("\nFaerdig!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stages",   nargs="*", type=int, default=[])
    parser.add_argument("--gc-only",  action="store_true")
    parser.add_argument("--db-slug",  default="giro-d-italia-2026", help="DB-slug med årstal")
    parser.add_argument("--pcs-slug", default="giro-d-italia",      help="PCS-slug til URL")
    parser.add_argument("--year",     type=int, default=2026)
    args = parser.parse_args()
    asyncio.run(main(args.stages, args.gc_only, args.db_slug, args.pcs_slug, args.year))
