"""
climb_vision_agent.py
Aflæser stigningsdata fra PCS' per-stigning-profilbilleder med Claude vision.

Hvorfor agenten findes (STG-031, godkendt af ejeren 2026-10-06):
  For mange løb har PCS **ingen klatredata som tekst** — hverken på løbets
  forside, `/info/route` eller `/info/profiles` (verificeret råt for Il
  Lombardia 2026: nul forekomster af Ghisallo, Civiglio, Sormano, Ganda).
  Dataen ligger udelukkende i **billederne** på `/info/profiles`, som ud over
  hel-etape-profilen har én profil pr. stigning med navn, længde,
  gennemsnitshældning, tophøjde og en gradient-tabel pr. kilometer.

  De to eksisterende veje er blindgyder:
    - `gpx_climb_agent.py` scraper HTML'en og finder derfor intet. Når den
      undtagelsesvis finder noget, **fabrikerer** den oven i købet
      `gradient_sections` ud af en sinuskurve (`generate_gradient_sections()`),
      hvilket er opdigtet data.
    - `profile_reader_agent.py` kører ganske vist vision, men på
      `stages.elevation_image_url`, som efter LEG-001 peger på **vores eget**
      genererede billede. Det har ingen stigningsnavne, netop fordi
      `stage_climbs` er tom. Cirkulær blindgyde.

  Denne agent læser kilden, hvor dataen faktisk er.

Hvad der gør et fund troværdigt — tre uafhængige kontroller:

  1. SUMKONTROL. Gradient-tabellen vægtes med hver delstræknings længde og
     holdes op mod den gennemsnitshældning, PCS selv angiver. Madonna del
     Ghisallo: (7,7+10,2+8,5+7,9+2,0+0,1-2,8+6,4)·1 km + 9,2·0,6 km = 45,52,
     divideret med 8,6 km = 5,29 % mod PCS' angivne 5,3 %. Stemmer tabellen
     ikke med gennemsnittet, er billedet læst forkert, og stigningen afvises.
  2. LÆNGDEKONTROL. Antal felter i tabellen skal passe til længden. En tabel
     med 4 felter til en 9 km lang stigning er en fejllæsning.
  3. GPX-KONTROL (når ruten findes). Stigningen genfindes i GPX-sporet ud fra
     tophøjde, længde og højdemeter. Det giver `km_from_start`, som billedet
     ikke indeholder, OG er et uafhængigt vidne på, at tallene er rigtige.
     Uden GPX skrives stigningen stadig, men uden km-placering.

En stigning, der ikke består 1 og 2, skrives ALDRIG. Det er `CLAUDE.md` §6:
kan data ikke verificeres, publicér det ikke.

Licens: vi udtrækker FAKTA (terrænets hældning langs en offentlig vej) og
gemmer aldrig kildebilledet — `profile_image_url` sættes ikke, og frontenden
viser i forvejen kun `source='generated'`-billeder (LEG-001). Samme skelnen som
`aso_roadbook_agent.py` og `profile_image_digitizer.py`, som ejeren godkendte
2026-08-02.

Skriver kun med --write-db. Uden flaget er kørslen en ren rapport.

    python climb_vision_agent.py --race il-lombardia-2026
    python climb_vision_agent.py --race il-lombardia-2026 --write-db
    python climb_vision_agent.py --race tour-de-france-2026 --stage 14 --write-db
    python climb_vision_agent.py --race il-lombardia-2026 --write-db --overwrite
"""

from __future__ import annotations

import argparse
import base64
import io

import os
import re
import sys

import anthropic
import requests
from dotenv import load_dotenv
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Importeres FOER stdout pakkes ind. climb_profile_generator pakker selv stdout
# ind ved import; gjorde vi det foerst, ville vores egen wrapper miste sin
# sidste reference, blive frigivet og lukke den underliggende buffer — hvorefter
# alt videre print doer med "I/O operation on closed file". Samme faelde er
# beskrevet i data_sources.py._agent_attr().
import climb_profile_generator as cpg

if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding.lower() != "utf-8":
    _STDOUT = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stdout = _STDOUT

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")

SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

PCS_BASE = "https://www.procyclingstats.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0"

MODEL = "claude-opus-5"

