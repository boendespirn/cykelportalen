# Automatisering — plan for kørsel uden hænder

Skrevet 2026-10-12. **Intet af dette er bygget endnu** — det er planen, der skal
godkendes, før der røres ved driften.

Målet, med ejerens ord: *alt info og agenter inden, imens og efter et ræs kører
automatisk og online, så det ikke afhænger af, at computeren er tændt.*

---

## 1. Svaret på "Claude Code i Chrome, Cowork, eller som nu?"

**Ingen af de tre.** Begrundelsen er den samme for dem alle: de er
samtaleværktøjer, ikke driftsmotorer.

- **Claude i Chrome** styrer en browser i din egen session. Den kan ikke vågne
  klokken 04:30, fordi en etape i Australien er kørt, og den dør, når browseren
  lukkes. Samme afhængighed af din maskine, som vi forsøger at komme af med.
- **Cowork** er bygget til dokument- og kontorarbejde i et styret miljø, ikke
  til at holde en Chromium-baseret scraper kørende døgnet rundt med vores
  Supabase-nøgler.
- **Som nu** betyder `runner.py` på din PC. Det er netop dét, der gav 2026's
  huller: Vueltas sidste fire etaper har intet resultat, fordi ingen trykkede
  efter sidste etape.

**Anbefalingen er en fjerde:** flyt den runner, vi allerede har, op i skyen ved
siden af API'et, og giv den en skemalægger. Claude Code bliver dér, hvor den
hører hjemme — til at bygge og fejlsøge, ikke til at være driften.

## 2. Det meste findes allerede

Det er vigtigt for omfanget: **køen er online i forvejen.**

| Del | Hvor | Status |
|---|---|---|
| Jobkatalog (hvilke trin hører til hvilket job) | `agent_catalog.py` | ✅ findes |
| Kø | Supabase-tabellen `agent_runs` (`queued → running → done/failed`) | ✅ findes |
| Start/afbryd + log | `api.py` på Railway + `/admin/pipelines` på Vercel | ✅ findes |
| Udførsel | `runner.py` | ⚠️ kører **på din PC** |
| Skemalægning | — | ❌ findes ikke; du er skemalæggeren |

Der mangler altså **to** ting: en skemalægger, der lægger jobs i køen af sig
selv, og en worker, der tager dem online.

## 3. Del A — skemalæggeren

Et nyt script, `scheduler.py`, der kører hvert 5. minut, ser på kalenderen i
databasen og lægger de jobs i kø, som er forfaldne. Den **udfører** intet selv —
den skriver kun rækker i `agent_runs`, præcis som admin-knappen gør i dag. Det
bevarer runnerens sikkerhedsmodel: kun kendte `job_key`s, aldrig en kommando
udefra.

### Reglerne

| Udløser | Job | Hvorfor netop dér |
|---|---|---|
| 7 dage før start | `fuld_forberedelse` | Rute, stigninger og profiler er klar i god tid — og der er en uge til at opdage, at en kilde mangler |
| 48 t før | `startliste` | PCS har sjældent hele feltet tidligere |
| 24 t før | `tv_tider` + `raesinfo` | TV-tider offentliggøres sent, og ruten kan nå at blive ændret |
| 6 t før | `startliste` | Sene afbud |
| Ved start | `startliste` | Endelige startnumre; samtidig en sidste kontrol af, at løbet overhovedet er i gang |
| Forventet mål + 1 t | `resultater` | Resultat og klassement |
| Derefter hver 30. min | `resultater` | Indtil etapen HAR et resultat — så stopper reglen af sig selv |
| 3 t efter sidste etape | `raesreferat` | Når alle etapereferater er skrevet |
| Dagligt kl. 06 | `nyheder_rss`, `nyheder_ai`, `daglig_pipeline` | Som i dag |
| Ugentligt, mandag | `datakilde_scan` | Fanger en kilde, der er rådnet, før den koster et løb |

For etapeløb gælder de seks første regler **pr. etape** (undtagen
`fuld_forberedelse`, som er pr. løb).

### Hvornår er "forventet mål"?

Vi har ikke starttidspunktet for de fleste etaper — kun 17 af 115 i 2026. Derfor
gætter skemalæggeren ikke:

1. Har etapen en TV-sending, bruges dens **sluttid** (TV slutter ved målstregen).
2. Ellers: starttid + distance ÷ 40 km/t, hvis starttiden findes.
3. Ellers: **poll billigt** — forsøg hver 30. minut fra kl. 12 til 22 lokal tid
   på løbsdagen. Et forsøg er én sideindlæsning, og reglen stopper i samme
   sekund, resultatet står i databasen.

