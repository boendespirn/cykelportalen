"""
cross_results_agent.py — resultater til cykelcross fra seriernes egne kilder.

HVORFOR EN EGEN AGENT. `results_agent.py` henter fra ProCyclingStats via
etapens PCS-URL. Et cross-loeb har ingen — dets stages.source_url peger paa
cykelkalenderen — saa resultatjobbet koerte trofast hver morgen og fandt
intet (Overijse og Heerde 2026-10-28/29). Serierne udgiver derimod selv
resultatet, og det er den officielle kilde.

KILDER (ejeren pegede paa dem 2026-10-29):

  Superprestige  superprestigecyclocross.be/nl/uitslagen. Siden har ét afsnit
                 pr. loeb (by + dato) med top 3 pr. kategori og et "Bekijk"-
                 link til den fulde resultat-PDF fra tidtageren.
  HG Cross       hgcross.be. Loebets side linker til chronorace
                 ("ListeRapports.aspx?eventId=…"), som viser resultatet paa
                 acn-timing.com. Siden henter sine data fra et aabent JSON-API
                 hos chronorace — samme data, som siden selv viser, uden login.

KONTROL FOER NOGET GEMMES (CLAUDE.md §6 — korrekthed foer hastighed):
  * kildens dato skal vaere loebets dato — ellers er det sidste saesons udgave
  * placeringerne skal vaere 1, 2, 3 … uden huller
  * Superprestige: PDF'ens top 3 skal staa ens paa oversigtssiden
  * HG Cross: kildens egen tidsafstand skal passe med den, vi regner ud
Fejler en kontrol, gemmes intet, og koerslen melder hvorfor.

Vi gemmer top 10 med vinderens tid og de oevriges tidsafstand — samme form som
`results_agent.py` bruger for landevej, saa frontenden viser dem ens.

Koer:
    py agents/cross_results_agent.py --race superprestige-overijse-2026
    py agents/cross_results_agent.py --alle --dry-run
"""
from __future__ import annotations

import argparse
import html
import os
import re
import sys
import unicodedata
from datetime import date, datetime, timezone

import requests
from dotenv import load_dotenv
from slugify import slugify

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cross_startlist_agent import find_eller_opret_rytter, iso2  # noqa: E402

load_dotenv()

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
WRITE = {**AUTH, "Content-Type": "application/json",
         "Prefer": "resolution=merge-duplicates,return=minimal"}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129 Safari/537.36")

TOP = 10

SP_UITSLAGEN = "https://www.superprestigecyclocross.be/nl/uitslagen"
HG_SIDE = "https://hgcross.be"
CHRONO_EVENT = "https://prod.chronorace.be/api/Event/view/{id}"
CHRONO_TRAE = "https://results.chronorace.be/api/results/generic/uci/{ctx}/dh?key=cms"
CHRONO_TABEL = ("https://results.chronorace.be/api/results/table/search/"
                "{ctx}/{key}?srch=&pageSize=200")
ACN_VISNING = ("https://www.acn-timing.com/?lng=EN#/events/{id}/ctx/{ctx}"
               "/generic/{node}/home/{key}")

# Herre-elite hedder noget forskelligt fra kilde til kilde og fra saeson til
# saeson ("Elite Mannen", "Elite Mannen & U23", "Men Elite").
HERRE_ELITE = re.compile(r"elite\s*mannen|men\s*elite|elite\s*men|heren\s*elite", re.I)


def hent(url: str):
    try:
        return requests.get(url, headers={"User-Agent": UA}, timeout=45)
    except requests.RequestException as exc:
        print(f"    [hentefejl] {url[:70]} — {type(exc).__name__}")
        return None


def hent_json(url: str):
    r = hent(url)
    if r is None or not r.ok:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def sb_get(table: str, params: str) -> list:
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}?{params}",
                     headers=AUTH, timeout=45)
    return r.json() if r.ok else []