# Hvor meget den vægtede gradient-tabel må afvige fra PCS' egen angivne
# gennemsnitshældning. PCS runder selv til én decimal, og aflæsningen af et
# enkelt felt kan ramme ved siden af, men 0,6 procentpoint er langt mere end
# afrunding — det er en fejllæsning.
SUM_TOLERANCE_PP = 0.6

# Tabellen har ét felt pr. kilometer, så antallet skal matche længden rundet op.
# Ét felts slør rummer, at PCS af og til deler den sidste stump i to.
LAENGDE_SLOER_FELTER = 1

# GPX-kontrollen. Tophøjden er det skarpeste signal (den er aflæst direkte fra
# billedet), så den får det snævreste vindue.
GPX_TOP_SLOER_M = 60
GPX_LAENGDE_SLOER_PCT = 25.0
GPX_STIGNING_SLOER_PCT = 30.0


# ── Det, vision skal svare med ───────────────────────────────────────────────

class Stigning(BaseModel):
    """Én stigning, som den står på PCS' profilbillede."""

    navn: str = Field(
        description="Stigningens navn alene, fx 'Madonna del Ghisallo'. UDEN "
                    "parenteser som '(last 1.6 km - 8.2%)' og uden kategori."
    )
    laengde_km: float = Field(description="Stigningens længde i km, fx 8.6")
    gennemsnit_gradient: float = Field(
        description="Gennemsnitshældning i procent, fx 5.3"
    )
    top_hoejde_m: int | None = Field(
        default=None,
        description="Højden i meter over havet ved TOPPEN, fx 739. Null hvis "
                    "den ikke står på billedet."
    )
    gradienter_pr_km: list[float] = Field(
        description="Tallene i kasserne langs bunden, ét pr. delstrækning, i "
                    "rækkefølge fra foden mod toppen. Negative tal tages med "
                    "som negative, fx [7.7, 10.2, 8.5, 7.9, 2.0, 0.1, -2.8, 6.4, 9.2]."
    )


VISION_PROMPT = (
    "Dette er ProCyclingStats' profilbillede af ÉN stigning i et cykelløb.\n\n"
    "Aflæs præcis det, der står på billedet:\n"
    "- Stigningens navn (øverst). Tag KUN navnet med — ikke parenteser som "
    "\"(last 1.6 km - 8.2%)\", som er en note om de sidste kilometer.\n"
    "- Længden i km og gennemsnitshældningen i procent (står typisk som "
    "\"739 m - 8.6 Km at 5.3 %\").\n"
    "- Tophøjden i meter over havet, hvis den står der.\n"
    "- Tallene i kasserne langs bunden: det er hældningen for hver delstrækning, "
    "fra foden til venstre mod toppen til højre. Læs dem ALLE, i rækkefølge, og "
    "husk fortegnet — et nedadgående stykke står som et negativt tal.\n\n"
    "Gæt aldrig. Står et tal ikke klart på billedet, så udelad det hellere."
)


# ── Databasen ────────────────────────────────────────────────────────────────

def sb_get(table: str, query: str) -> list[dict]:
    res = requests.get(f"{SUPABASE_URL}/rest/v1/{table}?{query}",
                       headers=SB_HEADERS, timeout=30)
    return res.json() if res.ok and isinstance(res.json(), list) else []


def hent_race(slug: str) -> dict | None:
    rows = sb_get("races", f"slug=eq.{slug}&select=id,name,slug,pcs_url&limit=1")
    return rows[0] if rows else None


def hent_stages(race_id: str, stage_number: int | None) -> list[dict]:
    q = (f"race_id=eq.{race_id}&select=id,stage_number,distance_km,stage_type,"
         f"pcs_stage_url,source_url&order=stage_number.asc")
    if stage_number is not None:
        q += f"&stage_number=eq.{stage_number}"
    return sb_get("stages", q)


def antal_stigninger(stage_id: str) -> int:
    return len(sb_get("stage_climbs", f"stage_id=eq.{stage_id}&select=id"))


def slet_stigninger(stage_id: str) -> None:
    requests.delete(f"{SUPABASE_URL}/rest/v1/stage_climbs?stage_id=eq.{stage_id}",
                    headers=SB_HEADERS, timeout=30)