Punkt 3 er med vilje primitiv. Alternativet — at gætte et måltidspunkt — ville
gøre præcis det, der kostede os Vueltas sidste etaper: ét forkert gæt, og ingen
opdager det.

### Så en regel ikke kan løbe løbsk

- **Idempotens:** en regel må kun lægge ét job i kø pr. (job, løb, etape,
  regel, dag). Skemalæggeren tjekker `agent_runs`, før den skriver.
- **Loft:** højst 20 resultat-forsøg pr. etape. Rammes loftet, skrives et issue
  i stedet for at blive ved.
- **Ét job ad gangen:** uændret — runneren tager kun ét, fordi to Playwright-
  kørsler samtidig løb tør for hukommelse under Vuelta-backfillen.
- **Tørkørsel:** `scheduler.py --dry-run --dage 14` printer, hvad den ville
  lægge i kø, uden at skrive noget. Det er sådan, vi godkender reglerne, før de
  tændes.

## 4. Del B — workeren online

| Mulighed | For | Imod | Dom |
|---|---|---|---|
| **Railway-worker** (ny service i samme projekt som API'et) | Env-variabler findes allerede; altid tændt; samme repo; Chromium via Playwrights eget image | ~5-10 USD/md | **Anbefalet** |
| GitHub Actions (cron) | Billigt | Mindst 5 min granularitet i praksis, Playwright skal installeres ved hver kørsel, nøgler skal dubleres | Som **vagthund**, ikke som motor |
| Fortsat PC | Ingen ændring | Afhænger af, at maskinen er tændt | Afvist — det er problemet, vi fjerner |

**Konkret:** en ny Railway-service på samme repo med startkommandoen
`python runner.py`, bygget på `mcr.microsoft.com/playwright/python:v1.59.0`, så
Chromium følger med. Skemalæggeren kan køre i samme service som en baggrundstråd
— ét sted at holde øje med.

**Vagthund:** en GitHub Action hver time, der spørger API'et: "har workeren
sendt livstegn inden for 15 minutter, og står der jobs i kø, som er mere end en
time gamle?" Hvis nej, en besked. Uden den opdager vi først en død worker, når
et løb mangler sit resultat.

## 5. Når noget går galt

Tre lag, fra billigst til dyrest:

1. **Loggen** står allerede i `/admin/pipelines` pr. kørsel.
2. **Besked ved fejl:** en Telegram-besked fra workeren, når et job fejler, eller
   når resultat-reglen rammer sit loft.
3. **Dagligt sammendrag** kl. 07: hvad kørte i går, hvad fejlede, hvad mangler
   stadig data. Det er dét, der ville have fanget Vuelta-hullet samme dag.

## 6. Eksekvering — fire faser

| Fase | Indhold | Tid | Færdig når |
|---|---|---|---|
| **1** | `scheduler.py` med `--dry-run`. Ingen skrivning, ingen deploy. | ½ dag | Du har set listen over, hvad den ville køre de næste 14 dage, og godkendt reglerne |
| **2** | Railway-worker: Dockerfile, ny service, ét manuelt job kørt igennem derfra | ½ dag | Et job startet fra admin kører i skyen med PC'en slukket |
| **3** | Tænd skemalæggeren for **ét** løb — Tour of Guangxi (13.-18. oktober) er den oplagte prøve, den starter i morgen | ½ dag | Guangxis seks etaper får resultat, uden at nogen trykker |
| **4** | Hele kalenderen + vagthund + daglig besked | 1 dag | En uge uden manuelle indgreb, og ingen huller |

Derefter, som forberedelse til 2027: **slug-verifikation før sæsonstart** (den
kontrol, der 2026-10-12 fandt fire forældede PCS-slugs) og import af
2027-kalenderen, så skemalæggeren har noget at regne på.

## 7. Det, planen ikke løser

- **Referat for endagsløb** mangler stadig en kilde (RES-008). Automatisering
  gør ikke en kilde til, der ikke findes.
- **Kilder, vi ikke råder over,** kan lukke igen, som Strava gjorde (STG-033).
  Derfor vagthunden og det ugentlige kildescan.
- **De dyre trin** (vision-aflæsning af stigninger, referater via Anthropic API)
  kører stadig kun én gang pr. løb. Automatiseringen må ikke gøre dem til en
  løbende udgift — derfor er de bundet til `fuld_forberedelse` 7 dage før og
  ikke til nogen gentagende regel.