def bare_tekst(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def navnenoegle(navn: str) -> str:
    """Navnet uden accenter, store bogstaver og ordstilling. Kilderne skriver
    "VANTHOURENHOUT Michael", oversigtssiden "Michael Vanthourenhout" — og
    databasen har begge former (`lejeune-giel` og `giel-lejeune`)."""
    s = unicodedata.normalize("NFKD", navn or "").encode("ascii", "ignore").decode()
    return " ".join(sorted(re.findall(r"[a-z]+", s.lower())))


# ── Superprestige ────────────────────────────────────────────────────────────

def _sp_afsnit(side: str) -> list[dict]:
    """Oversigtssidens loebsafsnit: by, dato og pr. kategori top 3 + PDF-link."""
    ud = []
    for del_ in side.split('accordion--uitslagen-location">')[1:]:
        by = bare_tekst(del_[:del_.find("<")])
        m = re.search(r'accordion--uitslagen-date">\s*(\d{2})/(\d{2})/(\d{2})', del_)
        if not m:
            continue
        dag = date(2000 + int(m.group(3)), int(m.group(2)), int(m.group(1)))
        kategorier = []
        for kat in del_.split("<h3>")[1:]:
            navn = bare_tekst(kat[:kat.find("</h3>")]).rstrip(" :")
            top3 = [re.sub(r"^\d+\.\s*|\s*\([A-Z]{3}\)$", "", bare_tekst(p))
                    for p in re.findall(r"<li[^>]*>\s*<p>(.*?)</p>", kat, re.S)]
            link = re.search(r'href="([^"]+/files/[^"]+)"[^>]*>\s*Bekijk', kat)
            kategorier.append({"navn": navn, "top3": top3,
                               "pdf": link.group(1) if link else None})
        ud.append({"by": by, "dato": dag, "kategorier": kategorier})
    return ud


def _sp_tid(s: str) -> int | None:
    """'1h03?18.0"' → 3798. Tidtageren skriver minuttegnet som et tegn, der
    ikke overlever PDF-udtraekket, saa vi laeser kun cifrene. Kun en tid MED
    timer er en sluttid; '+15.0"' er en afstand og '2 r' en overhalet rytter."""
    m = re.fullmatch(r"(\d+)h(\d{2})\D(\d{2})(?:\.\d)?\"?", s.strip())
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))


def _sp_laes_pdf(pdf: bytes) -> tuple[date | None, list[dict]]:
    """Tidtagerens resultat-PDF. Hver raekke ankres paa UCI-ID'et
    ("100 071 556 51") med UCI-koden ("BEL19931210") lige foer — to former,
    der ikke opstaar tilfaeldigt. Foer dem staar navnet (evt. med
    startnummeret foran) og placeringen; efter dem kategori, klub og tid."""
    import pymupdf as fitz
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        linjer = [x.strip() for side in doc for x in side.get_text().splitlines()
                  if x.strip()]

    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", linjer[0] if linjer else "")
    dag = date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None

    ankre = [k for k in range(2, len(linjer))
             if re.fullmatch(r"\d{3} \d{3} \d{3} \d{2}", linjer[k])
             and re.fullmatch(r"[A-Z]{3}\d{8}", linjer[k - 1])]
    raekker = []
    for n, k in enumerate(ankre):
        mb = re.fullmatch(r"(\d{1,3}) (.+)", linjer[k - 2])
        if mb:
            navn, foer = mb.group(2), k - 3
        else:
            navn, foer = linjer[k - 2], k - 4   # startnummeret paa egen linje
        pos = int(linjer[foer]) if foer >= 0 and linjer[foer].isdigit() else None
        # Naeste raekkes placering + startnummer + navn staar foer dens anker.
        slut = ankre[n + 1] - 2 if n + 1 < len(ankre) else len(linjer)
        efter = linjer[k + 1:slut]
        tid = next((t for t in map(_sp_tid, efter) if t), None)
        status = next((s for s in ("DNF", "DNS", "DSQ") if s in efter), None)
        raekker.append({"pos": None if status else pos, "navn": navn,
                        "nat": linjer[k - 1][:3], "tid": tid, "status": status})
    return dag, raekker