def indsaet_stigninger(raekker: list[dict]) -> bool:
    if not raekker:
        return True
    res = requests.post(f"{SUPABASE_URL}/rest/v1/stage_climbs",
                        json=raekker, headers=SB_HEADERS, timeout=30)
    if not res.ok:
        print(f"    [DB FEJL] {res.status_code} — {res.text[:200]}")
    return res.ok


# ── PCS ──────────────────────────────────────────────────────────────────────

def profiles_url(race: dict, stage: dict) -> str | None:
    """Undersiden med ét profilbillede pr. stigning.

    Et etapeløb har den pr. etape (…/stage-7/info/profiles); et endagsløb har
    kun løbets forside, og så hænger undersiden på den.
    """
    base = stage.get("pcs_stage_url") or stage.get("source_url") or race.get("pcs_url")
    if not base:
        return None
    return base.rstrip("/") + "/info/profiles"


def klatrebilleder(side_url: str) -> list[str]:
    """Per-stigning-billederne, i rækkefølge langs ruten.

    PCS navngiver dem "<løb>-climb-<hash>.jpg", "…-climb-n2-…", "…-climb-n8-…".
    Nummeret er rækkefølgen; det første har intet nummer. Hel-etape-profilen
    ("-profile-"), rutekortet ("-map-") og målzonen ("-finish-") er IKKE
    stigninger og filtreres fra — samme skelnen som elevation_image_agent.py
    laver, blot med modsat fortegn.
    """
    try:
        res = requests.get(side_url, headers={"User-Agent": UA}, timeout=30)
    except requests.RequestException:
        return []
    if not res.ok:
        return []

    fundet: list[tuple[int, str]] = []
    for src in re.findall(r'src="([^"]*profiles/[^"]*)"', res.text):
        fil = src.split("/")[-1]
        if "-climb" not in fil:
            continue
        m = re.search(r"-climb-n(\d+)-", fil)
        nr = int(m.group(1)) if m else 1
        url = src if src.startswith("http") else f"{PCS_BASE}/{src.lstrip('/')}"
        if url not in [u for _, u in fundet]:
            fundet.append((nr, url))
    return [u for _, u in sorted(fundet)]


def hent_billede(url: str, referer: str) -> tuple[bytes, str] | None:
    """PCS svarer 403 på et billede uden Referer — derfor sendes den altid."""
    try:
        res = requests.get(url, headers={"User-Agent": UA, "Referer": referer},
                           timeout=30)
    except requests.RequestException:
        return None
    ctype = (res.headers.get("content-type") or "").split(";")[0].strip()
    if not res.ok or not ctype.startswith("image/"):
        return None
    return res.content, ctype


# ── Vision ───────────────────────────────────────────────────────────────────

def aflaes_stigning(client: anthropic.Anthropic, billede: bytes,
                    media_type: str) -> Stigning | None:
    try:
        svar = client.messages.parse(
            model=MODEL,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64.standard_b64encode(billede).decode("ascii"),
                    }},
                    {"type": "text", "text": VISION_PROMPT},
                ],
            }],
            output_format=Stigning,
        )
    except anthropic.APIError as e:
        print(f"    [vision-fejl] {type(e).__name__}: {e}")
        return None
    if svar.stop_reason == "refusal":
        print("    [vision-fejl] modellen afviste billedet")
        return None
    return svar.parsed_output


# ── Kontrollerne ─────────────────────────────────────────────────────────────

def _skemaer(laengde_km: float, antal: int) -> list[tuple[str, list[float]]]:
    """Mulige inddelinger af gradient-tabellen.

    PCS deler ikke altid i hele kilometer: Madonna del Ghisallo har 9 felter
    til 8,6 km (1 km + en rest), mens korte stigninger som San Fermo della
    Battaglia deles finere. At antage 1 km pr. felt afviste derfor en korrekt
    aflæsning (set 2026-10-06). Vi gætter ikke på inddelingen — vi prøver de
    tre, PCS faktisk bruger, og lader SUMKONTROLLEN afgøre hvilken der holder.
    Rammer ingen af dem, er billedet læst forkert.
    """
    if antal < 1 or laengde_km <= 0:
        return []
    ud: list[tuple[str, list[float]]] = []
    for navn, trin in (("1 km", 1.0), ("0,5 km", 0.5)):
        helt = antal - 1
        rest = laengde_km - helt * trin
        if 0 < rest <= trin * 2:
            ud.append((navn, [trin] * helt + [round(rest, 3)]))
    ud.append(("jævn", [laengde_km / antal] * antal))
    return ud


