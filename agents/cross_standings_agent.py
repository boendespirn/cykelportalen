"""
cross_standings_agent.py — de officielle samlede stillinger i cykelcross-serierne.

HVORFOR OFFICIELLE OG IKKE VORES EGNE. Vi gemmer kun top 10 pr. loeb
(cross_results_agent.py). En rytter, der blev nr. 12 i ét loeb, har point eller
tid, vi ikke kender, saa et klassement regnet ud af vores egne resultater ville
vaere forkert for alle uden for top 10 — og ofte ogsaa i top 10. Serierne
offentliggoer selv stillingen, saa den hentes dér (ejer-godkendt 2026-11-08,
docs/plan-cross-rutekort-og-stillinger.md).

KILDER (kontrolleret raat 2026-11-08):
  * X2O Trofee — x2otrofee.be/klassement-elite-mannen/: HTML-tabel med plads,
    navn, hold og samlet TID. Serien afgoeres paa tid, ikke point.
  * Superprestige — superprestigecyclocross.be/nl/klassement: top 3 paa siden
    og den fulde stilling som PDF bag "Bekijk" under "Elite Mannen". PDF'en er
    en regnearksudskrift: plads, "Fornavn Efternavn (Bel)", total og point pr.
    afdeling. Delte pladser staar uden nummer.
  * World Cup og HG Cross — ingen kilde endnu.

KONTROLLER, foer noget gemmes (CLAUDE.md §6):
  * Superprestige: antallet af afdelinger med point i PDF'en skal vaere lig
    antallet af kørte Superprestige-loeb i vores kalender. Er stillingen ikke
    opdateret efter seneste loeb, gemmes intet — en foraeldet stilling, der
    staar som aktuel, er vaerre end ingen.
  * X2O: foererens samlede tid divideret med antal kørte loeb skal ligge
    mellem 40 og 90 minutter. Ellers er stillingen enten foraeldet eller
    tolket forkert.
  * Begge: mindst 10 ryttere, og stillingens foerer skal vaere i vores egen
    top 10 i mindst ét af seriens kørte loeb.

Koer:
    py agents/cross_standings_agent.py --alle --dry-run
    py agents/cross_standings_agent.py --race superprestige-niel-2026
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
from datetime import date, datetime, timezone

import requests
from dotenv import load_dotenv
from slugify import slugify

if (getattr(sys.stdout, "encoding", "") or "").lower().replace("-", "") != "utf8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cross_startlist_agent import navne_rotationer  # noqa: E402

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
WRITE = {**AUTH, "Content-Type": "application/json",
         "Prefer": "resolution=merge-duplicates,return=minimal"}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129 Safari/537.36")


def hent(url: str) -> requests.Response:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=45)
    r.raise_for_status()
    return r


def sb_get(table: str, params: str) -> list:
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}?{params}", headers=AUTH, timeout=45)
    r.raise_for_status()
    return r.json()


def saeson(d: date | None = None) -> str:
    """Cross-saesonen gaar hen over nytaar: "2026/27" fra juli til juni —
    samme form som crossSaeson() i frontenden."""
    d = d or date.today()
    fra = d.year if d.month >= 7 else d.year - 1
    return f"{fra}/{str(fra + 1)[2:]}"


def koerte_loeb(kategori: str, s: str) -> list[dict]:
    """Seriens loeb i saesonen, der er kørt (dato foer i dag)."""
    fra = int(s[:4])
    return sb_get("races", f"select=id,slug,start_date&category=eq.{requests.utils.quote(kategori)}"
                           f"&start_date=gte.{fra}-07-01&start_date=lt.{date.today().isoformat()}"
                           f"&start_date=lte.{fra + 1}-06-30&order=start_date")


def i_vores_top10(rider_id: str | None, loeb: list[dict]) -> bool:
    """Er stillingens foerer i vores top 10 i et af seriens kørte loeb?

    X2O har endnu ingen resultatkilde (2026-11-08), saa dér findes ingen
    top 10 at holde stillingen op imod. Saa kraeves det i stedet, at foereren
    stod paa startlisten til et af loebene — svagere, men stadig en kontrol af,
    at kilden og vores kalender handler om de samme loeb."""
    if not rider_id or not loeb:
        return False
    ids = ",".join(r["id"] for r in loeb)
    if sb_get("results", f"select=id&race_id=in.({ids})&limit=1"):
        return bool(sb_get("results", f"select=id&rider_id=eq.{rider_id}&race_id=in.({ids})&limit=1"))
    return bool(sb_get("startlists", f"select=id&rider_id=eq.{rider_id}&race_id=in.({ids})&limit=1"))


_RYTTER_CACHE: dict[str, str | None] = {}


def find_rytter(navn: str) -> str | None:
    """Rytteren i vores database, uanset ordstilling ("NYS Thibau" /
    "Thibau Nys"). Oprettes ALDRIG her: en stilling er ikke en kilde til nye
    rytterprofiler, og navnet gemmes alligevel som tekst."""
    if navn not in _RYTTER_CACHE:
        _RYTTER_CACHE[navn] = None
        for n in navne_rotationer(navn):
            rows = sb_get("riders", f"slug=eq.{slugify(n)}&select=id&limit=1")
            if rows:
                _RYTTER_CACHE[navn] = rows[0]["id"]
                break
    return _RYTTER_CACHE[navn]


# ── X2O Trofee ────────────────────────────────────────────────────────────────

X2O_URL = "https://x2otrofee.be/klassement-elite-mannen/"
TID = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})$")


def _sek(t: str) -> int | None:
    m = TID.match(t.strip())
    if not m:
        return None
    h, mi, se = int(m.group(1) or 0), int(m.group(2)), int(m.group(3))
    return h * 3600 + mi * 60 + se


def x2o() -> tuple[list[dict], str]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(hent(X2O_URL).text, "html.parser")
    tabel = soup.find("table")
    if tabel is None:
        raise ValueError("ingen tabel paa X2O's stillingsside")
    ud = []
    for tr in tabel.find_all("tr"):
        pos = tr.find("td", class_="standing-row-pos")
        info = tr.find("td", class_="standing-row-info")
        celler = tr.find_all("td")
        if not pos or not info or not pos.get_text(strip=True).isdigit():
            continue
        # Navn og hold staar i samme celle som <h5> og <h6>; tiden i sidste celle.
        navn = info.find("h5")
        hold = info.find("h6")
        sek = _sek(celler[-1].get_text(strip=True))
        if not navn or sek is None:
            continue
        ud.append({"position": int(pos.get_text(strip=True)),
                   "rider_name": navn.get_text(strip=True),
                   "team_name": hold.get_text(strip=True) if hold else None,
                   "points": None, "time_seconds": sek})
    return ud, X2O_URL


def kontroller_x2o(raekker: list[dict], antal_loeb: int) -> str | None:
    if antal_loeb == 0:
        return "ingen X2O-loeb kørt endnu i saesonen"
    snit_min = raekker[0]["time_seconds"] / antal_loeb / 60
    if not 40 <= snit_min <= 90:
        return (f"foererens tid svarer til {snit_min:.0f} min pr. loeb over {antal_loeb} loeb "
                "— stillingen er ikke opdateret efter seneste loeb, eller den er tolket forkert")
    return None


# ── Superprestige ─────────────────────────────────────────────────────────────

SP_SIDE = "https://www.superprestigecyclocross.be/nl/klassement"
SP_RAEKKE = re.compile(r"^(?:(\d+)\s+)?([^\d|][^|]*?)(?:\s*\(([A-Za-z]{3})\))?$")


def _sp_pdf_url() -> str:
    t = hent(SP_SIDE).text
    i = t.find("Elite Mannen:")
    if i < 0:
        raise ValueError("'Elite Mannen' staar ikke paa Superprestiges stillingsside")
    m = re.search(r'href="([^"]+/files/[^"]+)"[^>]*>\s*Bekijk', t[i:i + 3000])
    if not m:
        raise ValueError("ingen 'Bekijk'-PDF under Elite Mannen")
    return m.group(1)


def superprestige(antal_loeb: int) -> tuple[list[dict], str]:
    """(raekker, pdf-url).

    Hver raekke er "navn, total, point pr. kørt afdeling" — og pladsnummeret
    for NAESTE rytter staar paa sin egen linje lige efter (1-9) eller foran
    navnet paa samme linje (10+). Delte pladser har intet nummer. Uden at
    vide, hvor mange afdelinger der er kørt, kan en plads ikke skelnes fra et
    pointtal ("29 | 15 | 14 | 2" er Vanthourenhouts 29 = 15 + 14, og 2 er
    Wyseures plads). Derfor laeses der med vores eget antal kørte loeb, og
    summen kontrolleres: er PDF'en ikke opdateret efter seneste loeb, gaar
    summen ikke op, og intet gemmes."""
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    url = _sp_pdf_url()
    with fitz.open(stream=hent(url).content, filetype="pdf") as doc:
        linjer = [x.strip() for side in doc for x in side.get_text().splitlines() if x.strip()]

    raekker: list[dict] = []
    plads = 0
    naeste: int | None = None          # plads, der stod paa linjen foer navnet
    i = 0
    while i < len(linjer):
        m = SP_RAEKKE.match(linjer[i])
        tal: list[int] = []
        j = i + 1
        while j < len(linjer) and re.fullmatch(r"\d+", linjer[j]):
            tal.append(int(linjer[j]))
            j += 1
        if (m and len(tal) >= 1 + antal_loeb
                and not re.search(r"stand|totaal|wedstrijd|naam", linjer[i], re.I)):
            total, pr_loeb, rest = tal[0], tal[1:1 + antal_loeb], tal[1 + antal_loeb:]
            if total == 0:
                break                   # resten er tomme raekker i regnearket
            if sum(pr_loeb) != total:
                raise ValueError(
                    f"{m.group(2).strip()}: total {total} er ikke summen af {pr_loeb} — "
                    f"stillingen er ikke opdateret efter løb nr. {antal_loeb}, eller "
                    "PDF'en er lagt anderledes op")
            if m.group(1):
                plads = int(m.group(1))
            elif naeste is not None:
                plads = naeste
            elif plads == 0:
                plads = 1
            # ellers: delt plads med rytteren foer
            raekker.append({"position": plads, "rider_name": m.group(2).strip(),
                            "team_name": None, "points": total, "time_seconds": None})
            naeste = rest[0] if len(rest) == 1 else None
            i = j
        else:
            if re.fullmatch(r"\d+", linjer[i]) and naeste is None:
                naeste = int(linjer[i])
            i += 1
    return raekker, url


# ── Faelles ──────────────────────────────────────────────────────────────────

SERIER = {
    "X2O Trofee": "x2o",
    "Superprestige": "superprestige",
}


def behandl(kategori: str, toer: bool) -> bool:
    s = saeson()
    loeb = koerte_loeb(kategori, s)
    print(f"\n[{kategori} {s}]  {len(loeb)} loeb kørt")
    if SERIER[kategori] == "x2o":
        raekker, kilde = x2o()
        fejl = kontroller_x2o(raekker, len(loeb)) if raekker else "tom stilling"
    else:
        raekker, kilde = superprestige(len(loeb))
        fejl = None if raekker else "tom stilling"
    if not fejl and len(raekker) < 10:
        fejl = f"kun {len(raekker)} ryttere i stillingen"
    for r in raekker:
        r["rider_id"] = find_rytter(r["rider_name"])
    if not fejl and not i_vores_top10(raekker[0]["rider_id"], loeb):
        fejl = (f"foereren {raekker[0]['rider_name']} findes ikke i vores top 10 i noget "
                "af seriens kørte loeb — kilde og data passer ikke sammen")
    for r in raekker[:5]:
        vaerdi = (f"{r['points']} p" if r["points"] is not None
                  else f"{r['time_seconds'] // 3600}:{r['time_seconds'] % 3600 // 60:02d}:{r['time_seconds'] % 60:02d}")
        print(f"   {r['position']:>3}. {r['rider_name']:<28} {vaerdi}  {'' if r['rider_id'] else '(ukendt rytter)'}")
    kendte = sum(1 for r in raekker if r["rider_id"])
    print(f"   {len(raekker)} ryttere, {kendte} kendt i vores database")
    if fejl:
        print(f"   ✗ gemmer ikke: {fejl}")
        return False
    if toer:
        print("   (toer) intet gemt")
        return True

    nu = datetime.now(timezone.utc).isoformat()
    rows = [{**r, "category": kategori, "season": s, "races_counted": len(loeb),
             "source_url": kilde, "updated_at": nu} for r in raekker]
    res = requests.post(f"{SUPABASE_URL}/rest/v1/series_standings"
                        "?on_conflict=category,season,rider_name",
                        json=rows, headers=WRITE, timeout=60)
    if not res.ok:
        print(f"   [DB-fejl] {res.status_code} {res.text[:200]}")
        return False
    # Ryttere, der er faldet ud af stillingen, maa ikke blive staaende.
    requests.delete(f"{SUPABASE_URL}/rest/v1/series_standings"
                    f"?category=eq.{requests.utils.quote(kategori)}&season=eq.{s}"
                    f"&updated_at=lt.{requests.utils.quote(nu)}", headers=WRITE, timeout=45)
    print(f"   ✓ {len(rows)} raekker gemt")
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--race", help="kun loebets serie (springer andre loeb over)")
    ap.add_argument("--alle", action="store_true")
    ap.add_argument("--dry-run", action="store_true", dest="toer")
    ap.add_argument("--stage", help=argparse.SUPPRESS)       # fra jobbet "resultater"
    ap.add_argument("--all-stages", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if not SUPABASE_URL or not SUPABASE_KEY:
        sys.exit("SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY mangler")

    if args.race:
        rows = sb_get("races", f"slug=eq.{args.race}&select=category,race_type&limit=1")
        kat = rows[0]["category"] if rows else None
        if kat not in SERIER:
            # IKKE en fejl: trinnet staar i det faelles resultat-job.
            print(f"{args.race} hoerer ikke til en serie med officiel stilling — springer over")
            return
        kategorier = [kat]
    elif args.alle:
        kategorier = list(SERIER)
    else:
        ap.error("vaelg --race <slug> eller --alle")

    fejl = 0
    for k in kategorier:
        try:
            behandl(k, args.toer)
        except (requests.RequestException, ValueError) as exc:
            # En kilde, der har lagt sin side om, skal melde sig — ellers ser
            # det ud, som om stillingen bare ikke er opdateret.
            print(f"   [fejl] {type(exc).__name__}: {exc}")
            fejl += 1
    if fejl:
        sys.exit(f"{fejl} serie(r) kunne ikke laeses")


if __name__ == "__main__":
    main()
