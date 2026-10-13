# Datakilde-research — plan

**Status:** forslag, afventer ejerens go. Skrevet 2026-10-14.
**Issue:** DATA-011 (ny). Beslægtet: DATA-003 (udækkede løb), OPS-010 (automatisering).

Målet er en worker, der **selv opdager, hvilke løb der mangler hvilke data, finder kilderne, verificerer dem og husker både held og uheld** — så et nyt løb kan tilføjes med en linje, og dataene kommer af sig selv.

---

## 1. Hvad vi skal bruge pr. løb

Otte datatyper. De tre første afgør, om en løbsside er tynd eller stærk:

| `data_type` | Hvad | Hvorfor |
|---|---|---|
| `stage_info` | distance, D+, start/mål, dato, starttid | uden den er løbssiden tom |
| `route_gpx` | rutegeometri | kort, højdeprofil, stigningsprofiler, VeloViewer-match |
| `climbs` | stigninger m. kategori, km, længde, gradient | kernen i "hvilket terræn kører de ind i" |
| `startlist` | ryttere | favoritter, danske ryttere |
| `teams` | holdlister | holdsider |
| `results` | resultat + klassement | under og efter løbet |
| `live_text` | skriftlig kommentering | referater |
| `streaming` | hvor det kan ses | TV-tider |

Bemærk `climbs` som egen type: Guangxi viste, at et løb godt kan have stigningsdata uden at have GPX.

---

## 2. Hukommelsen: tabellen `race_data_sources`

Én række pr. **(løb, datatype, kilde)**. Tabellen er både katalog og forsøgslog — det er dét, der gør prioriteringen mulig.

```
race_id          uuid      -> races.id
data_type        text      -- se tabellen ovenfor
status           text      -- 'found' | 'missing' | 'not_applicable'
url              text      -- den konkrete, verificerede URL
source_name      text      -- 'procyclingstats', 'cyclingstage', 'edgecycling', 'organiser', ...
access           text      -- 'open' | 'login' | 'paywall'
is_backup        bool      -- false = primær, true = reservekilde
priority         int       -- rækkefølge når flere findes

verified_at      timestamptz  -- hvornår kilden sidst blev BEVIST at virke
verification     jsonb        -- beviset: fx {"gpx_km": 165.4, "officiel_km": 165.6, "afvigelse_pct": 0.1}

last_attempt_at  timestamptz  -- hvornår vi sidst LEDTE
attempt_count    int
last_failure     text         -- kort, konkret: "intet /route paa officielt site; gpxUrl null i API"
attempted_paths  jsonb        -- hvad der allerede er proevet, saa naeste koersel ikke gentager det

discovered_by    text      -- 'research_agent' | 'manual'
```

**`not_applicable` er lige så vigtig som de to andre.** Et endagsløb har ingen etapeinfo, og et løb uden dansk TV-aftale har ingen streaming. Uden den tilstand bygger der sig en permanent rød liste op, som man holder op med at læse — samme lære som `race_completeness.ikke_muligt`.

---

## 3. Køen og prioriteringen

Præcis som du beskrev, i denne rækkefølge:

1. **Aldrig forsøgt og mangler.** Nye løb ryger øverst automatisk, fordi de ikke har nogen rækker endnu.
2. **Mangler, længst siden sidste forsøg.**
3. **Reservekilder** til det, der allerede har én kilde — kun når 1 og 2 er tomme.

**Spærretid (så den ikke maler løs):**

| Situation | Må forsøges |
|---|---|
| Normalt | 1 gang pr. måned pr. (løb, datatype) |
| Under 30 dage til løbsstart | 1 gang pr. uge |
| Under 7 dage til løbsstart | 1 gang i døgnet |
| Løbet er kørt, og typen er fremadrettet (fx `route_gpx`) | sættes i dvale |

Sidste punkt er værd at tage med: der er ingen grund til at lede efter ruten til et løb, der allerede er kørt.

---

## 4. Standardproceduren — sådan leder den

Seks trin, billigst først. Trin 1-3 koster ingenting og vil klare de fleste løb.

**Trin 1 — spørg de kilder, vi allerede kender.**
Prøv de kendte mønstre, før der søges: PCS-slug, cyclingstages fælles index **og løbets egen underside**, arrangørens site fra `races.source_url`, ASO-sites. Dette er i al væsentlighed `datakilde_scan_agent.py` udvidet fra 2 til 8 datatyper.

> **Il Lombardia-lektien skal ind her:** søg med **løst navnematch** (difflib ≥ 0,72), ikke på vores eget slug. Kilden kaldte løbet `tour-of-lombardy`; vi kalder det `il-lombardia`, og derfor lå en GPX offentligt i 11 dage, uden at vi fandt den.

**Trin 2 — find arrangørens officielle site.**
Fra `races.source_url`, fra PCS' egen link-boks, eller ved navnegæt på domæner. Hent forsiden **råt**.

**Trin 3 — kend sidetypen.**
- *Almindelig HTML:* led efter `/route`, `/stages`, `/startlist`, `/teams`, `/live`, `/tv`.
- *JavaScript-app (umi/Next/React):* forsiden er tom. **Hent i stedet JS-bundlen og find API-værten i den** — præcis sådan blev Guangxi knækket (`cycling.edgecycling.cn` stod i `umi.js`). Kald så API'et og læs felterne.
- *PDF-roadbook:* gem URL'en, markér `found`, og lad et menneske beslutte udtræksmetoden.

**Trin 4 — søg på nettet** (kun hvis 1-3 fejler). `"<løbsnavn> <år> route gpx"`, `"… startlist"`, `"… live"`. Læs de 5 øverste resultater råt.

