# Historisk landingsside-backfill — fremdrift (SEO-022)

Detaljeret kørsels-pointer for `SEO-022` (`state/issues.md`) og planen i
`docs/superpowers/plans/2026-07-15-historiske-landingssider-5-aar.md`.
Opdateres efter hvert pipeline-trin/løb, så en frisk session (eller en session
der løber tør for kontekst) kan fortsætte præcis der, hvor den forrige slap.

**Rækkefølge:** kronologisk baglæns — 2026 (løbende, separat spor, se `STRATEGI.md` §1
Fase 1) → 2025 → 2024 → 2023 → 2022 → 2021. Inden for hvert år: Tour de France →
Giro d'Italia/Vuelta a España → de 5 Monuments (Milano-Sanremo, Ronde van Vlaanderen,
Paris-Roubaix, Liège-Bastogne-Liège, Il Lombardia) → øvrige WorldTour-etapeløb →
resterende étdagsløb.

**Kørselskommando pr. løb** (fra `agents/`):
`python race_prep_pipeline.py PCS-SLUG --year YYYY`
(8 trin; `--historic` sættes automatisk når `YYYY` < indeværende sæson — springer
rytterbilleder over, kører resultater med `--all-stages`)

**PCS-slug ≠ DB-slug:** brug PCS' eget slug (fx `tour-de-france`, `vuelta-a-espana`,
`milan-san-remo`) — pipelinen slår selv DB-sluggen op via `PCS_TO_DB_SLUG` i
`startlist_agent.py`.

---

## Status lige nu (2026-07-15, sat på pause pga. to fund nedenfor)

**Fase:** 0 — testkørsel af `race_prep_pipeline.py tour-de-france --year 2025`
afslørede to reelle, blokerende huller i pipelinen selv (ikke i årgang-ændringerne).
Begge skal rettes, før nogen skala-kørsel giver mening — ellers gentages
SEO-019-fejlen (tynde/tomme sider), bare med et helt tomt DB-write oveni.

### Fund 1 — stage_pcs_agent.py's batch-upsert taber al data stille, ~PGRST102

`save_stages()`'s Supabase-upsert af en hel etape-liste på én gang fejler med
`"All object keys must match"` (PostgREST kræver ens nøglesæt på tværs af alle
objekter i én batch-POST), fordi nogle etaper har `elevation_image_url` med
(PCS fandt billede) og andre ikke (bevidst udeladt jf. `ARKITEKTUR.md`s note om at
undgå at nulstille et eksisterende billede — se linje 41). Når batchen er
heterogen, fejler **hele** batchen — konsollen viste "OK" pr. etape (scraping
lykkedes), men databasen fik intet. Verificeret direkte: `tour-de-france-2025`
har 21 etape-rækker, men `distance_km`/`elevation_image_url` er NULL på alle 21
efter kørslen. **Rammer formentlig også indeværende sæsons løbende opdateringer**,
ikke kun historisk backfill — værd at undersøge om dette har ramt 2026-data
også et sted (STG-002/STG-015-mønsteret nævner allerede lignende symptomer).
**Fix:** split upsert i to homogene sub-batches (med/uden `elevation_image_url`)
i stedet for én blandet batch, eller upsert enkeltvis.

### Fund 2 — race_prep_pipeline.py opretter aldrig stage_climbs-rækker

Pipelinens trin 6 (`climbfinder_agent.py`) og 7 (`climb_profile_generator.py`)
**tilføjer kun billeder til allerede eksisterende `stage_climbs`-rækker** — de
opretter dem ikke. De faktiske opret-trin (`gpx_climb_agent.py` og/eller
`profile_reader_agent.py`, jf. `ARKITEKTUR.md`s fulde stignings-pipeline,
trin 2-3) indgår slet ikke i `race_prep_pipeline.py`s 8 trin. Verificeret:
climbfinder_agent-kørslen for tour-de-france-2025 fandt "21 etaper" at tjekke,
men 0 stigninger at opdatere — fordi der reelt ikke findes nogen `stage_climbs`-
rækker for løbet overhovedet (bekræftet: 0 rækker i DB). Dette forklarer
sandsynligvis hele det oprindelige 0-stigninger-mønster for 2021-2025, som
`docs/superpowers/plans/2026-07-15-historiske-landingssider-5-aar.md` byggede
på. **Fix:** tilføj `gpx_climb_agent.py --race SLUG --all` (og/eller
`profile_reader_agent.py`) som nyt trin i `race_prep_pipeline.py` FØR
climbfinder/GPX-fallback-trinnene.

### Andre observationer fra testkørslen (ikke blokerende, men noteret)

- **Cloudflare-challenge stoppede etape-scraping ved etape 13/21** — PCS'
  bot-beskyttelse reagerede efter ~12 sekventielle sidehentninger. Skal
  håndteres (længere delays mellem etaper, evt. retry-med-backoff) før skala.
  Betyder også: selv når batch-bugget er rettet, kan én kørsel ikke
  nødvendigvis nå alle 21 etaper uden en pause/retry-mekanisme.
  Historisk data ændrer sig aldrig, så en gentaget kørsel næste dag/session
  for at samle resten op er ufarlig, bare langsommere end håbet.
- **Kørslen tog >10 min og blev dræbt af mit eget værktøjs timeout** — en fuld
  8-trins-kørsel for et grand tour (21 etaper × flere scraping-trin) tager
  reelt længere end 10 minutter. Fremtidige kørsler skal enten køre med et
  længere timeout, eller opdeles i selvstændige trin/etaper der hver især er
  hurtigere end det.
- 4 ryttere (Thomas, Démare, Woods, Sepúlveda) matchede ikke i `riders`-tabellen
  (findes formentlig ikke i DB, da de ikke er på nogen 2026-startliste) —
  lav volumen (4/188), ikke blokerende, men betyder rytterlink på historiske
  startlister vil mangle for enkelte navne, indtil de oprettes.

## Næste skridt (afventer ejerens prioritering — se spørgsmål i sessionen)

1. Ret Fund 1 (homogen batch-upsert i `stage_pcs_agent.py`).
2. Tilføj det manglende klatre-opret-trin til `race_prep_pipeline.py` (Fund 2).
3. Gentest `tour-de-france --year 2025` fra bunden, verificér denne gang at
   `distance_km`, `elevation_image_url` OG `stage_climbs`-rækker reelt lander
   i DB, ikke kun konsol-"OK".
4. Fortsæt derefter nedad gennem køen som planlagt.

## Færdige løb

*(ingen endnu — begge fund ovenfor skal rettes først)*

## Kendte blokeringer / afventer ejer

- Fund 1 og 2 ovenfor — kræver kodeændringer, ikke kun kørsel, før backfillen
  reelt producerer brugbare sider.
