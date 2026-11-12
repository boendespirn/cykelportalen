"""
pcs_stage_overview_agent.py — stigninger fra PCS' hel-etape-profiler.

Til løb, hvor PCS endnu kun har ét profilbillede pr. etape (ingen `-climb`-
billeder pr. stigning, som climb_vision_agent.py kræver) — fx Giro og Tour 2027,
som blev præsenteret i efteråret 2026. Billederne ligger på
`<pcs_url>/stage-1/info/all-stage-profiles`.

Fremgangsmåde:
  1. Claude vision aflæser PCS-billedet: navngivne stigninger med topkm,
     tophøjde, længde og hældning, og om de bærer et bjergikon (kategoriseret).
  2. Har løbet en officiel ASO-profil i profile_image_anchors.json (Touren),
     aflæses også den, og arrangørens egne tal og navne vinder, hvor de findes.
  3. KONTROL: hver stigning holdes op mod vores egen højdekurve, digitaliseret
     fra arrangørens officielle profil (profile_image_digitizer.py) — en
     uafhængig kilde. Både tophøjden og højdegevinsten over stigningens længde
     skal passe. Består den ikke, skrives den ikke (CLAUDE.md §6).

Mellemsprint skrives KUN, hvis et billede faktisk viser et sprintikon.
Kategorien (HC/1/2...) skrives kun, når den står på billedet; ellers sættes
`kategoriseret=true`, og `category` forbliver NULL.

Licens: vi udtrækker fakta (navn, km, højde) og gemmer aldrig kildebilledet.

Kør:
  python agents/pcs_stage_overview_agent.py --race tour-de-france-2027 [--stage 9] [--write-db] [--overwrite]
"""
from __future__ import annotations

import argparse
import base64
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
from profile_image_digitizer import digitize_stage_profile, load_config  # noqa: E402

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
MODEL = os.getenv("VISION_MODEL", "claude-opus-5")

# Kontrolgrænser mod den digitaliserede officielle kurve. Kurven er tvunget
# gennem arrangørens egne tophøjder, så tophøjden er det skarpeste signal.
TOP_SLOER_M = 70
TOP_VINDUE_KM = 1.5
GEVINST_SLOER_M = 60
GEVINST_SLOER_PCT = 30.0


# ── Det, vision skal svare med ───────────────────────────────────────────────

class Stigning(BaseModel):
    navn: str | None = Field(description="Stigningens navn som trykt, uden km/%-tal. Null hvis intet navn står ved den.")
    top_km: float | None = Field(description="Km-tallet på x-aksen ved den lodrette linje til toppen. For målstigningen: etapens samlede distance.")
    top_hoejde_m: int | None = Field(description="Højden i meter ved toppen, som trykt.")
    laengde_km: float | None = Field(description="Længden i km, fra 'X km - Y%' eller '(X km à Y%)'.")
    gradient: float | None = Field(description="Gennemsnitshældning i procent.")
    bjergikon: bool = Field(description="True hvis stigningen har et bjergikon/badge (kategoriseret bjergspurt).")
    kategori: str | None = Field(description="'HC', '1', '2', '3' eller '4' KUN hvis det står i/ved ikonet. Ellers null.")
    er_maal: bool = Field(description="True hvis stigningen slutter ved målstregen.")


class Sprint(BaseModel):
    navn: str | None
    km: float


class Aflaesning(BaseModel):
    stigninger: list[Stigning]
    sprint: list[Sprint] = Field(description="KUN mellemsprint med et tydeligt sprintikon (fx grønt 'S'). Tom liste hvis ingen.")


PCS_PROMPT = (
    "Dette er en hel-etape-højdeprofil fra ProCyclingStats/La Flamme Rouge.\n"
    "Over profilen står labels ved lodrette linjer: højde, navn og evt. 'X km - Y%'. "
    "Km-tallet for hver linje står nederst på aksen (nogle står i den sorte bjælke under aksen).\n"
    "Målstigningen står øverst til højre ved målflaget som 'X Km - Y%' med et ikon; "
    "dens navn er målbyen/toppen, og top_km er etapens samlede distance.\n\n"
    "Returnér KUN stigninger, dvs. labels der har både en længde og en hældning. "
    "Spring byer, 'start climb', 'end descent' og rene højdepunkter over. "
    "Står en længde/hældning uden navn (fx et stykke af en længere stigning), sæt navn=null.\n"
    "bjergikon=true kun hvis der er et mørkt bjergikon under labelen. Står der 'HC' eller et tal i ikonet, "
    "så er det kategorien.\n"
    "Mellemsprint: kun hvis der er et tydeligt sprintikon. Gæt aldrig — udelad hellere."
)

