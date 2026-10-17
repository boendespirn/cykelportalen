"""
scheduler.py
Lægger pipeline-jobs i kø, når løbskalenderen siger, at de er forfaldne.

Hvorfor (OPS-010): indtil 2026-10-13 var ejeren selv skemalæggeren. Det kostede
data præcis dér, hvor opmærksomheden slap — Vueltas sidste fire etaper stod uden
resultat i en måned, og syv WorldTour-etapeløb havde slet ingen data, fordi
ingen trykkede på knappen.

Hvad den IKKE gør:
  Den udfører intet. Den skriver kun rækker i `agent_runs` med status 'queued',
  nøjagtig som knappen i /admin/pipelines gør — og `runner.py` henter dem. Det
  bevarer runnerens sikkerhedsmodel: kun kendte `job_key`s fra agent_catalog,
  aldrig en kommando udefra. Ejeren kan se og afbryde hver eneste kørsel i
  dashboardet som hidtil.

Reglerne (ejerens, 2026-10-12):
  7 dage før     fuld_forberedelse   (pr. løb)
  48 timer før   startliste          (pr. løb)
  24 timer før   tv_tider + raesinfo (pr. løb)
  6 timer før    startliste          (pr. løb)
  ved start      startliste          (pr. løb)
  mål + 1 time   resultater          (pr. etape)
  hver ½ time    resultater          (pr. etape, indtil etapen HAR et resultat)
  slut + 3 timer raesreferat         (pr. løb)

Kør:
  python scheduler.py --dage 14      vis planen for de næste 14 dage
  python scheduler.py --dry-run      vis hvad der er forfaldent lige nu
  python scheduler.py                læg det forfaldne i kø, og stop
  python scheduler.py --loop         bliv kørende, tjek hvert 5. minut
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

import requests
from dotenv import load_dotenv

import notify

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
SKRIV = {**AUTH, "Content-Type": "application/json", "Prefer": "return=representation"}

TJEK_INTERVAL = 300          # sekunder mellem tjek i --loop
RESULTAT_TAETTE = 3           # forsøg hver time lige efter forventet mål
RESULTAT_BACKOFF_TIMER = 3    # derefter: ét forsøg hver tredje time
RESULTAT_BACKOFF_FORSOEG = 4  # hvor mange af de langsomme forsøg
RESULTAT_MAKS = 12            # loft, så en etape uden resultat ikke poller evigt
SWEEP_FRA = 5                # UTC-time, hvor timevis-fejningen begynder
SWEEP_TIL = 21               # UTC-time, hvor den slutter


# ── Tid ───────────────────────────────────────────────────────────────────────

def _eu_sommertid(d: date) -> bool:
    """EU's regel: sommertid fra sidste søndag i marts til sidste søndag i oktober.

    Beregnet frem for slået op, så scheduleren ikke afhænger af, at `tzdata` er
    installeret i det image, den kører i.
    """
    def sidste_soendag(aar: int, maaned: int) -> date:
        naeste = date(aar, maaned + 1, 1) if maaned < 12 else date(aar + 1, 1, 1)
        d2 = naeste - timedelta(days=1)
        return d2 - timedelta(days=(d2.weekday() + 1) % 7)
    return sidste_soendag(d.year, 3) <= d < sidste_soendag(d.year, 10)


def lokal_til_utc(d: date, time_: int, minut: int = 0) -> datetime:
    """Dansk lokaltid → UTC. Løbene køres i Europa; de oversøiske rammer
    fallback-vinduet, som er bredt nok til at dække dem."""
    offset = 2 if _eu_sommertid(d) else 1
    return datetime(d.year, d.month, d.day, time_, minut, tzinfo=timezone.utc) - timedelta(hours=offset)


def nu() -> datetime:
    return datetime.now(timezone.utc)


# ── Database ──────────────────────────────────────────────────────────────────

def hent(sti: str) -> list:
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{sti}", headers=AUTH, timeout=60)
    r.raise_for_status()
    return r.json()


def _url_tid(t: datetime) -> str:
    """Tidsstempel klar til en URL.

    `isoformat()` slutter på '+00:00', og PLUS betyder MELLEMRUM i en
    query-streng — tidsstemplet nåede derfor PostgREST som ugyldigt, og hele
    opslaget svarede 400. Fejlen var usynlig lokalt, hvor køen var tom, og
    dukkede først op i workerens log.
    """
    return quote(t.isoformat(), safe="")


def koeede_jobs(fra: datetime, til: datetime) -> list[dict]:
    """Jobs, skemalæggeren selv har lagt i kø i perioden — grundlaget for, at
    den samme regel ikke kan lægge det samme job i kø to gange.

    `trigger` er en CHECK-begrænset kolonne ('button', 'cli', 'schedule'), så
    reglens navn kan ikke stå dér. Det ligger i `args.regel` i stedet.
    """
    return hent(f"agent_runs?select=job_key,race_slug,stage_number,args,status,queued_at"
                f"&queued_at=gte.{_url_tid(fra)}&queued_at=lte.{_url_tid(til)}"
                f"&trigger=eq.schedule&order=queued_at.desc&limit=1000")


def laeg_i_koe(job_key: str, race_slug: str | None, stage_number: int | None,
               regel: str, tør: bool) -> bool:
    if tør:
        return True
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/agent_runs",
        json={"job_key": job_key, "race_slug": race_slug, "stage_number": stage_number,
              "status": "queued", "trigger": "schedule", "args": {"regel": regel}},
        headers=SKRIV, timeout=30,
    )
    if not r.ok:
        print(f"  [FEJL] kunne ikke lægge {job_key} i kø: {r.status_code} {r.text[:160]}")
        return False
    return True


# ── Regler ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Udloeser:
    """Ét planlagt jobtidspunkt."""
    tidspunkt: datetime
    job_key: str
    race_slug: str
    stage_number: int | None
    regel: str

    def noegle(self) -> tuple:
        return (self.job_key, self.race_slug, self.stage_number, self.regel)


# Forberedelsen koeres FLERE gange, ikke én. Et loeb faar sine data drypvis:
# arrangoeren lægger ruten ud uger foer, stigningerne kommer naar ruten er
# kendt, og startlisten faa dage foer. Koerte vi kun én gang syv dage foer,
# fik vi det, der tilfaeldigvis laa klar netop dén dag — Veneto Classic havde
# baade GPX-kilde og stigningskilde registreret som "found", men hverken rute
# eller stigninger hentet, da loebet var et doegn vaek (2026-10-17).
#
# Kadencen er ejerens (2026-10-17) og foelger, hvor hurtigt data aendrer sig:
# sjaeldent langt ude, dagligt den sidste uge.
FOER_LOEB = [
    (timedelta(days=30),  "fuld_forberedelse", "30d"),
    (timedelta(days=14),  "fuld_forberedelse", "14d"),
    # Dagligt den sidste uge.
    *[(timedelta(days=d), "fuld_forberedelse", f"{d}d") for d in range(7, 0, -1)],
    (timedelta(hours=48), "startliste",        "48t"),
    (timedelta(hours=24), "tv_tider",          "24t-tv"),
    (timedelta(hours=24), "raesinfo",          "24t-rute"),
    (timedelta(hours=6),  "fuld_forberedelse", "6t-prep"),
    (timedelta(hours=6),  "startliste",        "6t"),
    (timedelta(0),        "startliste",        "start"),
]


# Job uden løb: de kører på klokkeslæt, ikke på kalenderen. Tidspunktet er i
# UTC og lagt uden for løbstimerne, så de aldrig konkurrerer med resultathentning
# om runneren (den tager ét job ad gangen).
DAGLIGE_GLOBALE = [
    (3, "datakilde_research", "dagligt-0300"),
    # tv_agent scraper HELE sendeplanen i én kørsel og kan ikke begrænses til
    # ét løb. Derfor hører den også hjemme her, ikke kun 24 timer før hvert
    # løb: kanalerne offentliggør 2-3 uger frem, og med kun "24t-tv"-reglen
    # stod et løb med en kendt sendetid alligevel som "sendeplanen er ikke
    # offentliggjort endnu" indtil dagen før. Det rammer cross hårdest — 24
    # løb fra oktober til december, hvor sendetiden er dét, brugeren kommer
    # efter. Reglen "24t-tv" beholdes som sikkerhedsnet tæt på løbet.
    (4, "tv_tider", "dagligt-0400"),
]


def forventet_maal(stage: dict, tv: list[dict]) -> datetime | None:
    """Hvornår etapen ventes at være i mål — eller None, hvis vi ikke ved det.

    Vi GÆTTER ikke et tidspunkt ud af ingenting: et forkert gæt er netop det,
    der kostede Vuelta sine sidste etaper. Uden holdepunkt falder kalderen
    tilbage på et bredt pollevindue, som stopper i samme sekund, resultatet
    står i databasen.
    """
    d = date.fromisoformat(stage["date"])

    for s in tv:
        if s.get("broadcast_date") == stage["date"] and s.get("end_time"):
            t = s["end_time"]
            return lokal_til_utc(d, int(t[:2]), int(t[3:5]))

    if stage.get("stage_start_time") and stage.get("distance_km"):
        t = stage["stage_start_time"]
        start = lokal_til_utc(d, int(t[:2]), int(t[3:5]))
        return start + timedelta(hours=float(stage["distance_km"]) / 40.0)

    return None


def resultat_tidspunkter(stage: dict, tv: list[dict]) -> list[datetime]:
    """Hvornår vi forsøger at hente etapens resultat.

    To lag, fordi vi ikke kender løbets tidszone: `races.country_code` er tom
    på 20 af 2026-sæsonens 36 løb — heriblandt Guangxi, Tour Down Under og UAE
    Tour, altså præcis dem, der IKKE kører i dansk tid.

      1. Kender vi det forventede måltidspunkt (TV-sluttid eller starttid +
         distance), slår vi til tæt: mål + 1 time og derefter hver halve time
         seks gange. Det dækker den normale etape.
      2. Derudover et TIMEVIS fejesvingning hen over hele døgnet i UTC
         (05-21). Det koster én sideindlæsning i timen og kan — modsat et gæt
         på tidszonen — ikke ramme ved siden af, uanset om etapen slutter i
         Adelaide eller i Nice.

    Begge lag stopper af sig selv: `planlaeg()` springer etaper over, der
    allerede HAR et resultat, så så snart det står i databasen, planlægges der
    ikke flere forsøg.
    """
    d = date.fromisoformat(stage["date"])
    tider: list[datetime] = []

    maal = forventet_maal(stage, tv)
    if maal:
        # Ejerens kadence (2026-10-17): én gang i timen, og efter tre forgaeves
        # forsoeg hver tredje time. Et resultat, der ikke er kommet efter tre
        # timer, kommer sjaeldent i det fjerde kvarter — men det kan komme
        # timer senere, naar arrangoeren er langsom. Tidligere stod der hvert
        # halve minut i seks forsoeg plus en timevis fejning, og Tour of
        # Guangxi fik derfor op mod 20 forsoeg i doegnet.
        start = maal + timedelta(hours=1)
        tider += [start + i * timedelta(hours=1) for i in range(RESULTAT_TAETTE)]
        tider += [start + timedelta(hours=RESULTAT_TAETTE)
                  + i * timedelta(hours=RESULTAT_BACKOFF_TIMER)
                  for i in range(RESULTAT_BACKOFF_FORSOEG)]

    # Fejningen er sikkerhedsnettet for de loeb, hvor vi ikke kender
    # maaltidspunktet — 20 af saesonens 36 har tom country_code. Den er nu
    # hver tredje time i stedet for hver time: den skal fange et resultat, vi
    # ellers ville overse, ikke vaere den primaere kilde.
    tider += [datetime(d.year, d.month, d.day, t, tzinfo=timezone.utc)
              for t in range(SWEEP_FRA, SWEEP_TIL + 1, RESULTAT_BACKOFF_TIMER)]
    # Etaper slutter sent nok til, at resultatet kan komme efter midnat UTC
    tider += [datetime(d.year, d.month, d.day, 23, tzinfo=timezone.utc) + timedelta(hours=i)
              for i in (1, 3)]

    return sorted(set(tider))[:RESULTAT_MAKS]


def planlaeg(fra: datetime, til: datetime) -> list[Udloeser]:
    """Alle udløsere i vinduet [fra, til] — beregnet ud fra kalenderen."""
    loeb = hent(f"races?select=id,slug,name,race_type,start_date,end_date"
                f"&end_date=gte.{(fra - timedelta(days=30)).date()}"
                f"&start_date=lte.{(til + timedelta(days=30)).date()}"
                f"&order=start_date&limit=500")
    ud: list[Udloeser] = []

    # Løbsløse job først — de hænger ikke på nogen kalenderpost.
    dag = fra.date()
    while dag <= til.date():
        for time_utc, job, regel in DAGLIGE_GLOBALE:
            t = datetime(dag.year, dag.month, dag.day, time_utc,
                         tzinfo=timezone.utc)
            if fra <= t <= til:
                ud.append(Udloeser(t, job, "", None, regel))
        dag += timedelta(days=1)

    for r in loeb:
        slug = r["slug"]
        start = date.fromisoformat(r["start_date"])
        # Løbet begynder kl. 10 lokal tid, når vi ikke ved bedre. Det er kun
        # ankeret for FØR-reglerne; resultatreglerne bruger etapens eget
        # måltidspunkt.
        start_tid = lokal_til_utc(start, 10)

        for delta, job, regel in FOER_LOEB:
            t = start_tid - delta
            if fra <= t <= til:
                ud.append(Udloeser(t, job, slug, None, regel))

        stages = hent(f"stages?race_id=eq.{r['id']}&select=id,stage_number,date,distance_km,"
                      f"stage_start_time,data_status&order=stage_number&limit=50")
        tv = hent(f"broadcast_schedule?race_id=eq.{r['id']}"
                  f"&select=stage_number,broadcast_date,end_time&limit=200")
        resultater = {x["stage_id"] for x in
                      hent(f"results?race_id=eq.{r['id']}&select=stage_id&limit=1000")}

        for st in stages:
            if not st.get("date"):
                continue            # en etape uden dato kan ikke skemalægges
            if st.get("data_status") in ("cancelled", "no_result"):
                # En aflyst etape får aldrig et resultat — og det gør en
                # HOLDENKELTSTART heller ikke: PCS' aktive fane er en
                # holdrangliste uden rytterkolonne, og `results` er
                # rytterbaseret (Paris-Nice og Dauphiné E3 2026). Uden dette
                # ville skemalæggeren jage et resultat, der ikke findes, 20
                # gange om dagen og melde etapen som manglende for evigt.
                continue
            if st["id"] in resultater:
                continue            # resultatet står der allerede
            for i, t in enumerate(resultat_tidspunkter(st, tv)):
                if fra <= t <= til:
                    ud.append(Udloeser(t, "resultater", slug, st["stage_number"],
                                       f"resultat+{i}"))

        if r.get("end_date") and (r.get("race_type") or "") == "stage_race":
            slut = lokal_til_utc(date.fromisoformat(r["end_date"]), 20)
            if fra <= slut <= til:
                ud.append(Udloeser(slut, "raesreferat", slug, None, "referat"))

    return sorted(ud, key=lambda u: u.tidspunkt)


# ── Kørsel ────────────────────────────────────────────────────────────────────

def koer_en_gang(tør: bool) -> int:
    """Lægger de udløsere i kø, der er forfaldne lige nu."""
    tid = nu()
    # Et vindue bagud, så et job ikke går tabt, hvis skemalæggeren var nede, da
    # tidspunktet passerede.
    udloesere = planlaeg(tid - timedelta(hours=2), tid)
    allerede = {(k["job_key"], k["race_slug"], k["stage_number"],
                 (k.get("args") or {}).get("regel"))
                for k in koeede_jobs(tid - timedelta(days=2), tid)}

    lagt = 0
    for u in udloesere:
        if u.noegle() in allerede:
            continue
        etape = f" E{u.stage_number}" if u.stage_number else ""
        print(f"  {'[tør] ' if tør else ''}{u.job_key:18} {u.race_slug}{etape}  ({u.regel})")
        if laeg_i_koe(u.job_key, u.race_slug, u.stage_number, u.regel, tør):
            lagt += 1
    if not lagt:
        print("  intet forfaldent")
    return lagt


DIGEST_TIME_UTC = 6          # kl. 07/08 dansk tid
_sidste_digest: date | None = None


KILDE_LABEL = {"startlist": "startliste", "results": "resultater",
               "streaming": "tv"}

# Beskeden er en HANDLELISTE til ejeren, ikke en statusrapport. Derfor kun de
# to typer, han faktisk kan skaffe i hånden: startliste og tv.
#
# `results` er bevidst UDE for kommende løb — et løb, der ikke er kørt endnu,
# mangler selvfølgelig sit resultat, og den linje ville stå der hver eneste
# morgen uden at nogen kunne gøre noget. Den tages kun med, når løbet ER kørt
# og resultatet alligevel ikke er fundet; dét er et reelt hul.
#
# `stage_info` er også ude: den fyldes af pipelinen selv og kræver ingen
# menneskelig kilde.
KILDETYPER_ALTID = ("startlist", "streaming")

# Herfra finder ejeren kilden i hånden. Siden dækker alle cross-løb og linker
# direkte videre til arrangørens startliste.
CROSS_OPSLAG = "https://cyclocross24.com/dk/calendar/"


def manglende_kilder(dage: int = 7) -> list[str]:
    """Løb inden for `dage`, hvor vi stadig mangler en kilde.

    Hvorfor en egen sektion: cykelcross kan agenterne ikke selv skaffe kilder
    til. PCS opretter først sin side få dage før løbet, arrangørerne varierer
    fra serie til serie, og cyclocross24 — som har dem alle og linker direkte
    videre til startlisterne — ligger bag en bot-spærre, vi ikke omgår
    (docs/cross-datakilder-plan.md). Beskeden lader derfor ejeren gøre præcis
    dét, en agent ikke må: slå løbet op i hånden og sende kilden videre.
    """
    i_dag = nu().date()
    til = i_dag + timedelta(days=dage)
    # Vinduet gaar BEGGE veje: fremad for de loeb, vi skal naa at skaffe
    # startliste og tv til, og en uge tilbage for koerte loeb, hvis resultat
    # aldrig blev fundet.
    fra = i_dag - timedelta(days=dage)
    loeb = hent("races?select=id,slug,name,start_date,end_date,race_type,category"
                f"&start_date=gte.{fra.isoformat()}"
                f"&start_date=lte.{til.isoformat()}&order=start_date&limit=200")

    linjer: list[str] = []
    for r in loeb:
        slut = r.get("end_date") or r.get("start_date")
        er_koert = bool(slut and slut < i_dag.isoformat())
        # Et koert loeb skal ikke staa paa listen for sin startliste eller
        # sendetid — de er uden betydning bagefter.
        relevante = ("results",) if er_koert else KILDETYPER_ALTID

        huller = sorted({x["data_type"] for x in
                         hent(f"race_data_sources?race_id=eq.{r['id']}"
                              f"&status=eq.missing&select=data_type&limit=20")
                         if x["data_type"] in relevante})
        if not huller:
            continue
        maerke = "🚲" if r.get("race_type") == "cyclocross" else "•"
        navne = ", ".join(KILDE_LABEL.get(h, h) for h in huller)
        linjer.append(f"  {maerke} {r['start_date']} {r['name']}\n      mangler: {navne}")
    return linjer


def dagligt_sammendrag(tving: bool = False) -> None:
    """Én besked om morgenen: hvad kørte i går, hvad fejlede, hvad mangler.

    Det er dét, der ville have fanget Vuelta-hullet samme dag i stedet for en
    måned senere. Fejlede kørsler melder sig selv med det samme (runner.py);
    sammendraget fanger den anden slags — dét, der ALDRIG kørte.
    """
    global _sidste_digest
    i_dag = nu().date()
    if not tving and (_sidste_digest == i_dag or nu().hour != DIGEST_TIME_UTC):
        return
    _sidste_digest = i_dag

    # Vinduet er I GÅR — ikke "fra i går og frem". Den første udgave talte
    # også nattens kørsler med og meldte dem som gårsdagens: ejeren fik
    # 2026-10-13 besked om en fejlet startliste, der i virkeligheden var en
    # prøvekørsel samme nat, afbrudt af et deploy.
    i_gaar = i_dag - timedelta(days=1)
    koersler = hent(f"agent_runs?select=job_key,race_slug,status,exit_code"
                    f"&queued_at=gte.{i_gaar.isoformat()}&queued_at=lt.{i_dag.isoformat()}"
                    f"&limit=500")
    fejlede = [k for k in koersler if k.get("status") == "failed"]

    # Kørte etaper uden resultat — det hul, ingen opdager af sig selv.
    mangler: list[str] = []
    for r in hent(f"races?select=id,slug&end_date=gte.{(i_dag - timedelta(days=4)).isoformat()}"
                  f"&start_date=lte.{i_dag.isoformat()}&limit=50"):
        med_resultat = {x["stage_id"] for x in
                        hent(f"results?race_id=eq.{r['id']}&select=stage_id&limit=1000")}
        for st in hent(f"stages?race_id=eq.{r['id']}&select=id,stage_number,date,data_status"
                       f"&date=lte.{i_gaar.isoformat()}&order=stage_number&limit=50"):
            if st.get("data_status") in ("cancelled", "no_result") or st["id"] in med_resultat:
                continue
            mangler.append(f"{r['slug']} E{st['stage_number']} ({st['date']})")

    linjer = [f"📋 Klassementet — {i_dag.isoformat()}",
              f"{len(koersler)} kørsler i går, {len(fejlede)} fejlede"]
    if fejlede:
        linjer += [f"  ❌ {k['job_key']} · {k.get('race_slug') or '—'}" for k in fejlede[:8]]
    if mangler:
        linjer.append(f"Mangler resultat ({len(mangler)}):")
        linjer += [f"  • {m}" for m in mangler[:8]]

    # Kilder, vi ikke selv kan skaffe. Står til sidst, fordi det er en
    # OPGAVE til ejeren, ikke en fejlmelding — og den skal kunne læses som
    # en huskeliste, der kan afsluttes.
    kilder = manglende_kilder(7)
    if kilder:
        linjer.append(f"\n🔎 Mangler kilder (næste 7 dage, {len(kilder)} løb):")
        linjer += kilder[:10]
        if len(kilder) > 10:
            linjer.append(f"  … og {len(kilder) - 10} til")
        linjer.append(f"Find dem her: {CROSS_OPSLAG}")

    if not fejlede and not mangler and not kilder:
        linjer.append("Ingen fejl, ingen huller.")
    notify.send("\n".join(linjer))


def vis_plan(dage: int) -> None:
    tid = nu()
    udloesere = planlaeg(tid, tid + timedelta(days=dage))
    print(f"scheduler.py — planlagte kørsler de næste {dage} dage "
          f"({len(udloesere)} i alt, tider i UTC)\n")
    dag = None
    for u in udloesere:
        d = u.tidspunkt.date()
        if d != dag:
            print(f"\n{d:%Y-%m-%d}")
            dag = d
        etape = f" E{u.stage_number}" if u.stage_number else ""
        print(f"  {u.tidspunkt:%H:%M}  {u.job_key:18} {u.race_slug}{etape}  ({u.regel})")
    if not udloesere:
        print("  ingen — der er ingen løb i perioden")


if __name__ == "__main__":
    # line_buffering: uden den samles udskriften i en buffer, når stdout er en
    # pipe (som i containeren), og skemalæggeren ser død ud i Railways log,
    # selv om den kører fint. runner.py flusher hver linje af samme grund.
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)

    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", dest="tør", action="store_true",
                   help="skriv ikke i køen — vis kun, hvad der ville ske")
    p.add_argument("--dage", type=int, default=0,
                   help="vis planen for de næste N dage i stedet for at køre")
    p.add_argument("--loop", action="store_true",
                   help="bliv kørende og tjek hvert 5. minut")
    p.add_argument("--sammendrag", action="store_true",
                   help="send morgenbeskeden NU (til test); --dry-run skriver "
                        "den kun i terminalen")
    args = p.parse_args()

    if args.sammendrag:
        # Nulstil daglaasen, saa beskeden kan sendes paa forlangende.
        _sidste_digest = None
        if args.tør:
            kilder = manglende_kilder(7)
            print(f"Manglende kilder, naeste 7 dage ({len(kilder)} loeb):")
            print("\n".join(kilder) if kilder else "  ingen")
        else:
            dagligt_sammendrag(tving=True)
    elif args.dage:
        vis_plan(args.dage)
    elif args.loop:
        print(f"scheduler.py kører — tjekker hvert {TJEK_INTERVAL // 60}. minut. Ctrl+C for at stoppe.")
        while True:
            print(f"\n[{nu():%Y-%m-%d %H:%M} UTC]")
            try:
                koer_en_gang(args.tør)
                dagligt_sammendrag()
            except Exception as e:
                print(f"  [FEJL] {type(e).__name__}: {e}")
            time.sleep(TJEK_INTERVAL)
    else:
        koer_en_gang(args.tør)