def _vaegtet(gradienter: list[float], laengder: list[float],
             laengde_km: float) -> float:
    return sum(g * l for g, l in zip(gradienter, laengder)) / laengde_km


def kontrollér(s: Stigning) -> tuple[bool, str, list[float]]:
    """Summer gradient-tabellen og holder den op mod PCS' eget gennemsnit.

    Returnerer (godkendt, forklaring, de sektionslængder der passede).
    """
    if not s.navn.strip():
        return False, "intet navn aflæst", []
    if s.laengde_km <= 0 or s.laengde_km > 60:
        return False, f"urimelig længde {s.laengde_km} km", []
    if len(s.gradienter_pr_km) < 2:
        return False, "for få felter i gradient-tabellen", []

    bedste = None
    for navn, laengder in _skemaer(s.laengde_km, len(s.gradienter_pr_km)):
        vaegtet = _vaegtet(s.gradienter_pr_km, laengder, s.laengde_km)
        afvig = abs(vaegtet - s.gennemsnit_gradient)
        if bedste is None or afvig < bedste[0]:
            bedste = (afvig, navn, vaegtet, laengder)

    if bedste is None:
        return False, "tabellen passer ikke til længden", []

    afvig, navn, vaegtet, laengder = bedste
    if afvig > SUM_TOLERANCE_PP:
        return False, (f"tabellen giver {vaegtet:.2f} % mod PCS' angivne "
                       f"{s.gennemsnit_gradient} % (afvigelse {afvig:.2f} pp, "
                       f"bedste inddeling: {navn})"), []
    return True, (f"tabel {vaegtet:.2f} % ≈ angivet {s.gennemsnit_gradient} % "
                  f"({len(laengder)} felter à {navn})"), laengder


def hoejdemeter(s: Stigning, laengder: list[float]) -> int:
    """Stigningens nettohøjdemeter, regnet af tabellen.

    BEMÆRK: `stage_climbs.elevation_m` er højdemeter-GEVINSTEN, ikke tophøjden
    — det er dét, `climb_profile_generator.within_tolerance()` sammenligner GPX
    med. Tophøjden har ingen kolonne, og at skrive den i elevation_m er præcis
    den fejl, Vuelta-dataene lider af.
    """
    return round(sum(g * l for g, l in zip(s.gradienter_pr_km, laengder)) * 10)


def sektioner(s: Stigning, laengder: list[float]) -> list[dict]:
    """gradient_sections med hvert felts afstand fra stigningens fod."""
    ud, km = [], 0.0
    for g, l in zip(s.gradienter_pr_km, laengder):
        ud.append({"km": round(km, 2), "gradient": float(g)})
        km += l
    return ud


# ── GPX: hvor på ruten ligger stigningen? ────────────────────────────────────

def hent_gpx(race_slug: str, stage_number: int, officiel_km: float | None):
    """GPX-sporet med kumulative afstande, skaleret til den officielle distance."""
    punkter = cpg.download_stage_gpx(race_slug, stage_number)
    if not punkter or len(punkter) < 100:
        return None
    cum = cpg.cumulative_distances_km(punkter)
    skala = (officiel_km / cum[-1]) if (officiel_km and cum[-1] > 0) else 1.0
    return punkter, cum, skala


