"""
giro_climb_detail_agent.py — Giroens officielle STIGNINGSPROFILER (RCS).

Rutesiden på giroditalia.it har ud over etapeprofilen en detaljeprofil for
etapens afgørende stigning (typisk målstigningen): navn, fod og top med højde,
længde, højdemeter, gennemsnit, max-hældning og et felt pr. 0,5/1 km med
hældningen. Det er arrangørens egne tal og den rigeste kilde, vi har for
Giro-stigninger uden GPX.

Agenten:
  1. henter billederne fra `https://www.giroditalia.it/en/the-route/`,
  2. lader Claude vision afgøre, om billedet er en stigningsprofil, og aflæse den,
  3. KONTROLLERER aflæsningen — hældningsfelterne vægtet skal ramme den angivne
     gennemsnitshældning (0,6 pp, samme regel som climb_vision_agent.py), og
     top − fod skal ramme de angivne højdemeter og længde × gennemsnit (±6 %),
  4. finder stigningen i stage_climbs (tophøjde ±40 m + navn), og
  5. skriver gradient_sections, max_gradient og arrangørens længde/hældning/
     tophøjde. VeloViewer-id rører den ikke.

Licens: vi udtrækker fakta; billedet vises/gemmes aldrig.

Kør:
  python agents/giro_climb_detail_agent.py --race giro-d-italia-2027 [--write-db]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

import anthropic
import requests
from dotenv import load_dotenv
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent))
from climb_vision_agent import _skemaer, _vaegtet  # noqa: E402
from pcs_stage_overview_agent import aflaes_raa  # noqa: E402

if not isinstance(sys.stdout, io.TextIOWrapper) or (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"
ROUTE_URL = "https://www.giroditalia.it/en/the-route/"

SUM_TOLERANCE_PP = 0.6
HOEJDE_SLOER_PCT = 6.0
TOP_MATCH_M = 40


class Stigningsprofil(BaseModel):
    er_stigningsprofil: bool = Field(description="True KUN hvis billedet er en detaljeprofil af ÉN stigning "
                                                 "(fod til venstre, top til højre, felter med hældning). "
                                                 "False for hel-etape-profiler, kort og andet.")
    navn: str | None = Field(default=None, description="Stigningens navn ved toppen, normal skrivemåde (ikke VERSALER).")
    fod_navn: str | None = None
    fod_m: int | None = Field(default=None, description="Højde ved foden (tallet før fodens navn).")
    top_m: int | None = Field(default=None, description="Højde ved toppen.")
    laengde_km: float | None = Field(default=None, description="Fra boksen, fx '10.1 km'.")
    hoejdemeter: int | None = Field(default=None, description="Fra boksen, fx '1200 m'.")
    gennemsnit: float | None = Field(default=None, description="Fra boksen, fx '11.9%'.")
    max_gradient: float | None = Field(default=None, description="Højeste 'max X %' på billedet.")
    felter: list[float] = Field(default_factory=list,
                                description="De små tal i rækken lige over km-aksen, ét pr. delstrækning, "
                                            "fra foden mod toppen. IKKE de store farvede bånd med %.")


PROMPT = (
    "Er dette en detaljeprofil af én stigning fra Giro d'Italia (RCS)? Den har fodens navn og højde "
    "lodret til venstre, toppens navn og højde lodret til højre, en boks med 'X km / Y m / Z%', "
    "'max N %'-markører og en række små hældningstal lige over km-aksen.\n"
    "Hvis ja: aflæs præcis det, der står. Felterne er de små tal i rækken over km-aksen (typisk ét pr. "
    "0,5 km), fra venstre mod højre — ikke de store farvede bånd. Gæt aldrig; udelad hellere.\n"
    "Hvis nej (hel etape, kort, logo …): er_stigningsprofil=false og resten tomt."
)


def kontroller(s: Stigningsprofil) -> tuple[bool, str, list[dict]]:
    if not (s.navn and s.laengde_km and s.gennemsnit and s.top_m is not None and s.fod_m is not None):
        return False, "mangler nøgletal", []
    forventet = s.laengde_km * s.gennemsnit * 10
    for navn, vaerdi in (("top−fod", s.top_m - s.fod_m), ("angivne højdemeter", s.hoejdemeter)):
        if vaerdi is not None and abs(vaerdi - forventet) > forventet * HOEJDE_SLOER_PCT / 100:
            return False, f"{navn} {vaerdi} m mod længde×gennemsnit {forventet:.0f} m", []
    bedste = None
    for skema, laengder in _skemaer(s.laengde_km, len(s.felter)):
        afv = abs(_vaegtet(s.felter, laengder, s.laengde_km) - s.gennemsnit)
        if bedste is None or afv < bedste[0]:
            bedste = (afv, skema, laengder)
    if bedste is None or bedste[0] > SUM_TOLERANCE_PP:
        return False, (f"felterne passer ikke til gennemsnittet "
                       f"({'afvigelse %.2f pp' % bedste[0] if bedste else f'{len(s.felter)} felter passer ikke til {s.laengde_km} km'})"), []
    km, sek = 0.0, []
    for g, l in zip(s.felter, bedste[2]):
        sek.append({"km": round(km, 2), "gradient": float(g)})
        km += l
    return True, f"{len(s.felter)} felter à {bedste[1]}, afvigelse {bedste[0]:.2f} pp", sek


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--race", required=True)
    ap.add_argument("--write-db", action="store_true")
    a = ap.parse_args()

    html = requests.get(ROUTE_URL, headers={"User-Agent": UA}, timeout=30).text
    aar = a.race.rsplit("-", 1)[-1]
    # Rutens billeder lægges op året før løbet (2027-ruten: oktober/november 2026).
    billeder = list(dict.fromkeys(
        "https://static2.giroditalia.it/" + m for m in
        re.findall(rf'wp-content/uploads/{int(aar) - 1}/1[012]/[A-Za-z0-9_-]+\.(?:jpg|png)', html)))
    anker = json.load(open(REPO_ROOT / "agents" / "profile_image_anchors.json", encoding="utf-8")).get(a.race, {})
    kendte = {st.get("source_url", "").split("?")[0] for st in anker.get("stages", {}).values()}
    billeder = [b for b in billeder if b not in kendte]
    print(f"{len(billeder)} billeder at undersøge (etapeprofiler fraregnet)")

    race = requests.get(f"{SUPABASE_URL}/rest/v1/races?slug=eq.{a.race}&select=id", headers=SB_HEADERS).json()[0]
    climbs = requests.get(
        f"{SUPABASE_URL}/rest/v1/stage_climbs?select=id,name,km_from_start,length_km,avg_gradient,top_hoejde_m,"
        f"stages!inner(race_id,stage_number)&stages.race_id=eq.{race['id']}", headers=SB_HEADERS).json()

    client = anthropic.Anthropic()
    rapport = {"race": a.race, "dato": date.today().isoformat(), "kilde": ROUTE_URL, "fundet": [], "afvist": []}
    for url in billeder:
        s = aflaes_raa(client, url, PROMPT, Stigningsprofil, referer=ROUTE_URL)
        if not s or not s.er_stigningsprofil:
            continue
        ok, note, sek = kontroller(s)
        # Felt-rækken aflæses ikke altid ens (Mortirolo: 26 felter, næste gang 24).
        # Kontrollen afviser fejlaflæsninger, så et nyt forsøg er ufarligt.
        for _ in range(2):
            if ok:
                break
            s2 = aflaes_raa(client, url, PROMPT, Stigningsprofil, referer=ROUTE_URL)
            if s2 and s2.er_stigningsprofil:
                s = s2
                ok, note, sek = kontroller(s)
        print(f"\n{s.navn}: {s.laengde_km} km à {s.gennemsnit}% {s.fod_m}→{s.top_m} m, max {s.max_gradient}% — {note}")
        if not ok:
            rapport["afvist"].append({"url": url, "navn": s.navn, "grund": note})
            continue
        kand = [c for c in climbs if c.get("top_hoejde_m") is not None and abs(c["top_hoejde_m"] - s.top_m) <= TOP_MATCH_M]
        kand.sort(key=lambda c: -SequenceMatcher(None, c["name"].lower(), s.navn.lower()).ratio())
        if not kand:
            print("   ✗ ingen stigning i databasen med den tophøjde")
            rapport["afvist"].append({"url": url, "navn": s.navn, "grund": "ingen DB-stigning med tophøjden"})
            continue
        # Samme stigning kan køres flere gange (Mortirolo ×2 på etape 16):
        # alle passager med samme navn, tophøjde og længde (±15 %) får dataene.
        foerste = kand[0]
        maal = [c for c in kand if c["name"] == foerste["name"]
                and abs((c["length_km"] or 0) - s.laengde_km) <= 0.15 * s.laengde_km]
        if not maal:
            print(f"   ✗ '{foerste['name']}' har længde {foerste['length_km']} km — for langt fra {s.laengde_km}")
            rapport["afvist"].append({"url": url, "navn": s.navn, "grund": "længden passer ikke til DB-stigningen"})
            continue
        data = {"gradient_sections": sek, "max_gradient": s.max_gradient, "length_km": s.laengde_km,
                "avg_gradient": s.gennemsnit, "top_hoejde_m": s.top_m,
                "elevation_m": s.top_m - s.fod_m, "source": "rcs-stigningsprofil"}
        for c in maal:
            print(f"   ✓ → etape {c['stages']['stage_number']} '{c['name']}' "
                  f"(før {c['length_km']} km à {c['avg_gradient']}%)")
            rapport["fundet"].append({"url": url, "climb_id": c["id"], "etape": c["stages"]["stage_number"],
                                      "navn": c["name"], "data": data})
            if a.write_db:
                # Toppen bliver, hvor den er; foden flyttes til den officielle længde.
                top_km = c["km_from_start"] + c["length_km"]
                data = {**data, "km_from_start": round(top_km - s.laengde_km, 1)}
                requests.patch(f"{SUPABASE_URL}/rest/v1/stage_climbs?id=eq.{c['id']}", json=data,
                               headers=SB_HEADERS, timeout=30).raise_for_status()

    ud = REPO_ROOT / "output" / "giro_climb_detail" / f"{a.race}.json"
    ud.parent.mkdir(parents=True, exist_ok=True)
    ud.write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nFundet: {len(rapport['fundet'])}, afvist: {len(rapport['afvist'])}. Rapport: {ud}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
