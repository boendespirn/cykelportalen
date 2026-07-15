# Historisk landingsside-backfill — fremdrift (SEO-022 / SEO-023)

Kørsels-pointer for `SEO-022`/`SEO-023` (`state/issues.md`). Læs denne fil
FØRST i enhver ny session om dette emne — den er den ene sandhedskilde for,
hvad der er besluttet, bygget, og hvad der mangler. Opdateres efter hvert
væsentligt skridt, så en frisk session (ny klon, ingen hukommelse) kan
fortsætte uden at genopdage noget af det, der allerede er afklaret.

**Hvis ejeren siger noget i retning af "gå i gang med at få kød på
landingssiderne / hent data om historiske etaper"** — det er præcis dette
spor. Følg checklisten under "Næste skridt" nedenfor, i rækkefølge.

---

## Beslutninger truffet (læs disse — spørg IKKE ejeren om dem igen)

1. **Mål:** alle løb i indeværende sæson (2026) skal have fuld dybde
   (stigningsprofiler mm., allerede eksisterende 9-trins `race_prep_pipeline.py`).
   Historiske løb (år < 2026) skal have en **lettere overbliksstruktur uden
   individuelle stigningsprofiler** — det var den reelle flaskehals. Fuld
   begrundelse: `docs/superpowers/plans/2026-07-15-historiske-landingssider-5-aar.md`
   (§ "REVIDERET 2026-07-15").
2. **Historisk sidestruktur** (hvad der SKAL og IKKE skal med) er fuldt
   specificeret i `docs/superpowers/specs/2026-07-15-historiske-etapesider-letvaegt.md`.
   Kort: hel-etape højdeprofil (ikke pr.-stigning), rute, fuld startliste,
   favoritter **uden** lokal-mærkning, danske ryttere, top 10-etaperesultat,
   løbets **endelige** klassement (ikke etape-for-etape-akkumuleret), og en ny
   AI-genereret historisk fortælling.
3. **Kilde til den historiske fortælling: TourTracker** (`live.tourtrackerprocycling.com`,
   ejerens forslag, testet og godkendt 2026-07-15). Se samme spec-dokument for
   fuld teknisk gennemgang. Kort: `secure.tourtrackerdata.com/tours/{TOUR_ID}/jsonp/reports/stageNreports.jsonp`
   (kort redaktionel recap) + `.../plays/stageNplays.jsonp` (rig blow-by-blow-
   kommentering). **Brug som faktuel funderingskilde — republicér ALDRIG teksten
   ordret** (copyright, `CLAUDE.md` §7). AI'en skriver egen, original tekst.
4. **"Kendt/nyhedsværdig etape"-kriterium:** skriv kun en fuld fortælling, når
   kilden (`reports`/`plays`) reelt har noget at fortælle (ægte drama/angreb/tæt
   afgørelse); ellers en kort, ærlig faktuel opsummering. Ingen forudbestemt
   liste over "vigtige" etaper.
5. **Rækkefølge for backfill:** kronologisk baglæns — 2025 → 2024 → 2023 →
   2022 → 2021. Inden for hvert år: Tour de France → Giro d'Italia/Vuelta a
   España → de 5 Monuments → øvrige WorldTour-etapeløb → resterende étdagsløb.
   (2026 er et separat, løbende spor med fuld dybde — ikke en del af denne kø.)

---

## Allerede bygget og verificeret (genbrug — byg ikke om)

- **`agents/tourtracker_id_map.json`** — færdig mapping `races.slug` →
  TourTracker tour-ID. 133 af 212 DB-løb matchet, inkl. alle 5 prioritets-
  niveauer i planen. Genbyg med `python agents/build_tourtracker_id_map.py`,
  hvis `races`-tabellen vokser.
- **Pipeline-scripts er årgang-parameteriserede:** `startlist_agent.py` og
  `stage_pcs_agent.py` tager `--year YYYY`. `results_agent.py` har
  `--all-stages` (henter alle etapers resultater, ikke kun seneste).
- **STG-022 rettet:** `stage_pcs_agent.py`s `save_stages()` batch-upsert
  fejlede stille ved heterogene nøglesæt — rettet til at splitte i homogene
  sub-batches. Verificeret mod rigtig 2025-data.
- **STG-023 rettet:** `gpx_climb_agent.py` tilføjet som pipeline-trin, der
  reelt opretter `stage_climbs`-rækker (tidligere manglede dette skridt helt).
  **Bemærk:** dette trin er kun relevant for **indeværende sæson (Fase 1)**
  efter revisionen — historiske sider (Fase 2-3) springer det bevidst over.
- **Kendt driftsbegrænsning:** PCS' Cloudflare-beskyttelse stopper
  `stage_pcs_agent.py` efter ca. 10-12 sekventielle etapesider. En fuld grand
  tour kræver typisk 2 kørsler (scriptet er idempotent — ufarligt at genkøre).

---

## IKKE bygget endnu — dette er den faktiske næste opgave

`race_prep_pipeline.py` kører stadig altid alle 9 trin (inkl. stignings-
oprettelse) uanset `--historic`. Der findes **endnu ingen** letvægts-pipeline
og **ingen** narrativ-generator. Konkret mangler:

1. **DB-migration:** nyt felt `stages.historic_recap` (text, nullable) —
   adskilt fra det eksisterende `description` (anden tone/formål, se spec).
2. **Ny narrativ-agent** (fx `agents/historic_recap_agent.py`): for en given
   `--race SLUG --stage N`, slå `db_slug` op i `tourtracker_id_map.json`,
   hent `reports`/`plays` for den etape, og generér original, varieret,
   kommentator-sprog-tekst efter kriteriet i punkt 4 ovenfor. Skriv til
   `stages.historic_recap`.
3. **Letvægts-pipeline-flow for historiske løb:** `race_prep_pipeline.py`s
   `--historic`-gren skal opdateres til at **springe stignings-trinnene (6-8)
   over** (de blev tilføjet til STG-023 for indeværende sæson, men gælder ikke
   historisk efter revisionen) og tilføje det nye narrativ-trin i stedet.
4. **Frontend:** `cykel-frontend/app/[slug]/stage/[n]/page.tsx` og
   `lib/historic-stage.ts` skal ændres fra en blank årstals-404 til reel
   sidevisning for historiske løb med komplet data — jf. Fase 3 i plan-
   dokumentet: datafuldstændigheds-tjek (ikke `stage_climbs`), fjern lokal-
   favorit-logik for historiske sider, vis løbets endelige klassement (ikke
   `getEffectiveClassification()`s etape-frosne forsøg), render
   `historic_recap`, geninsæt intern linking, `sitemap.ts`.

## Næste skridt (kør i denne rækkefølge)

1. Migrér `stages.historic_recap` (nyt nullable text-felt).
2. Byg narrativ-agenten (punkt 2 ovenfor) — test på Tour de France 2025 etape
   10 (samme etape STG-023 allerede verificerede har komplet stage-data).
3. Opdater `race_prep_pipeline.py`s `--historic`-gren (punkt 3).
4. Byg frontend-ændringerne (punkt 4) — test lokalt før deploy.
5. Kør letvægts-pipelinen for `tour-de-france --year 2025` (fuld etape 1-21),
   genåbn siderne for det løb først, verificér visuelt/manuelt før resten af
   køen sættes i gang.
6. Fortsæt derefter nedad gennem køen (punkt 5 i "Beslutninger truffet").

## Færdige løb (historisk backfill, den faktiske kø)

*(ingen endnu — punkt 1-5 ovenfor skal bygges først)*