ASO_PROMPT = (
    "Dette er Tour de France-arrangørens (ASO) officielle etapeprofil.\n"
    "Lodrette tekster ved linjer: 'højde m NAVN', og for kategoriserede stigninger står "
    "'(X km à Y%)' efter navnet og et rødt bjergikon over linjen. Km-tal står i den sorte bjælke.\n"
    "Målet står til højre: hvis det har et rødt bjergikon, er målet en stigning med '(X km à Y%)'.\n\n"
    "Returnér KUN stigninger med '(X km à Y%)'. Navn som trykt (med accenter, normal skrivemåde, ikke VERSALER). "
    "bjergikon=true for alle med rødt bjergikon. Kategori kun hvis et tal/HC står i ikonet.\n"
    "Mellemsprint: kun hvis der er et tydeligt grønt sprintikon. Gæt aldrig."
)

# Giroens officielle profil (RCS, giroditalia.it). PCS kan være helt uden
# labels — Giro 2027 etape 20 havde intet, ikke engang målstigningen Monte
# Zoncolan, som kun står på RCS-billedet ("10.1 km 11.9% → 22%").
GIRO_PROMPT = (
    "Dette er Giro d'Italias officielle etapeprofil (RCS).\n"
    "Lodrette tekster ved linjer: 'højde - NAVN'; bjergspurter (GPM) har et blåt trekant-ikon "
    "ved bunden og navnet med fed skrift. Km-tal står langs bunden.\n"
    "Ved en GPM kan der stå 'X km' og 'Y%' (evt. '→ max%') — det er stigningens længde og "
    "gennemsnitshældning. Målet står til højre (stor ramme); har det et GPM-ikon og 'X km Y%', er "
    "målet en stigning: navn = målets navn, top_km = etapens distance, er_maal=true.\n\n"
    "Returnér KUN stigninger, hvor både længde og hældning står på billedet. "
    "Navn som trykt, men normal skrivemåde (ikke VERSALER). bjergikon=true for GPM. "
    "Kategori kun hvis den står. Mellemsprint kun med tydeligt sprintikon. Gæt aldrig."
)


# ── Hentning ─────────────────────────────────────────────────────────────────

def sb_get(table: str, query: str) -> list[dict]:
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}?{query}", headers=SB_HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def pcs_billeder(pcs_url: str) -> dict[int, str]:
    """{etapenr: billed-URL} fra PCS' samleside over alle etapeprofiler."""
    side = f"{pcs_url.rstrip('/')}/stage-1/info/all-stage-profiles"
    html = requests.get(side, headers={"User-Agent": UA}, timeout=30).text
    ud = {}
    for m in re.finditer(r'(images/profiles/[^"\']+?-stage-(\d+)-profile-[0-9a-f]+\.jpg)', html):
        ud[int(m.group(2))] = "https://www.procyclingstats.com/" + m.group(1)
    return ud


def hent_billede(url: str, referer: str = "https://www.procyclingstats.com/") -> tuple[bytes, str] | None:
    r = requests.get(url, headers={"User-Agent": UA, "Referer": referer}, timeout=30)
    ctype = (r.headers.get("content-type") or "").split(";")[0].strip()
    if not r.ok or not ctype.startswith("image/"):
        return None
    return r.content, ctype


def aflaes(client: anthropic.Anthropic, url: str, prompt: str) -> Aflaesning | None:
    return aflaes_raa(client, url, prompt, Aflaesning)


def aflaes_raa(client: anthropic.Anthropic, url: str, prompt: str, schema,
               referer: str = "https://www.procyclingstats.com/"):
    """Henter et billede og aflæser det med vision ind i `schema` (pydantic)."""
    b = hent_billede(url, referer)
    if not b:
        print(f"    [billede] kunne ikke hentes: {url[:90]}")
        return None
    data, ctype = b
    try:
        svar = client.messages.parse(
            model=MODEL, max_tokens=16000, thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": ctype,
                                             "data": base64.standard_b64encode(data).decode("ascii")}},
                {"type": "text", "text": prompt},
            ]}],
            output_format=schema,
        )
    except anthropic.APIError as e:
        print(f"    [vision-fejl] {type(e).__name__}: {e}")
        return None
    return svar.parsed_output


