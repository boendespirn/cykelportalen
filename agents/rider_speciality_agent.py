"""
rider_speciality_agent.py
Opdaterer speciality og date_of_birth for alle ryttere der mangler det i DB.
Bruger Playwright til at omgaa Cloudflare paa individuelle rytter-sider.

PCS ændrede HTML-struktur: data sidder nu i ul.list (ikke ul.infolist)
og speciality udledes fra hoejeste score i .pps-sektionen.

Koor: python rider_speciality_agent.py
Beregnet koretid: ~20-25 min for 919 ryttere (3 samtidige sider).
Re-run er sikkert: henter kun ryttere med speciality = NULL.
"""

import os
import re
import sys
import io
import asyncio
import requests
from datetime import datetime
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

# Antal samtidige Playwright-sider
CONCURRENCY = 3

# PCS .pps kategori-navne -> vores interne speciality-vaerdier
# Matcher STAGE_SPECIALISTS i stage/[n]/page.tsx
PCS_CATEGORY_TO_SPECIALITY: dict[str, str] = {
    "onedayraces": "Classics",
    "gc":          "GC",
    "sprint":      "Sprinter",
    "climber":     "Climber",
    "tt":          "Time trialist",
    "hills":       "Puncheur",
}

DB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

# JavaScript korer i browseren for at udtraekke data fra den nye PCS HTML-struktur
_EXTRACT_JS = """() => {
    // DOB: find ul.list der indeholder 'Date of birth'
    let dob = null;
    for (const ul of document.querySelectorAll('ul.list')) {
        if (!ul.innerText.includes('Date of birth')) continue;
        const full = [...ul.querySelectorAll('li')].map(li => li.innerText.trim()).join(' ');
        const m = full.match(/(\\d{1,2})\\w*\\s+(\\w+)\\s+(\\d{4})/);
        if (m) dob = m[1] + ' ' + m[2] + ' ' + m[3];
        break;
    }

    // Speciality: find .pps-kategori med hoejest score
    let maxVal = -1, maxCat = null;
    for (const li of document.querySelectorAll('.pps li')) {
        const valEl = li.querySelector('.xvalue');
        const catEl = li.querySelector('.xtitle a');
        if (!valEl || !catEl) continue;
        const val = parseInt(valEl.innerText.replace(/[^0-9]/g, ''), 10);
        const cat = catEl.innerText.trim().toLowerCase().replace(/\\s+/g, '');
        if (!isNaN(val) && val > maxVal) { maxVal = val; maxCat = cat; }
    }

    return [maxCat, dob];
}"""


# ── Database ──────────────────────────────────────────────────────────────────

def get_riders_to_update() -> list[dict]:
    """Henter ryttere med speciality = NULL og en source_url."""
    url = (
        f"{SUPABASE_URL}/rest/v1/riders"
        "?speciality=is.null"
        "&source_url=not.is.null"
        "&select=id,name,source_url"
        "&order=name"
        "&limit=1000"
    )
    res = requests.get(url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
    res.raise_for_status()
    return res.json()


def patch_rider(rider_id: str, speciality: str | None, dob: str | None) -> None:
    data: dict = {}
    if speciality:
        data["speciality"] = speciality
    if dob:
        data["date_of_birth"] = dob
    if not data:
        return
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/riders?id=eq.{rider_id}",
        json=data,
        headers=DB_HEADERS,
    )
    if not res.ok:
        print(f"    [DB FEJL] {res.status_code} {res.text[:120]}")


# ── Scraping ──────────────────────────────────────────────────────────────────

async def scrape_one(browser, rider: dict) -> tuple[str | None, str | None]:
    """Returnerer (speciality, raw_dob). Begge kan vaere None."""
    page = await browser.new_page(user_agent=CF_UA)
    try:
        await page.goto(rider["source_url"], wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        title = await page.title()
        if any(s in title.lower() for s in ["just a moment", "403", "404", "not found", "access denied"]):
            return None, None

        result = await page.evaluate(_EXTRACT_JS)
        if not result or not isinstance(result, list) or len(result) < 2:
            return None, None

        pcs_cat, dob_raw = result[0], result[1]
        speciality = PCS_CATEGORY_TO_SPECIALITY.get(pcs_cat, None) if pcs_cat else None
        return speciality, dob_raw

    except Exception as e:
        print(f"    FEJL ({rider['name']}): {e}")
        return None, None
    finally:
        await page.close()


def parse_dob(raw: str | None) -> str | None:
    """Konverterer DOB-streng til ISO YYYY-MM-DD."""
    if not raw:
        return None
    m = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
    if m:
        return m.group(1)
    for fmt in ("%d %B %Y", "%B %d, %Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw.strip()[:20], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


# ── Hoved ────────────────────────────────────────────────────────────────────

async def run() -> None:
    riders = get_riders_to_update()
    total = len(riders)
    print(f"Fandt {total} ryttere der mangler speciality\n")

    if not riders:
        print("Alle ryttere er allerede opdateret!")
        return

    updated = 0
    failed = 0

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        for batch_start in range(0, total, CONCURRENCY):
            batch = riders[batch_start : batch_start + CONCURRENCY]
            tasks = [scrape_one(browser, r) for r in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for rider, result in zip(batch, results):
                idx = batch_start + batch.index(rider) + 1
                tag = f"[{idx}/{total}]"

                if isinstance(result, Exception):
                    print(f"  {tag} {rider['name']} -> UNDTAGELSE: {result}")
                    failed += 1
                    continue

                speciality, dob_raw = result
                dob = parse_dob(dob_raw)

                if speciality or dob:
                    patch_rider(rider["id"], speciality, dob)
                    dob_str = f", foedt {dob}" if dob else ""
                    spec_str = speciality or "ingen speciality"
                    print(f"  {tag} {rider['name']} -> {spec_str}{dob_str}")
                    updated += 1
                else:
                    print(f"  {tag} {rider['name']} -> ingen data")
                    failed += 1

        await browser.close()

    print(f"\nFaerdig: {updated} opdateret, {failed} uden data / fejl")


if __name__ == "__main__":
    asyncio.run(run())
