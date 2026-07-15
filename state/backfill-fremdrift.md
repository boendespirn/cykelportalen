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

## Bygget og deployet 2026-07-15 (samme dag, opfølgende session)

Punkt 1-4 fra den tidligere "IKKE bygget endnu"-liste er nu færdige,
committet (`2cdad6b`, "feat(SEO-023): byg narrativ-agent + genaabn
historiske etapesider (letvaegt)") og pushet til `master`:

1. **DB-migration:** `stages.historic_recap` (text, nullable) — anvendt via
   `mcp__supabase__apply_migration` (ikke en fil i repoet, kør
   `list_migrations` for at bekræfte hvis i tvivl).
2. **`agents/historic_recap_agent.py`** — bygget og testet på Tour de France
   2025 etape 10 (skriver ægte, original tekst, verificeret i DB). Kilde-
   prioritet: TourTracker (`reports`+`plays` via `tourtracker_id_map.json`)
   når tilgængelig og >= 250 tegn ("full"-tilstand, 3-4 afsnit); ellers vores
   egen DB (top 3-resultat) alene ("short"-tilstand, 1 afsnit); springer helt
   over hvis hverken kilde findes. NB: JSON-parsing har et fallback for en
   ugyldig `\'`-escape, Claude nogle gange sætter om apostroffer i navne
   (fx "O\'Connor") — ren `json.loads` fejler på det, retter og prøver igen.
3. **`race_prep_pipeline.py --historic`:** springer nu trin 6-8 (individuelle
   stigningsprofiler) over og tilføjer trin 10 (`historic_recap_agent.py
   --all-stages`) efter resultater.
4. **Frontend genåbnet:**
   - `[slug]/stage/[n]/page.tsx`: datafuldstændigheds-tjek er
     `stage.elevation_image_url` (sat af `stage_pcs_agent.py`, trin 2) i
     stedet for `stage_climbs` — én simpel, konsistent completeness-signal
     brugt alle steder (se nedenfor). `historic_recap` renderes i en ny
     "Historisk tilbageblik"-sektion. Klassement bruger nu altid
     `getFinalClassification()` (løbets endelige, ikke etape-frosset) for
     historiske sider — titel "Løbets endelige klassement". Lokal-favorit-
     mærkning og individuelle stigningsprofiler er eksplicit deaktiveret for
     historiske sider (`effectiveClimbs = isHistoric ? [] : climbs`).
   - `api.py`: `/races/{slug}/stages/{n}` returnerer nu `historic_recap`.
     `/races` (bulk) returnerer nyt felt `ready_through_stage` (højeste
     SAMMENHÆNGENDE etapenummer fra 1 med `elevation_image_url` sat) —
     bruges af `sitemap.ts` OG af linking-beslutninger på løbs-/rytterside,
     så vi aldrig linker til en historisk side, der reelt stadig er
     skeleton-data (samme fejl som SEO-019 oprindeligt fixede).
   - **Vigtigt fund:** `sitemap.ts` ekskluderede FØR denne session alle løb
     med `end_date` > 30 dage gammelt — dvs. reelt SAMTLIGE historiske løb
     var usynlige for Google via sitemappet, uanset om siderne fandtes.
     Rettet: alle løb er nu med (lavere prioritet/`changeFrequency` for
     historiske), men etape-URL'er for historiske løb er kun med op til
     `ready_through_stage`.
   - Samme linking-gating er også lagt ind i `riders/[slug]/page.tsx`s
     palmares-sektion (etapesejre) — `api.py`s `/riders/{slug}/palmares` og
     `/riders/{slug}/stage-wins` returnerer nu også `elevation_image_url` pr.
     etapesejr til formålet.
   - Verificeret: `npx tsc --noEmit` grønt, lokal `uvicorn`-test af `/races`,
     `/races/tour-de-france-2025/stages/10` (historic_recap til stede) og
     `/riders/pogacar-tadej/palmares` (elevation_image_url til stede).

## Tour de France 2025 — status efter første fulde kørsel (2026-07-15)

Verificeret LIVE på klassementet.dk (WebFetch): `stage/5` viser fuld side
(Historisk tilbageblik + Løbets endelige klassement), `stage/15` giver
korrekt 404 (endnu ikke backfillet) — datafuldstændigheds-gaten virker
som tilsigtet i begge retninger.

- **Resultater + klassement: 21/21 etaper** — var allerede i DB (fandtes
  formentlig fra en tidligere, uafhængig `results_agent.py`-kørsel, ikke
  noget denne sessions pipeline-kørsel skulle skaffe).
- **`historic_recap`: 21/21 etaper** — kørt færdig, inkl. en generaliseret
  rettelse af `historic_recap_agent.py`s JSON-parsing (Claude sætter
  ikke-deterministisk ugyldige backslash-escapes ud over kun `\'`,
  committet `2dcc42e`).
- **`elevation_image_url` (= sidens "er den klar til visning"-signal):
  kun 10/21 etaper.** `stage_pcs_agent.py` rammer PCS' Cloudflare-
  beskyttelse konsekvent — første kørsel (som del af den fulde pipeline)
  stoppede ved etape 13, en umiddelbar gentagelse bagefter stoppede
  allerede ved etape 11 (dvs. VÆRRE, ikke bedre — tyder på at gentagne
  forsøg i hurtig rækkefølge skærper blokeringen i stedet for at
  bygge videre). Scriptet genscraper altid fra etape 1 (ingen
  resume-fra-N-mekanik) — hver kørsel spilder derfor forsøg på allerede
  hentede etaper, før den når de manglende.
- **Konsekvens for resten af 5-års-køen:** denne Cloudflare-mur er
  UAFHÆNGIG af hvilket løb der scrapes — den samme ~10-12-etaper-pr-
  forsøg-grænse vil ramme ethvert løb, ikke kun Tour de France 2025.
  Fuld backfill af alle ~130+ matchede historiske løb vil derfor kræve
  MANGE spredte kørsler over tid (køletid mellem forsøg), ikke én
  sammenhængende session — realistisk et flerdages/-ugers spor, ikke
  timer. Sitemap/intern linking er allerede korrekt gated til kun at
  vise færdige etaper undervejs, så dette er ikke blokerende for at
  fortsætte køen — blot en pacing-realitet at kende.
- **Baseret på**: `state/issues.md` STG-022's "Kendt driftsbegrænsning"
  beskrev allerede dette mønster for `stage_pcs_agent.py` — dette er
  første observation af, at det også rammer historiske løb og at
  gentagne forsøg tilsyneladende forværrer det, ikke kun begrænser det
  til et fast loft.

## Næste skridt (kør i denne rækkefølge)

1. ~~Migrér `stages.historic_recap`~~ — færdig.
2. ~~Byg narrativ-agenten~~ — færdig, testet på Tour de France 2025 etape 10.
3. ~~Opdater `race_prep_pipeline.py`s `--historic`-gren~~ — færdig.
4. ~~Byg frontend-ændringerne~~ — færdig, `tsc` grønt, deployet (pushet til
   `master`, commit `2cdad6b`).
5. **NÆSTE:** kør letvægts-pipelinen for `tour-de-france --year 2025` (fuld
   etape 1-21): `python race_prep_pipeline.py tour-de-france --year 2025
   --historic` fra `agents/`. Bemærk: kun 7 af 21 etaper har
   `elevation_image_url` sat lige nu (`ready_through_stage=7` ved sidste
   tjek) — resten af etapedata/basisprofilbilleder (pipeline-trin 1-2) skal
   køres først, før narrativ-trinnet (10) giver fuld dækning. Verificér
   visuelt/manuelt på klassementet.dk/tour-de-france-2025/stage/N før resten
   af køen sættes i gang.
6. Fortsæt derefter nedad gennem køen (punkt 5 i "Beslutninger truffet")
   — kronologisk baglæns 2025 → 2021, Tour de France → Giro/Vuelta → 5
   Monuments → øvrige WorldTour → resterende étdagsløb.

## Færdige løb (historisk backfill, den faktiske kø)

**2025-sæsonen, `historic_recap` skrevet for (18 løb, verificeret 2026-07-15):**
Tour de France (21/21), Giro d'Italia (21/21), Vuelta a España (21/21),
Critérium du Dauphiné (8/8), Tour de Suisse (8/8), Tour de Romandie (5/5),
Itzulia Basque Country (6/6), Volta Ciclista a Catalunya (7/7),
Tirreno-Adriatico (7/7), Paris-Nice (8/8), Santos Tour Down Under (6/6),
Tour of Guangxi (6/6, DB-only "short"-tilstand — ingen TourTracker-mapping),
Renewi Tour (5/5, DB-only), Tour de Pologne (7/7, DB-only),
UAE Tour (7/7, DB-only), Milano-Sanremo (1/1), Liège-Bastogne-Liège (1/1),
Il Lombardia (1/1). Paris-Roubaix (1/1) — se DATA-002-note nedenfor.

**Elevation_image_url / "siden er klar til visning":** kun Tour de France
har fået opmærksomhed her (10/21, se note ovenfor i filen). De øvrige
2025-løb har typisk 0 billeder endnu — `stage_pcs_agent.py` skal køres
(idempotent, kort kørsel pr. løb pga. Cloudflare) for hvert af dem for at
åbne deres etapesider/synliggøre étdagsløbenes historic_recap.

**Ikke gjort endnu, samme dag:**
- Ronde van Vlaanderen 2025: forkert PCS-slug gættet manuelt
  ("ronde-van-vlaanderen-tour-des-flandres-me"), PCS-siden gav "ingen
  profildata" — ikke undersøgt videre, samme klasse problem som DATA-002.
- Øvrige 2025 WorldTour étdagsløb (E3, Gent-Wevelgem, Amstel Gold Race,
  Flèche Wallonne, Strade Bianche, GP Québec/Montréal m.fl.) — laveste
  2025-prioritet ("resterende étdagsløb" i rækkefølgen), ikke påbegyndt.
- 2024 → 2021 — slet ikke påbegyndt.

**Ny, vigtig lærdom fra denne kørsel — DATA-002 (se `state/issues.md`):**
`stage_pcs_agent.py`s PCS-slug-mapping (`PCS_TO_DB_SLUG` i
`startlist_agent.py`) er bygget til NUVÆRENDE sæson og forudsætter at et
løbs PCS-slug ikke ændrer sig over årene. For løb der har skiftet
officielt navn (fx Paris-Roubaix → "Paris-Roubaix Hauts-de-France")
producerer den en AFVIGENDE db-slug for historiske år end den, løbet
allerede er gemt under — hvilket opretter en tom duplikat-løbsrække i
stedet for at ramme den rigtige. **Ejeren godkendte 2026-07-15 (Telegram)**
at samme fremgangsmåde bruges automatisk resten af køen: før et
etape_pcs_agent-kald, tjek om resultatet landede på en ny/anden slug end
forventet; hvis så, verificér at den nye række er tom (0 resultater/
startlister/klassementer udover den nyoprettede etape), flyt etaperne til
den korrekte eksisterende løbsrække, og slet duplikaten. Se DATA-002 i
`state/issues.md` for den fulde begrundelse.