def superprestige(race: dict) -> tuple[list[dict], str] | None:
    side = hent(SP_UITSLAGEN)
    if side is None or not side.ok:
        print("    uitslagen-siden svarede ikke")
        return None
    dag = date.fromisoformat(race["start_date"])
    afsnit = [a for a in _sp_afsnit(side.text) if a["dato"] == dag]
    if not afsnit:
        print("    intet resultat paa uitslagen-siden endnu")
        return None
    kat = next((k for k in afsnit[0]["kategorier"] if HERRE_ELITE.search(k["navn"])), None)
    if not kat or not kat["pdf"]:
        print(f"    {afsnit[0]['by']}: ingen herre-elite-PDF endnu")
        return None

    r = hent(kat["pdf"])
    if r is None or not r.ok or "pdf" not in (r.headers.get("content-type") or ""):
        print(f"    kunne ikke hente {kat['pdf'][:70]}")
        return None
    pdf_dag, raekker = _sp_laes_pdf(r.content)

    if pdf_dag != dag:
        print(f"    [KONTROL] PDF'ens dato {pdf_dag} er ikke loebets {dag} — gemmer intet")
        return None
    pdf_top3 = [navnenoegle(x["navn"]) for x in raekker if x["pos"]][:3]
    side_top3 = [navnenoegle(x) for x in kat["top3"]]
    if pdf_top3 != side_top3:
        print(f"    [KONTROL] PDF'ens top 3 {pdf_top3} passer ikke med siden "
              f"{side_top3} — gemmer intet")
        return None
    print(f"    {afsnit[0]['by']} {kat['navn']}: {len(raekker)} raekker i PDF'en")
    return raekker, kat["pdf"]


# ── HG Cross (chronorace / acn-timing) ───────────────────────────────────────

def _hg_event_ids() -> list[str]:
    """Alle chronorace-event-id'er, som hgcross.be linker til — fra
    resultatsiden og fra hvert loebs egen side, hvor linket kommer foerst."""
    forside = hent(HG_SIDE + "/")
    sider = {HG_SIDE + "/uitslagen/"}
    if forside is not None and forside.ok:
        sider |= set(re.findall(rf'href="({re.escape(HG_SIDE)}/[a-z0-9\-]+/)"',
                                forside.text, re.I))
    ids: list[str] = []
    for s in sorted(sider):
        r = hent(s)
        if r is None or not r.ok:
            continue
        for a, b in re.findall(r"ListeRapports\.aspx\?eventId=(\d+)|#/events/(\d+)/", r.text):
            if (a or b) not in ids:
                ids.append(a or b)
    return ids


def _hg_find_noegle(trae: dict) -> tuple[str, str] | None:
    """(node-id, tabelnoegle) for herre-elite i chronoraces menutrae."""
    def gaa(knude: dict, under_elite: bool):
        elite = under_elite or bool(HERRE_ELITE.search(knude.get("DisplayName") or ""))
        if elite and knude.get("Type") == "result":
            m = re.search(r'"key"\s*:\s*"([^"]+)"', knude.get("Route") or "")
            if m:
                return knude["Id"], m.group(1)
        for barn in knude.get("Childs") or []:
            fund = gaa(barn, elite)
            if fund:
                return fund
        return None
    return gaa(trae, False)


def _hg_tid(s: str) -> int | None:
    m = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{2})", (s or "").strip())
    if not m:
        return None
    return int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3))


