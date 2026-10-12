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

import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
SKRIV = {**AUTH, "Content-Type": "application/json", "Prefer": "return=representation"}

TJEK_INTERVAL = 300          # sekunder mellem tjek i --loop
RESULTAT_INTERVAL = 30 * 60  # nyt resultatforsøg hvert halve time
RESULTAT_MAKS = 20           # loft, så en etape uden resultat ikke poller evigt
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


def koeede_jobs(fra: datetime, til: datetime) -> list[dict]:
    """Jobs, skemalæggeren selv har lagt i kø i perioden — grundlaget for, at
    den samme regel ikke kan lægge det samme job i kø to gange."""
    return hent(f"agent_runs?select=job_key,race_slug,stage_number,trigger,status,queued_at"
                f"&queued_at=gte.{fra.isoformat()}&queued_at=lte.{til.isoformat()}"
                f"&trigger=like.skema:*&order=queued_at.desc&limit=1000")


def laeg_i_koe(job_key: str, race_slug: str | None, stage_number: int | None,
               regel: str, tør: bool) -> bool:
    if tør:
        return True
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/agent_runs",
        json={"job_key": job_key, "race_slug": race_slug, "stage_number": stage_number,
              "status": "queued", "trigger": f"skema:{regel}"},
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


FOER_LOEB = [
    (timedelta(days=7),   "fuld_forberedelse", "7d"),
    (timedelta(hours=48), "startliste",        "48t"),
    (timedelta(hours=24), "tv_tider",          "24t-tv"),
    (timedelta(hours=24), "raesinfo",          "24t-rute"),
    (timedelta(hours=6),  "startliste",        "6t"),
    (timedelta(0),        "startliste",        "start"),
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
        tider += [maal + timedelta(hours=1) + i * timedelta(seconds=RESULTAT_INTERVAL)
                  for i in range(6)]

    tider += [datetime(d.year, d.month, d.day, t, tzinfo=timezone.utc)
              for t in range(SWEEP_FRA, SWEEP_TIL + 1)]
    # Etaper slutter sent nok til, at resultatet kan komme efter midnat UTC
    tider += [datetime(d.year, d.month, d.day, 23, tzinfo=timezone.utc) + timedelta(hours=i)
              for i in range(1, 4)]

    return sorted(set(tider))[:RESULTAT_MAKS]


def planlaeg(fra: datetime, til: datetime) -> list[Udloeser]:
    """Alle udløsere i vinduet [fra, til] — beregnet ud fra kalenderen."""
    loeb = hent(f"races?select=id,slug,name,race_type,start_date,end_date"
                f"&end_date=gte.{(fra - timedelta(days=30)).date()}"
                f"&start_date=lte.{(til + timedelta(days=30)).date()}"
                f"&order=start_date&limit=500")
    ud: list[Udloeser] = []

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
            if st.get("data_status") == "cancelled":
                continue            # aflyst etape får aldrig et resultat
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
                 (k["trigger"] or "").removeprefix("skema:"))
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
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", dest="tør", action="store_true",
                   help="skriv ikke i køen — vis kun, hvad der ville ske")
    p.add_argument("--dage", type=int, default=0,
                   help="vis planen for de næste N dage i stedet for at køre")
    p.add_argument("--loop", action="store_true",
                   help="bliv kørende og tjek hvert 5. minut")
    args = p.parse_args()

    if args.dage:
        vis_plan(args.dage)
    elif args.loop:
        print(f"scheduler.py kører — tjekker hvert {TJEK_INTERVAL // 60}. minut. Ctrl+C for at stoppe.")
        while True:
            print(f"\n[{nu():%Y-%m-%d %H:%M} UTC]")
            try:
                koer_en_gang(args.tør)
            except Exception as e:
                print(f"  [FEJL] {type(e).__name__}: {e}")
            time.sleep(TJEK_INTERVAL)
    else:
        koer_en_gang(args.tør)
