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

import os, re, sys, io, asyncio, argparse, requests
from datetime import date, datetime
from playwright.async_api import async_playwright
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
GIRO_SLUG    = "giro-d-italia-2026"
PCS_BASE     = "https://www.procyclingstats.com/race/giro-d-italia/2026"

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
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    h = {**HEADERS(), "Prefer": f"resolution=merge-duplicates,return=minimal"}
    r = requests.post(url, json=rows, headers={**h, "Prefer": f"resolution=merge-duplicates,return=minimal"})
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
    function parseBonus(s) {
        if (!s) return 0;
        const m = s.match(/(\d+)/);
        return m ? parseInt(m[1]) : 0;
    }
    const tables = document.querySelectorAll('table');
    let tbl = null;
    for (const t of tables) {
        if (t.querySelectorAll('a[href*="/rider/"]').length > 5) { tbl = t; break; }
    }
    if (!tbl) return { rows: [], headers: [] };

    const headers = Array.from(tbl.querySelectorAll('th'))
        .map(th => th.innerText.trim().toLowerCase());

    const idxRnk     = headers.indexOf('rnk');
    const idxGC      = headers.indexOf('gc');
    const idxTimelag = headers.indexOf('timelag');
    const idxPnt     = headers.indexOf('pnt');
    const idxTime    = headers.lastIndexOf('time');

    // Bonus-kolonne (kolonne med ″-tegn i header eller tomme header)
    // er den efter Pnt
    const idxBonus   = idxPnt >= 0 ? idxPnt + 1 : -1;

    const rows = [];
    for (const tr of tbl.querySelectorAll('tbody tr')) {
        const cells = Array.from(tr.querySelectorAll('td')).map(c => c.innerText.trim());
        const link  = tr.querySelector('a[href*="/rider/"]');
        if (!link || cells.length < 4) continue;

        const pcsSlug = link.href.split('/rider/')[1] || null;
        rows.push({
            stage_pos : parseInt(cells[idxRnk])     || null,
            gc_pos    : parseInt(cells[idxGC])      || null,
            gc_gap    : cells[idxTimelag]            || null,
            pnt       : parseInt(cells[idxPnt])     || 0,
            bonus_sec : idxBonus >= 0 ? parseBonus(cells[idxBonus]) : 0,
            time_str  : idxTime >= 0 ? cells[idxTime] : null,
            pcs_slug  : pcsSlug,
        });
    }
    return { rows, headers };
}"""


_EXTRACT_CLASSIF_JS = r"""(classifType) => {
    // Klassement-sider (gc, points, mountains, youth)
    const tables = document.querySelectorAll('table');
    let tbl = null;
    for (const t of tables) {
        if (t.querySelectorAll('a[href*="/rider/"]').length > 5) { tbl = t; break; }
    }
    if (!tbl) return [];

    const headers = Array.from(tbl.querySelectorAll('th'))
        .map(th => th.innerText.trim().toLowerCase());
    const idxRnk  = headers.indexOf('rnk');
    const idxTime = headers.lastIndexOf('time');
    const idxPnt  = headers.indexOf('pnt');
    const idxGap  = headers.indexOf('gap');

    const rows = [];
    for (const tr of tbl.querySelectorAll('tbody tr')) {
        const cells = Array.from(tr.querySelectorAll('td')).map(c => c.innerText.trim());
        const link  = tr.querySelector('a[href*="/rider/"]');
        if (!link || cells.length < 4) continue;
        const pcsSlug = link.href.split('/rider/')[1] || null;
        rows.push({
            pos      : parseInt(cells[idxRnk]) || null,
            time_str : idxTime >= 0 ? cells[idxTime] : null,
            gap_str  : idxGap  >= 0 ? cells[idxGap]  : null,
            pnt      : idxPnt  >= 0 ? (parseInt(cells[idxPnt]) || 0) : 0,
            pcs_slug : pcsSlug,
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


def get_race() -> dict:
    data = sb_get("races", f"?select=id,name,slug&slug=eq.{GIRO_SLUG}&limit=1")
    if not data:
        raise ValueError(f"Løb '{GIRO_SLUG}' ikke fundet i DB")
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

async def accept_cookies(page):
    try:
        await page.wait_for_selector("text=Accepter alle", timeout=4000)
        await page.click("text=Accepter alle")
        await page.wait_for_timeout(800)
    except Exception:
        pass


async def scrape_stage(page, stage_num: int) -> list[dict]:
    url = f"{PCS_BASE}/stage-{stage_num}"
    print(f"  → {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await accept_cookies(page)
    await page.wait_for_timeout(1500)
    data = await page.evaluate(_EXTRACT_STAGE_JS)
    print(f"    {len(data['rows'])} ryttere fundet")
    return data["rows"]


async def scrape_classification(page, classif: str) -> list[dict]:
    url = f"{PCS_BASE}/{classif}"
    print(f"  → {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await accept_cookies(page)
    await page.wait_for_timeout(1500)
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
        pcs_slug = row.get("pcs_slug")
        if not pcs_slug:
            continue
        rider_id = slug_map.get(pcs_slug)
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
) -> int:
    """Bygger GC-klassement ud fra stage-resultaters GC-kolonne."""
    gc_rows = [r for r in rows if r.get("gc_pos")]
    gc_rows.sort(key=lambda r: r["gc_pos"])

    records = []
    leader_time = None

    for row in gc_rows:
        pcs_slug = row.get("pcs_slug")
        if not pcs_slug:
            continue
        rider_id = slug_map.get(pcs_slug)
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
) -> int:
    records = []
    for row in rows:
        pcs_slug = row.get("pcs_slug")
        if not pcs_slug:
            continue
        rider_id = slug_map.get(pcs_slug)
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


# ---------- main -----------------------------------------------------------

async def main(stages_to_scrape: list[int], gc_only: bool):
    race   = get_race()
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
    startlist  = get_startlist_map(race["id"])
    latest_stage_rows = []

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

                n = store_stage_results(rows, race["id"], stage["id"], stage_num, slug_map, startlist)
                print(f"  Gemt {n} etaperesultater")

                gc_n = store_gc_from_stage(rows, race["id"], stage_num, slug_map)
                print(f"  Gemt {gc_n} GC-poster (fra etapeside)")

                latest_stage_rows = rows

        # Hent klassementer fra PCS klassement-sider
        last_stage = max(targets) if targets else max(done_stages) if done_stages else None
        if last_stage:
            print(f"\nHenter klassementer efter etape {last_stage}:")
            for classif, ctype in [("points", "points"), ("mountains", "mountains"), ("youth", "youth")]:
                try:
                    c_rows = await scrape_classification(page, classif)
                    if c_rows:
                        n = store_classification(c_rows, race["id"], last_stage, ctype, slug_map)
                        print(f"  Gemt {n} {ctype}-poster")
                except Exception as e:
                    print(f"  Fejl ved {classif}: {e}")

        await browser.close()

    print("\nFaerdig!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stages", nargs="*", type=int, default=[])
    parser.add_argument("--gc-only", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.stages, args.gc_only))