def hg_cross(race: dict) -> tuple[list[dict], str] | None:
    dag = race["start_date"]
    for eid in _hg_event_ids():
        ev = hent_json(CHRONO_EVENT.format(id=eid))
        if not ev or str(ev.get("StartDate") or "")[:10] != dag:
            continue
        m = re.search(r"/ctx/([^/]+)", (ev.get("Parameters") or {}).get("Redirect") or "")
        if not m:
            print(f"    chronorace-event {eid} har ingen resultatkontekst endnu")
            return None
        ctx = m.group(1)
        fund = _hg_find_noegle(hent_json(CHRONO_TRAE.format(ctx=ctx)) or {})
        if not fund:
            print(f"    {ev.get('Title')}: ingen herre-elite-resultat endnu")
            return None
        node, key = fund
        tabel = hent_json(CHRONO_TABEL.format(ctx=ctx, key=key)) or {}
        kol = {c["DisplayName"]: c["FieldIdx"]
               for c in (tabel.get("TableDefinition") or {}).get("Columns") or []}
        if not {"Pos", "Name / Team", "#NOC", "Time"} <= kol.keys():
            print(f"    [KONTROL] ukendt tabelopbygning {sorted(kol)} — gemmer intet")
            return None
        raekker = []
        for x in (row for g in tabel.get("Groups") or [] for row in g.get("SlaveRows") or []):
            felt_tid = bare_tekst(x[kol["Time"]])
            pos = re.match(r"(\d+)\.", str(x[kol["Pos"]] or ""))
            navn = re.search(r"<b>(.*?)</b>", x[kol["Name / Team"]] or "")
            nat = re.search(r"flags/([a-z]{3})", x[kol["#NOC"]] or "")
            status = next((s for s in ("DNF", "DNS", "DSQ") if s in felt_tid), None)
            dele = felt_tid.split()
            raekker.append({
                "pos": int(pos.group(1)) if pos and not status else None,
                "navn": bare_tekst(navn.group(1)) if navn else "",
                "nat": nat.group(1).upper() if nat else None,
                # Kun en hel tid er en sluttid; "-4 LAP" er en overhalet rytter.
                "tid": None if "LAP" in felt_tid or status else _hg_tid(dele[0] if dele else ""),
                "kilde_afstand": _hg_tid(dele[1][1:]) if len(dele) > 1
                                 and dele[1].startswith("+") else None,
                "status": status,
            })
        # Kildens egen afstand skal vaere den, vi regner ud af sluttiderne.
        vinder = next((r["tid"] for r in raekker if r["pos"] == 1), None)
        for r in raekker[:TOP]:
            if r["tid"] and vinder and r["kilde_afstand"] is not None \
                    and r["tid"] - vinder != r["kilde_afstand"]:
                print(f"    [KONTROL] {r['navn']}: afstand {r['kilde_afstand']}s i kilden, "
                      f"{r['tid'] - vinder}s regnet ud — gemmer intet")
                return None
        print(f"    {ev.get('Title')}: {len(raekker)} raekker fra chronorace")
        return raekker, ACN_VISNING.format(id=eid, ctx=ctx, node=node, key=key)
    print("    hgcross.be linker endnu ikke til et resultat for denne dato")
    return None


# races.category → (race_data_sources.source_name, henter)
KILDER = {"Superprestige": ("superprestige", superprestige),
          "HG Cross": ("acn-timing", hg_cross)}


# ── Skrivning ────────────────────────────────────────────────────────────────

def find_rytter(r: dict, startfelt: dict, kilde: str, toer: bool) -> str | None:
    """Startlisten foerst: rytteren staar der under det navn, vi allerede har
    koblet. Ellers findes eller oprettes han som i startliste-agenten."""
    rid = startfelt.get(navnenoegle(r["navn"]))
    if rid:
        return rid
    return find_eller_opret_rytter({"navn": r["navn"], "nat": r["nat"], "uci_rank": None},
                                   kilde, toer)


def kontroller(raekker: list[dict]) -> str | None:
    placeret = [r for r in raekker if r["pos"]]
    if len(placeret) < TOP:
        return f"kun {len(placeret)} placerede ryttere"
    if [r["pos"] for r in placeret] != list(range(1, len(placeret) + 1)):
        return "placeringerne er ikke 1, 2, 3 … uden huller"
    if not placeret[0]["tid"]:
        return "vinderen har ingen sluttid"
    return None


def markér_kilde(race: dict, kildenavn: str, url: str, antal: int) -> None:
    """Kataloget skal vide, at resultatet er fundet — ellers staar loebet som
    "mangler resultat" i morgenbeskeden (samme grund som i startliste-agenten).
    Tabellen har ingen unik noegle paa (race_id, data_type), derfor PATCH/POST."""
    nu = datetime.now(timezone.utc).isoformat()
    felter = {"status": "found", "source_name": kildenavn, "url": url,
              "verified_at": nu, "last_attempt_at": nu, "discovered_by": "agent",
              "verification": {"placeringer": antal, "via": "cross_results_agent"}}
    rows = sb_get("race_data_sources",
                  f"race_id=eq.{race['id']}&data_type=eq.results&select=id&limit=1")
    if rows:
        requests.patch(f"{SUPABASE_URL}/rest/v1/race_data_sources?id=eq.{rows[0]['id']}",
                       json=felter, headers=WRITE, timeout=45)
    else:
        requests.post(f"{SUPABASE_URL}/rest/v1/race_data_sources",
                      json={"race_id": race["id"], "data_type": "results", **felter},
                      headers=WRITE, timeout=45)


