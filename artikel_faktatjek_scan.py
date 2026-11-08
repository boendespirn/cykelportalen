"""
artikel_faktatjek_scan.py
Faktatjekker de allerede publicerede artikler med samme tjek, som nye
artikler får før publicering (artikel_faktatjek.py). Lavet 2026-11-08, da
publiceringen blev fuldautomatisk: de gamle artikler blev skrevet, før
kilden blev hentet i fuld længde, og nogle er fyldt op med opdigtede detaljer
(Seixas-artiklen).

Udfald pr. artikel:
  publicer, uændret  → intet gøres
  publicer, rettet   → faktatjekkets rettelser gemmes (små indgreb, kun
                       fjernelse/omskrivning af påstande uden grundlag)
  kasser             → artiklen tages af siden (status rejected) — "hvis den
                       står skrevet med den fejl skal den bare fjernes"
  kilden kan ikke hentes → kan ikke verificeres → tages af siden

Kør:  python artikel_faktatjek_scan.py            (rapport, intet gemt)
      python artikel_faktatjek_scan.py --apply    (gemmer udfaldene)
"""

import argparse
import io
import json
import os
import sys

import requests
from anthropic import Anthropic
from dotenv import load_dotenv

import artikel_faktatjek as F
import artikel_links

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
HDR = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--gem-rapport", help="skriv udfaldene som JSON til denne fil")
    args = ap.parse_args()

    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    ryttere = F.hent_ryttere(SUPABASE_URL, SUPABASE_KEY)
    race_slugs = artikel_links.hent_race_slugs(SUPABASE_URL, SUPABASE_KEY)
    artikler = requests.get(
        f"{SUPABASE_URL}/rest/v1/news_articles?select=id,slug,title,content,source_url"
        # Kun omskrevne nyheder: artikler uden kildeadresse er redaktionelle
        # (Giro-guiderne) og kan ikke tjekkes mod en kilde.
        f"&status=eq.published&faktatjek=is.null&source_url=not.is.null"
        f"&order=published_at.desc&limit=500",
        headers=HDR, timeout=60).json()
    print(f"{len(artikler)} publicerede artikler uden faktatjek\n")

    udfald = []
    for a in artikler:
        kilde = F.hent_kildetekst(a["source_url"]) if a.get("source_url") else ""
        fk = F.faktatjek(client, kilde, a["title"], a["content"], ryttere)
        r = fk["rapport"]
        rettet = fk["godkendt"] and (fk["content"] != a["content"] or fk["titel"] != a["title"])
        handling = "uændret" if fk["godkendt"] and not rettet else ("rettet" if fk["godkendt"] else "fjernet")
        print(f"[{handling:>8}] {a['slug'][:70]}  (kilde {r['kilde_tegn']} tegn)")
        if handling != "uændret":
            print(f"           {r.get('begrundelse', '')[:200]}")
        for p in r.get("fjernede_paastande", []):
            print(f"           - {p[:160]}")
        udfald.append({"id": a["id"], "slug": a["slug"], "handling": handling, "rapport": r,
                       "titel": fk["titel"], "content": fk["content"]})

        if not args.apply:
            continue
        patch = {"faktatjek": r}
        if handling == "rettet":
            patch["content"] = artikel_links.rens(fk["content"], race_slugs)[0]
            patch["title"] = fk["titel"]
        elif handling == "fjernet":
            patch["status"] = "rejected"
        p = requests.patch(f"{SUPABASE_URL}/rest/v1/news_articles?id=eq.{a['id']}", json=patch,
                           headers={**HDR, "Content-Type": "application/json",
                                    "Prefer": "return=minimal"}, timeout=30)
        if not p.ok:
            print(f"           [FEJL] {p.status_code} {p.text[:200]}")

    if args.gem_rapport:
        with open(args.gem_rapport, "w", encoding="utf-8") as f:
            json.dump(udfald, f, ensure_ascii=False, indent=1)
    t = {h: sum(1 for u in udfald if u["handling"] == h) for h in ("uændret", "rettet", "fjernet")}
    print(f"\n{t['uændret']} uændret, {t['rettet']} rettet, {t['fjernet']} fjernet"
          + ("" if args.apply else " — tørløb, intet gemt"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