def find_i_gpx(gpx, s: Stigning, laengder: list[float],
               vindue: tuple[float, float] | None = None) -> tuple[float, str] | None:
    """Finder stigningens fod i GPX-sporet og returnerer (km_fra_start, note).

    Søger globalt: billedet fortæller ikke hvor på ruten stigningen ligger, så
    vi kan ikke bruge climb_profile_generator.locate_climb_segment(), der
    forfiner omkring en kendt position. Tophøjden er ankeret — den er aflæst
    direkte og er langt det skarpeste signal.
    """
    if s.top_hoejde_m is None:
        return None
    punkter, cum, skala = gpx
    forventet_stigning = hoejdemeter(s, laengder)

    bedste = None
    for j in range(len(punkter)):
        if abs(punkter[j][2] - s.top_hoejde_m) > GPX_TOP_SLOER_M:
            continue
        if vindue and not (vindue[0] <= cum[j] * skala <= vindue[1]):
            continue
        # Uden et vindue skal toppen være et lokalt maksimum — ellers rammer vi
        # et vilkårligt punkt på vej op ad den rigtige stigning. MED et vindue
        # er rækkefølgen allerede bundet af naboerne, og kravet kan slækkes:
        # en navngiven top ligger ikke altid på et maksimum. Selvinos top (918 m)
        # sidder midt på en stigning, der fortsætter til 1020 m, og blev derfor
        # afvist af det hårde krav (set 2026-10-06).
        if not vindue:
            lav, hoej = max(0, j - 60), min(len(punkter), j + 60)
            if punkter[j][2] < max(p[2] for p in punkter[lav:hoej]) - 5:
                continue

        maal = cum[j] - s.laengde_km / skala
        i = j
        while i > 0 and cum[i] > maal:
            i -= 1
        if i >= j:
            continue

        laengde = (cum[j] - cum[i]) * skala
        stigning = punkter[j][2] - punkter[i][2]
        if abs(laengde - s.laengde_km) / s.laengde_km * 100 > GPX_LAENGDE_SLOER_PCT:
            continue
        if forventet_stigning > 0 and (
                abs(stigning - forventet_stigning) / forventet_stigning * 100
                > GPX_STIGNING_SLOER_PCT):
            continue

        score = (abs(punkter[j][2] - s.top_hoejde_m) / GPX_TOP_SLOER_M
                 + abs(laengde - s.laengde_km) / s.laengde_km
                 + abs(stigning - forventet_stigning) / max(1, forventet_stigning))
        if bedste is None or score < bedste[0]:
            bedste = (score, round(cum[i] * skala, 1), laengde, stigning,
                      round(punkter[j][2]))

    if bedste is None:
        return None
    _, km, laengde, stigning, top = bedste
    return km, (f"GPX: fod ved km {km}, {laengde:.1f} km, +{stigning:.0f} m, "
                f"top {top} m (billedet: {s.laengde_km} km, "
                f"+{forventet_stigning} m, top {s.top_hoejde_m} m)")


# ── Kørslen ──────────────────────────────────────────────────────────────────