# ── Kontrol mod den officielle kurve ─────────────────────────────────────────

def _interp(kurve: list[tuple[float, float]], km: float) -> float:
    if km <= kurve[0][0]:
        return kurve[0][1]
    for (k0, h0), (k1, h1) in zip(kurve, kurve[1:]):
        if k0 <= km <= k1:
            return h0 + (h1 - h0) * (km - k0) / max(k1 - k0, 1e-9)
    return kurve[-1][1]


def kontroller(kurve, top_km: float, top_m: int | None, laengde: float, gradient: float) -> tuple[bool, str]:
    vindue = [h for k, h in kurve if abs(k - top_km) <= TOP_VINDUE_KM]
    kurve_top = max(vindue) if vindue else _interp(kurve, top_km)
    if top_m is not None and abs(kurve_top - top_m) > TOP_SLOER_M:
        return False, f"tophøjde {top_m} m, kurven siger {kurve_top:.0f} m"
    forventet = laengde * gradient * 10
    fod = _interp(kurve, top_km - laengde)
    gevinst = kurve_top - fod
    if abs(gevinst - forventet) > max(GEVINST_SLOER_M, forventet * GEVINST_SLOER_PCT / 100):
        return False, f"gevinst {forventet:.0f} m forventet, kurven siger {gevinst:.0f} m"
    return True, f"top {kurve_top:.0f} m, gevinst {gevinst:.0f}/{forventet:.0f} m"