**Trin 5 — VERIFICÉR, før noget skrives.**
Ingen URL registreres som `found`, før den er hentet og kontrolleret. Pr. type:

| Type | Kontrol |
|---|---|
| `route_gpx` | parse filen, mål dens længde mod officiel distance, tolerance 6 % (samme distancevagt som STG-025) |
| `stage_info` | distance/start/mål findes og stemmer med vores række |
| `startlist` | antal ryttere er plausibelt (60-220) |
| `climbs` | kategori + længde + gradient findes, og gradienttabellen vægter til snithældningen |
| `live_text`/`streaming`/`teams` | siden svarer 200 og nævner løbets navn og år |

**Dette trin er ikke til forhandling.** Et opsummerende værktøj opfandt 2026-07-31 seks plausible cyclingstage-URL'er, der alle gav 404. Kun rå hentning tæller som bevis.

**Trin 6 — skriv resultatet.** Fundet: URL + bevis i `verification`. Ikke fundet: `status='missing'`, `last_attempt_at`, og en **konkret** `last_failure` — "ingen GPX på officielt site, `gpxUrl` null i API" er brugbart; "fejlede" er ikke.

---

## 5. Hvor den kører

**Som et job i den eksisterende motor — ikke en ny service.** `scheduler.py` og `runner.py` kører allerede på Railway og har bevist sig: de hentede Guangxis startliste og etape 1-resultat helt selv 13. oktober, uden at nogen trykkede.

Det betyder nyt `job_key: "datakilde_research"` i `agent_catalog.py`, som arver alt det færdige: kø, Afbryd-knap, log, `run_validator.py`-dommen og pipeline-dashboardet. Schedulering: én kørsel i døgnet, uden for løbstimerne.

En separat service ville betyde endnu en ting, der kan dø stille.

---

## 6. Hvad der koster penge — og hvad der ikke gør

Trin 1-3 og 5-6 er rene HTTP-kald: **gratis**.

Trin 4 er ikke. En Python-worker på Railway kan **ikke** bruge den websøgning, Claude Code har — den findes kun i agent-værktøjet. Skal workeren google, kræver det ét af:

| Mulighed | Pris | Bemærkning |
|---|---|---|
| Drop søgning (kun trin 1-3) | 0 kr. | klarer formentlig 70-80 % af løbene; resten flages til dig |
| Søge-API (Brave/Serper) | ~30-60 kr./md. ved dette volumen | simplest |
| Claude API m. indbygget websøgning | lidt dyrere, men kan også *vurdere* siden | bedst hvis den skal læse SPA-bundles |

**Anbefaling:** byg fase 1-2 uden søgning først. Så kan vi måle, hvor mange løb der reelt strander, før der betales for noget. Budgetloft under alle omstændigheder: maks. N forsøg pr. kørsel.

---

## 7. Den egentlige gevinst: flyt kildekonfigurationen fra kode til tabel

I dag står GPX-kilderne hardkodet i `CYCLINGSTAGE_GPX_PAGES`. Det betyder, at selv når research-agenten *finder* en kilde, kræver det en kodeændring at bruge den — og så er automatikken kun halv.

Fase 4 vender det om: pipelinen slår kilden op i `race_data_sources`. Så bliver et fund umiddelbart brugbart, og et nyt løb kræver ingen kode.

**Men det skal hegnes ind,** for det er netop her, en forkert kilde kan ramme produktionen (CLAUDE.md §7):
- kun rækker med `status='found'` **og** bestået `verification` må bruges automatisk
- GPX bruges kun, hvis distancevagten godkender den — den kontrol gælder stadig **ved brug**, ikke kun ved fund
- alt andet end de verificérbare typer forbliver et **forslag**, du godkender

---

## 8. Faser

| Fase | Indhold | Værdi alene |
|---|---|---|
| 0 | Tabel + backfill af det, vi allerede ved | Dashboard: hvad mangler på tværs af alle løb |
| 1 | Prober uden søgning (trin 1-3, 5-6) | Finder det lavthængende gratis |
| 2 | Kø, spærretid, forsøgslog, Railway-job | Kører selv |
| 3 | Søgning (kræver din beslutning om API) | Tager de svære |
| 4 | Pipelines læser tabellen | Fund bliver til data uden kodeændring |
| 5 | Reservekilder | Robusthed |

Fase 0-2 er den bærende del. 3 og 5 er forbedringer.

---

## 9. Kan det bare køre derudaf?

**Ja for bogholderiet. Delvist for opdagelsen.**

Kø, prioritering, spærretid, forsøgslog og rapportering kan køre uden tilsyn for altid. Du vil altid kunne åbne dashboardet og se præcis, hvad der mangler, hvad der er prøvet, og hvornår.

Selve *findingen* har to grænser, der er værd at kende på forhånd:

1. **En ny platform koster én gang.** Guangxi krævede, at nogen gravede API'et ud af en JS-bundle. Det kan en worker ikke opfinde. Til gengæld amortiseres det — Wanda Sports kører flere løb på samme platform, så arbejdet gælder dem alle. Proceduren i trin 3 er netop skrevet for at gøre næste gang billigere.
2. **At finde en kilde er ikke det samme som at kunne bruge den.** En roadbook-PDF er fundet på fem minutter og udtrukket på fem timer.

Den realistiske forventning: workeren holder **fuldstændigt styr på, hvad der mangler**, henter selv det, der ligger i en kendt form, og giver dig en kort, prioriteret liste over de få løb, der kræver et menneske. Det er efter min vurdering 80 % af værdien, og det er den del, der skalerer, når du tilføjer løb.