def behandl(race: dict, toer: bool) -> bool:
    print(f"\n[{race['slug']}]  {race['start_date']}  ({race.get('category')})")
    if date.fromisoformat(race["start_date"]) > date.today():
        print("    ikke koert endnu")
        return False
    kilde = KILDER.get(race.get("category") or "")
    if not kilde:
        print(f"    serien '{race.get('category')}' har ingen kendt resultatkilde")
        return False
    kildenavn, hent_resultat = kilde
    fund = hent_resultat(race)
    if not fund:
        return False
    raekker, url = fund
    fejl = kontroller(raekker)
    if fejl:
        print(f"    [KONTROL] {fejl} — gemmer intet")
        return False

    stage = sb_get("stages", f"race_id=eq.{race['id']}&stage_number=eq.1&select=id&limit=1")
    if not stage:
        print("    loebet har ingen etape 1 at haenge resultatet paa")
        return False
    startfelt = {navnenoegle(s["riders"]["name"]): s["rider_id"] for s in sb_get(
        "startlists", f"race_id=eq.{race['id']}&select=rider_id,riders(name)&limit=500")
        if s.get("riders")}

    top = [r for r in raekker if r["pos"]][:TOP]
    vinder = top[0]["tid"]
    rows = []
    for r in top:
        rid = find_rytter(r, startfelt, url, toer)
        afstand = f"+{r['tid'] - vinder}s" if r["tid"] else "overhalet"
        print(f"      {r['pos']:>2}. {r['navn']:<26} {iso2(r['nat']) or '':<3} {afstand}"
              f"{'' if rid else '  (ny rytter)'}")
        if rid:
            rows.append({"race_id": race["id"], "stage_id": stage[0]["id"],
                         "rider_id": rid, "position": r["pos"],
                         "time_seconds": vinder if r["pos"] == 1 else None,
                         "time_gap_seconds": (r["tid"] - vinder) if r["tid"] else None})
    if toer:
        print(f"    (toer) {len(rows)} af {len(top)} ville blive gemt fra {url[:80]}")
        return True
    if len(rows) != len(top):
        print(f"    [KONTROL] kun {len(rows)} af {len(top)} ryttere kunne kobles — gemmer intet")
        return False
    res = requests.post(f"{SUPABASE_URL}/rest/v1/results?on_conflict=race_id,stage_id,rider_id",
                        json=rows, headers=WRITE, timeout=60)
    if not res.ok:
        print(f"    [DB-fejl] {res.status_code} {res.text[:200]}")
        return False
    markér_kilde(race, kildenavn, url, len(rows))
    print(f"    {len(rows)} placeringer gemt")
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--race", help="vores DB-slug")
    ap.add_argument("--alle", action="store_true", help="alle koerte cross-loeb uden resultat")
    ap.add_argument("--dry-run", action="store_true", dest="toer")
    # Resultatjobbet sender etapeflagene med; et cross-loeb har kun én etape.
    ap.add_argument("--stage", type=int)
    ap.add_argument("--all-stages", action="store_true")
    args = ap.parse_args()
    if not (args.race or args.alle):
        ap.error("vaelg --race <slug> eller --alle")
    if not SUPABASE_URL or not SUPABASE_KEY:
        sys.exit("SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY mangler")

    flt = f"&slug=eq.{args.race}" if args.race else f"&start_date=lte.{date.today()}"
    loeb = sb_get("races", "select=id,slug,name,category,start_date&race_type=eq.cyclocross"
                           f"&order=start_date{flt}")
    if not loeb:
        # IKKE en fejl: trinnet staar i det faelles resultatjob, som ogsaa
        # koerer paa landevejsloeb (samme grund som i cross_startlist_agent).
        print(f"{args.race or 'ingen'} er ikke et cykelcross-loeb — springer over")
        return
    if args.alle:
        har = {x["race_id"] for x in sb_get(
            "results", "select=race_id&race_id=in.(" + ",".join(r["id"] for r in loeb) + ")")}
        loeb = [r for r in loeb if r["id"] not in har]
    print(f"cross_results_agent — {len(loeb)} loeb")
    ok = 0
    for race in loeb:
        try:
            ok += bool(behandl(race, args.toer))
        except Exception as exc:                      # noqa: BLE001
            # Ét loeb maa ikke vaelte hele koerslen.
            print(f"    [fejl] {type(exc).__name__}: {exc}")
    print(f"\nFaerdig: {ok} af {len(loeb)} loeb fik et resultat")


if __name__ == "__main__":
    main()