def behandl_etape(client, race: dict, stage: dict, write_db: bool,
                  overwrite: bool) -> int:
    nr = stage["stage_number"]
    print(f"\n[E{nr}] {race['name']}")

    if not overwrite and antal_stigninger(stage["id"]) > 0:
        print("  Har allerede stigninger — springer over (brug --overwrite)")
        return 0

    side = profiles_url(race, stage)
    if not side:
        print("  Ingen PCS-URL på etapen — kan ikke finde profilsiden")
        return 0

    billeder = klatrebilleder(side)
    print(f"  {side}")
    print(f"  {len(billeder)} per-stigning-billede(r)")
    if not billeder:
        print("  Ingen stigningsbilleder på siden — etapen efterlades uden "
              "stigninger (aldrig gættet data)")
        return 0

    gpx = hent_gpx(race["slug"], nr,
                   float(stage["distance_km"]) if stage.get("distance_km") else None)
    print("  GPX: " + ("hentet — km-placering kan udledes"
                       if gpx else "ingen rute, km-placering udelades"))

    godkendte: list[dict] = []
    for i, url in enumerate(billeder, start=1):
        hentet = hent_billede(url, side)
        if not hentet:
            print(f"  {i}. kunne ikke hentes: {url}")
            continue

        s = aflaes_stigning(client, *hentet)
        if s is None:
            continue

        ok, grund, laengder = kontrollér(s)
        if not ok:
            print(f"  {i}. AFVIST  {s.navn}: {grund}")
            continue

        km_fra_start = None
        gpx_note = "ingen GPX at kontrollere mod"
        if gpx:
            fund = find_i_gpx(gpx, s, laengder)
            if fund:
                km_fra_start, gpx_note = fund
            else:
                gpx_note = "kunne ikke genfindes i GPX — km udelades"

        print(f"  {i}. OK      {s.navn} — {s.laengde_km} km @ "
              f"{s.gennemsnit_gradient} %, +{hoejdemeter(s, laengder)} m")
        print(f"              sum: {grund}")
        print(f"              {gpx_note}")

        godkendte.append({
            "stage_id":          stage["id"],
            "name":              s.navn.strip(),
            "km_from_start":     km_fra_start,
            "length_km":         s.laengde_km,
            "elevation_m":       hoejdemeter(s, laengder),
            "avg_gradient":      s.gennemsnit_gradient,
            "max_gradient":      max(s.gradienter_pr_km),
            "gradient_sections": sektioner(s, laengder),
            "sort_order":        i,
            "source":            "pcs_climb_profile",
            # Bæres kun med til anden runde og fjernes før skrivning.
            "_stigning":         s,
            "_laengder":         laengder,
        })

    if not godkendte:
        print("  Ingen stigninger bestod kontrollen — intet skrevet")
        return 0

    # Anden runde: en stigning uden km afgrænses af sine naboer. PCS' egen
    # nummerering ER rækkefølgen langs ruten, så en stigning mellem to fundne
    # naboer kan kun ligge imellem dem — og inden for det vindue er der ingen
    # tvetydighed tilbage at beskytte sig mod.
    if gpx:
        for n, r in enumerate(godkendte):
            if r["km_from_start"] is not None:
                continue
            foer = [x["km_from_start"] for x in godkendte[:n]
                    if x["km_from_start"] is not None]
            efter = [x["km_from_start"] for x in godkendte[n + 1:]
                     if x["km_from_start"] is not None]
            lav = max(foer) if foer else 0.0
            hoej = min(efter) if efter else float(stage.get("distance_km") or 0) or 1e9
            if hoej <= lav:
                continue
            fund = find_i_gpx(gpx, r["_stigning"], r["_laengder"], (lav, hoej))
            if fund:
                r["km_from_start"] = fund[0]
                print(f"  (2. runde) {r['name']} placeret mellem km {lav:.0f} "
                      f"og {hoej:.0f} — {fund[1]}")

    for r in godkendte:
        r.pop("_stigning", None)
        r.pop("_laengder", None)

    # Rækkefølgen langs ruten, når GPX gav os km. Ellers PCS' egen nummerering.
    med_km = [r for r in godkendte if r["km_from_start"] is not None]
    if len(med_km) == len(godkendte):
        godkendte.sort(key=lambda r: r["km_from_start"])
        for n, r in enumerate(godkendte, start=1):
            r["sort_order"] = n

    if not write_db:
        print(f"  {len(godkendte)} stigning(er) klar — IKKE skrevet "
              "(kør med --write-db)")
        return 0

    if overwrite:
        slet_stigninger(stage["id"])
    if indsaet_stigninger(godkendte):
        print(f"  ✓ {len(godkendte)} stigning(er) skrevet til stage_climbs")
        return len(godkendte)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Aflæser stigninger fra PCS' per-stigning-profilbilleder")
    p.add_argument("--race", required=True)
    p.add_argument("--stage", type=int, default=None)
    p.add_argument("--write-db", action="store_true",
                   help="Skriv til databasen. Uden flaget er kørslen en rapport.")
    p.add_argument("--overwrite", action="store_true",
                   help="Erstat etapens eksisterende stigninger")
    args = p.parse_args()

    if not ANTHROPIC_KEY:
        print("FEJL: ANTHROPIC_API_KEY mangler i .env")
        return 1
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("FEJL: SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY mangler i .env")
        return 1

    race = hent_race(args.race)
    if not race:
        print(f"Løb ikke fundet: {args.race}")
        return 1

    stages = hent_stages(race["id"], args.stage)
    if not stages:
        print("Ingen etaper fundet")
        return 1

    print(f"climb_vision_agent.py — {race['slug']} ({len(stages)} etape(r))")
    print(f"Model: {MODEL}" + ("" if args.write_db else "  ·  TØRLØB (skriver intet)"))

    client = anthropic.Anthropic()
    i_alt = 0
    for stage in stages:
        # Flade etaper og enkeltstarter har ingen kategoriserede stigninger at
        # hente — vi sparer både kald og støj i loggen.
        if (stage.get("stage_type") or "") in ("flat", "tt", "itt"):
            print(f"\n[E{stage['stage_number']}] springes over "
                  f"({stage['stage_type']})")
            continue
        i_alt += behandl_etape(client, race, stage, args.write_db, args.overwrite)

    print(f"\nFærdig: {i_alt} stigning(er) skrevet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