def _ens(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def flet(pcs: list[Stigning], officiel: list[Stigning]) -> list[tuple[Stigning, Stigning | None]]:
    """Parrer PCS' stigninger med arrangørens (samme top inden for 3 km).
    Officielle stigninger uden PCS-modstykke kommer også med som (o, o)."""
    brugt: set[int] = set()
    par = []
    for p in pcs:
        bedst, score = None, 0.0
        for i, o in enumerate(officiel):
            if i in brugt or p.top_km is None or o.top_km is None:
                continue
            if abs(p.top_km - o.top_km) <= 3:
                s = 1.0 + _ens(p.navn, o.navn) - abs(p.top_km - o.top_km) / 10
                if s > score:
                    bedst, score = i, s
        if bedst is not None:
            brugt.add(bedst)
            par.append((p, officiel[bedst]))
        else:
            par.append((p, None))
    for i, o in enumerate(officiel):
        if i not in brugt:
            par.append((o, o))
    return par


# ── Etape ────────────────────────────────────────────────────────────────────

def behandl(client, race: dict, stage: dict, pcs_url: str | None, cfg: dict | None,
            write_db: bool, overwrite: bool, rapport: dict) -> None:
    n = stage["stage_number"]
    dist = float(stage["distance_km"])
    print(f"\n── Etape {n} ({dist} km)")
    r = rapport.setdefault(str(n), {"skrevet": [], "afvist": [], "sprint": []})

    eksisterende = sb_get("stage_climbs", f"stage_id=eq.{stage['id']}&select=id")
    if eksisterende and not overwrite:
        print(f"    har allerede {len(eksisterende)} stigninger — springer over (--overwrite)")
        r["note"] = "havde stigninger"
        return

    kurve, dig = digitize_stage_profile(race["slug"], n, verbose=False)
    if not kurve:
        print(f"    ✗ ingen officiel kurve at kontrollere mod: {dig.get('error')}")
        r["note"] = f"ingen kontrolkurve: {dig.get('error')}"
        return

    pcs = aflaes(client, pcs_url, PCS_PROMPT) if pcs_url else None
    officiel = None
    st_cfg = (cfg or {}).get("stages", {}).get(str(n), {})
    off_prompt = {"aso": ASO_PROMPT, "giro": GIRO_PROMPT}.get((cfg or {}).get("style"))
    if off_prompt and st_cfg.get("source_url"):
        officiel = aflaes(client, st_cfg["source_url"], off_prompt)

    pcs_st = [s for s in (pcs.stigninger if pcs else []) if s.navn and s.laengde_km and s.gradient]
    off_st = [s for s in (officiel.stigninger if officiel else []) if s.navn and s.laengde_km and s.gradient]
    for s in pcs_st + off_st:
        if s.er_maal:
            s.top_km = dist

    raekker = []
    for p, o in flet(pcs_st, off_st):
        kilde = o or p
        navn = kilde.navn.strip()
        laengde, gradient = kilde.laengde_km, kilde.gradient
        top_km = kilde.top_km if kilde.top_km is not None else p.top_km
        top_m = kilde.top_hoejde_m or p.top_hoejde_m
        if top_km is None or laengde <= 0 or laengde > top_km + 0.5:
            r["afvist"].append({"navn": navn, "grund": "mangler/umulig km"})
            continue
        ok, note = kontroller(kurve, top_km, top_m, laengde, gradient)
        kategori = o.kategori if o and o.kategori else p.kategori
        kat_markeret = bool(p.bjergikon or (o and o.bjergikon))
        kildenavn = "aso-etapeprofil" if o is not None else "pcs-etapeprofil"
        mark = f"[KAT {kategori}]" if kategori else "[markeret]" if kat_markeret else ""
        print(f"    {'✓' if ok else '✗'} {navn}: top km {top_km}, {laengde} km à {gradient}% {mark} — {note}")
        if not ok:
            r["afvist"].append({"navn": navn, "top_km": top_km, "grund": note})
            continue
        raekker.append({
            "stage_id": stage["id"],
            "name": navn,
            "km_from_start": round(top_km - laengde, 1),
            "length_km": laengde,
            "avg_gradient": gradient,
            "elevation_m": round(laengde * gradient * 10),   # gevinst, ikke tophøjde
            "top_hoejde_m": top_m,
            "category": kategori if kategori in ("HC", "1", "2", "3", "4") else None,
            "kategoriseret": kat_markeret or bool(kategori),
            "source": kildenavn,
        })
        r["skrevet"].append({"navn": navn, "top_km": top_km, "laengde_km": laengde, "gradient": gradient,
                             "top_m": top_m, "kategori": kategori, "kategoriseret": kat_markeret,
                             "kilde": kildenavn})

    # Målstigning-vagt: slutter etapen på et bjerg (højt mål, kurven stiger ind
    # i mål), skal der være en stigning, der topper ved målstregen. Ellers er
    # den tabt — typisk fordi kilden kun nævner den i etapens navn.
    slut_gevinst = kurve[-1][1] - min(h for k, h in kurve if k >= dist - 8)
    har_maal = any(x["km_from_start"] + x["length_km"] >= dist - 1 for x in raekker)
    if slut_gevinst >= 250 and not har_maal:
        print(f"    ⚠ MÅLSTIGNING MANGLER: kurven stiger {slut_gevinst:.0f} m de sidste 8 km, "
              f"men ingen stigning topper i mål ({stage.get('finish_location')})")
        r["maalstigning_mangler"] = round(slut_gevinst)

    raekker.sort(key=lambda x: x["km_from_start"])
    for i, x in enumerate(raekker, 1):
        x["sort_order"] = i

    # Bevar det, tidligere kørsler har fundet og verificeret (VeloViewer-segment,
    # gradient-tabel, max-hældning), når den nye række er SAMME stigning: samme
    # navn (eller top inden for 1 km) og længden inden for 15 %. Ellers ville
    # --overwrite slette ejer-godkendte VeloViewer-match.
    if eksisterende:
        gamle = sb_get("stage_climbs", f"stage_id=eq.{stage['id']}&select=name,km_from_start,length_km,"
                                       "veloviewer_segment_id,gradient_sections,max_gradient")
        brugt_g = set()
        for x in raekker:
            top = x["km_from_start"] + x["length_km"]
            for j, g in enumerate(gamle):
                if j in brugt_g or not g.get("length_km"):
                    continue
                g_top = g["km_from_start"] + g["length_km"]
                samme = (_ens(g["name"], x["name"]) > 0.8 and abs(g_top - top) <= 3) or abs(g_top - top) <= 1
                if samme and abs(g["length_km"] - x["length_km"]) <= 0.15 * x["length_km"]:
                    brugt_g.add(j)
                    for felt in ("veloviewer_segment_id", "gradient_sections", "max_gradient"):
                        if g.get(felt) is not None:
                            x[felt] = g[felt]
                    break
        tabt = [g["name"] for j, g in enumerate(gamle) if j not in brugt_g and g.get("veloviewer_segment_id")]
        if tabt:
            print(f"    ⚠ VeloViewer-match uden modstykke i ny aflæsning (tabes): {tabt}")
            r["veloviewer_tabt"] = tabt
            if write_db:
                print("    ✗ etapen skrives IKKE — et verificeret match må ikke forsvinde uden review")
                return

    sprint = []
    for kilde in (officiel, pcs):
        if kilde and kilde.sprint:
            sprint = [{"km": s.km, "name": s.navn or ""} for s in kilde.sprint if 0 < s.km < dist]
            break
    r["sprint"] = sprint

    if not write_db:
        print(f"    (tørkørsel) {len(raekker)} stigninger, {len(sprint)} sprint")
        return
    # PostgREST kræver samme nøgler i alle rækker i en bulk-insert — ellers
    # 400 PGRST102. (Det slettede Giro 2027 e5/e14/e16 2026-11-12, fordi de
    # gamle rækker blev slettet FØR den fejlende indsættelse.)
    noegler = set().union(*(x.keys() for x in raekker)) if raekker else set()
    raekker = [{k: x.get(k) for k in noegler} for x in raekker]
    # Indsæt FØRST, slet de gamle bagefter — en fejl må aldrig efterlade en tom etape.
    if raekker:
        res = requests.post(f"{SUPABASE_URL}/rest/v1/stage_climbs", json=raekker,
                            headers={**SB_HEADERS, "Prefer": "return=representation"}, timeout=30)
        if not res.ok:
            print(f"    [DB FEJL] {res.status_code} {res.text[:200]} — de gamle rækker er urørte")
            return
        nye = {x["id"] for x in res.json()}
    else:
        nye = set()
    gamle_ids = [x["id"] for x in eksisterende if x["id"] not in nye]
    if gamle_ids:
        requests.delete(f"{SUPABASE_URL}/rest/v1/stage_climbs?id=in.({','.join(gamle_ids)})",
                        headers=SB_HEADERS, timeout=30).raise_for_status()
    if sprint and not stage.get("sprints"):
        requests.patch(f"{SUPABASE_URL}/rest/v1/stages?id=eq.{stage['id']}", json={"sprints": sprint},
                       headers=SB_HEADERS, timeout=30).raise_for_status()
    print(f"    ✓ skrevet: {len(raekker)} stigninger, {len(sprint)} sprint")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--race", required=True)
    ap.add_argument("--stage", type=int)
    ap.add_argument("--write-db", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()

    race = sb_get("races", f"slug=eq.{a.race}&select=id,slug,pcs_url")[0]
    q = f"race_id=eq.{race['id']}&select=id,stage_number,distance_km,sprints,finish_location&order=stage_number.asc"
    if a.stage:
        q += f"&stage_number=eq.{a.stage}"
    stages = sb_get("stages", q)
    billeder = pcs_billeder(race["pcs_url"]) if race.get("pcs_url") else {}
    print(f"PCS-billeder fundet: {len(billeder)}")
    cfg = load_config(a.race)
    client = anthropic.Anthropic()

    rapport: dict = {"race": a.race, "dato": date.today().isoformat(), "model": MODEL, "etaper": {}}
    for st in stages:
        if not st.get("distance_km"):
            continue
        behandl(client, race, st, billeder.get(st["stage_number"]), cfg,
                a.write_db, a.overwrite, rapport["etaper"])

    ud = REPO_ROOT / "output" / "pcs_stage_overview" / f"{a.race}{'-' + str(a.stage) if a.stage else ''}.json"
    ud.parent.mkdir(parents=True, exist_ok=True)
    ud.write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")
    skrevet = sum(len(v["skrevet"]) for v in rapport["etaper"].values())
    afvist = sum(len(v["afvist"]) for v in rapport["etaper"].values())
    print(f"\nI alt: {skrevet} godkendt, {afvist} afvist. Rapport: {ud}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
