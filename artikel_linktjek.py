"""
artikel_linktjek.py
Workerens løbende tjek af links i de publicerede nyhedsartikler (ejerens
ønske 2026-11-08: "for mange linkende ord" og links til 404-sider).

To lag:
  1. artikel_links.rens() — højst 2 interne links, hvert mål én gang, kun
     sider, der findes i databasen. Fanger også HTML-<a>, ikke kun markdown.
  2. Live-tjek: hver tilbageværende intern sti hentes på klassementet.dk.
     Kun et klart 404 (to gange) fjerner linket — en timeout eller 5xx er
     siden, der hikker, ikke linket, der er dødt, og bliver kun rapporteret.

Et link, der fjernes, bliver til sin ankertekst; teksten ændres aldrig.

Kør:  python artikel_linktjek.py            (viser kun, hvad der ville ske)
      python artikel_linktjek.py --apply    (retter artiklerne)
"""

import argparse
import io
import os
import sys

import requests
from dotenv import load_dotenv

import artikel_links

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
HDR = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def live_status(sti: str) -> int | None:
    """HTTP-status for stien på sitet (efter videresendelser) — None ved
    netværksfejl."""
    try:
        return requests.get(artikel_links.SITE + sti, timeout=30,
                            headers={"User-Agent": "klassementet-linktjek"}).status_code
    except requests.RequestException:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    race_slugs = artikel_links.hent_race_slugs(SUPABASE_URL, SUPABASE_KEY)
    res = requests.get(f"{SUPABASE_URL}/rest/v1/news_articles?select=id,slug,content"
                       f"&status=eq.published&order=published_at.desc&limit=2000",
                       headers=HDR, timeout=60)
    res.raise_for_status()
    artikler = res.json()
    print(f"{len(artikler)} publicerede artikler, {len(race_slugs)} løb i databasen")

    # Lag 1, og de stier der står tilbage
    rensede = {a["id"]: artikel_links.rens(a["content"], race_slugs) for a in artikler}
    stier = {s for indhold, _ in rensede.values() for s in artikel_links.interne_stier(indhold)}

    # Lag 2: live
    doede, usikre = set(), []
    for sti in sorted(stier):
        status = live_status(sti)
        if status == 404 and live_status(sti) == 404:
            doede.add(sti)
        elif status != 200:
            usikre.append(f"{sti} ({status or 'netværksfejl'})")
    print(f"{len(stier)} interne sider tjekket live: {len(doede)} døde, {len(usikre)} usikre")
    for u in usikre:
        print(f"  [USIKKER] {u} — rørt ikke, tjekkes igen næste gang")

    rettet = fejl = 0
    for a in artikler:
        indhold, aendringer = rensede[a["id"]]
        if doede:
            indhold, flere = artikel_links.rens(indhold, race_slugs, doede)
            aendringer += flere
        if not aendringer:
            continue
        print(f"\n  {a['slug']}")
        for t in aendringer:
            print(f"    - {t}")
        if not args.apply:
            continue
        p = requests.patch(f"{SUPABASE_URL}/rest/v1/news_articles?id=eq.{a['id']}",
                           json={"content": indhold},
                           headers={**HDR, "Content-Type": "application/json",
                                    "Prefer": "return=minimal"}, timeout=30)
        if p.ok:
            rettet += 1
        else:
            fejl += 1
            print(f"    [FEJL] kunne ikke gemme: {p.status_code} {p.text[:200]}")

    if args.apply:
        print(f"\n{rettet} artikler rettet, {fejl} fejl")
    else:
        print("\nTørløb — intet gemt. Kør med --apply for at rette.")
    return 1 if fejl else 0


if __name__ == "__main__":
    sys.exit(main())
