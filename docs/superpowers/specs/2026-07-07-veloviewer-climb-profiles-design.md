# VeloViewer-baseret stigningsprofil (ny prioritet 1) — design

Dato: 2026-07-07
Status: Godkendt af ejer (arkitekturvalg afklaret via spørgsmål + juridisk research), klar til implementeringsplan.

## Baggrund og problem

`STRATEGI.md` peger selv på at "Climbfinder: mange bugs i at finde og vise de rigtige stigningsprofiler" er et af sidens kendte problemer. `climbfinder_agent.py` er i dag prioritet 1 for stigningsbilleder, med `climb_profile_generator.py` (egen GPX-genereret grafik) som fast fallback (jf. `ARKITEKTUR.md` §"Stignings-/profil-pipeline").

VeloViewer.com tilbyder markedets bedste visuelle 3D-profiler af stigninger, bygget direkte på Stravas segment-data. Målet er at gøre VeloViewers profil til den **nye prioritet 1** — før ClimbFinder — når vi kan finde og verificere det rigtige Strava/VeloViewer-segment for en given stigning.

## Juridisk grundlag (verificeret under design)

Dette er ikke en biting-detalje her — hele arkitekturen er formet af, hvad der reelt er tilladt:

- **VeloViewers [T&C for 3D-profiler](https://blog.veloviewer.com/terms-and-conditions-of-use-of-interactive-and-static-image-3d-profiles/):** Embedding via deres eget embed-script er **gratis for alle sites, inkl. kommercielle**, og er den metode de selv foretrækker. Bekræftet embed-format (fra live segmentside, Alpe d'Huez):
  ```html
  <iframe style="width:100%;height:450px;" src="https://veloviewer.com/segments/{ID}/embed" frameborder="0" scrolling="no"></iframe>
  ```
  Standardvalg (intet kort, 3D, km) kræver ingen query-parametre — ren URL med segment-ID er nok. Statiske billeder/print/video kræver forudgående tilladelse — **ikke valgt her**, se "Fravalgt tilgang" nedenfor.
- **[Strava API Agreement](https://www.strava.com/legal/api):** Strava strammede i 2024/2026-opdateringen reglerne markant: *"Strava Data provided by a specific user can only be displayed or disclosed in your Developer Application to that user. Strava Data related to other users, even if such data is publicly viewable on the Strava Platform, may not be displayed or disclosed."* Det betyder: **intet vi henter via Strava API'et (segmentnavn, distance, hældning, højdemeter) må nogensinde vises på klassementet.dk** — hverken i frontend eller admin.
- **Konsekvens for arkitekturen:** Strava API'et bruges **udelukkende server-side til intern verifikation** (match/ikke-match). Den offentlige visning sker **udelukkende via VeloViewers egen iframe-embed**, som opererer under VeloViewers eget forhold til Strava — vi viser aldrig Strava-data direkte selv. Kun det bare numeriske segment-ID (nødvendigt for embed-URL'en) persisteres i vores DB; ingen navne/distancer/hældninger fra Strava-svaret må skrives til DB, logs synlige for andre, eller frontend.
- **"Powered by Strava"-branding:** opfyldes allerede af VeloViewers embed selv — intet ekstra krævet af os.

## Fravalgt tilgang: statisk billede

Overvejet men fravalgt til fordel for live embed (ejerens valg): statiske VeloViewer-billeder ville kræve et login-baseret eksport-flow (ingen dokumenteret billed-API), og ville stadig kræve synlig VeloViewer-branding + backlink "i eksisterende skala". Live embed er både juridisk enklest (det er VeloViewers foretrukne, dokumenterede metode) og teknisk enklest (ingen billedhåndtering/Storage-upload).

## Segment-matching: hvordan vi finder det rigtige Strava-segment-ID

Der findes ingen offentlig Strava-API til at oprette ruter eller matche et GPX-spor mod segment-databasen — det er UI-only (Route Builder, kræver Strava Premium/Summit, som ejeren allerede har). Derfor er dette den ene del af flowet, der kræver browserautomatisering (Playwright, logget ind på ejerens konto) i stedet for et rent API-kald — en afvejning ejeren har accepteret bevidst (samme handling som en person ville udføre manuelt).

Flow pr. stigning (i nyt script `agents/veloviewer_agent.py`):

1. **Udtræk klatre-GPX'en**: genbrug vinduessøgningen fra `climb_profile_generator.py` (proportional km-position i etapens GPX, jf. dens eksisterende design) til at finde stigningens lat/lon-udsnit, og skriv det til en midlertidig GPX-fil. Ingen ny parsing-logik — kald ind i den eksisterende funktion i stedet for at duplikere den.
2. **Playwright → Strava Route Builder**: log ind (session genbruges via gemt `storage_state` JSON, så vi ikke logger ind for hver stigning), opret en rute af klatre-GPX'en via Route Builder/GPX-importeren, navngivet genkendeligt (`KP-{race_slug}-s{stage}-{climb_slug}`, så den er let at identificere/rydde op i).
3. **Læs rutens "Segments"-faneblad**: hent kandidat-segment-ID'er (fra hrefs, ingen tekstdata gemmes fra selve siden — kun ID'et, som er et Strava-internt nøgletal, ikke "Strava Data" i T&C-forstand).
4. **Verificér hver kandidat via Stravas officielle segment-API** (`GET /segments/{id}`, OAuth via `STRAVA_CLIENT_ID`/`STRAVA_CLIENT_SECRET`/`STRAVA_REFRESH_TOKEN` — allerede i `.env`): sammenlign `distance`/`average_grade`/afledt højdemeter mod DB'ens `length_km`/`avg_gradient`/`elevation_m`, samme tolerance-mønster som `climbfinder_agent.py`s `metrics_ok()` og `climb_profile_generator.py`s `within_tolerance()` (±33% længde, ±35%/min. 150m højdemeter, ±1.5% hældning). Ny funktion: `segment_matches_climb()`. De hentede Strava-felter bruges **kun i denne sammenligning, i hukommelsen** — skrives aldrig til DB eller logges i klartekst nogen steder synligt for andre.
5. **Ingen kandidat inden for tolerance** → stigningen springes over og logges som "intet VeloViewer-match", falder tilbage til eksisterende `climbfinder_agent.py` → `climb_profile_generator.py`-kæde. Aldrig gæt (samme princip som resten af pipelinen, jf. `CLAUDE.md` §7).
6. **Match fundet** → skriv **kun** `stage_climbs.veloviewer_segment_id` (nyt DB-felt, se nedenfor). Rører aldrig et allerede sat `veloviewer_segment_id` uden `--overwrite` (samme mønster som de andre scripts).
7. **Ryd op**: slet den midlertidige Strava-rute igen (holder ejerens "Mine ruter"-liste ren — ruten var kun et redskab til at finde ID'et).

## Database

Ny nullable kolonne: `stage_climbs.veloviewer_segment_id integer`. Ingen andre nye felter — ingen `profile_source`-enum nødvendig, da prioritetsrækkefølgen udtrykkes direkte i frontend-rendering (se nedenfor), ikke i data-modellen.

`api.py:569` (`GET`-endpoint for `stage_climbs`) skal have `veloviewer_segment_id` tilføjet til `select=`-listen.

## Frontend

`cykel-frontend/app/[slug]/stage/[n]/ClimbProfile.tsx`:

- `Climb`-typen (linje 7-17) får `veloviewer_segment_id: number | null`.
- `hasVisualProfile()` (linje 226-228) udvides: `!!(c.veloviewer_segment_id || c.profile_image_url || (c.gradient_sections?.length ?? 0) > 0)`.
- Rendering (omkring linje 325-346) får en ny **første** gren før den eksisterende `profile_image_url`-gren:
  ```tsx
  {activeClimb.veloviewer_segment_id ? (
    <iframe
      src={`https://veloviewer.com/segments/${activeClimb.veloviewer_segment_id}/embed`}
      style={{ width: "100%", height: 450, border: 0 }}
      scrolling="no"
      title={activeClimb.name}
    />
  ) : activeClimb.profile_image_url ? (
    /* eksisterende gren, uændret */
  ) : /* eksisterende gradient_sections-gren, uændret */}
  ```
  Ingen lightbox for embed'en (den er allerede interaktiv/fuld bredde) — lightbox-knappen bruges kun for de to eksisterende statiske grene.

## Pipeline-rækkefølge

Opdateres i `ARKITEKTUR.md` og `.claude/agents/stigningsagent.md`:

`gpx_climb_agent.py` → `profile_reader_agent.py` → **`veloviewer_agent.py` (ny, prioritet 1)** → `climbfinder_agent.py` (prioritet 2, uændret) → `climb_profile_generator.py` (prioritet 3, uændret fallback) → `climb_region_agent.py` → `elevation_image_agent.py`.

`race_prep_pipeline.py` får et nyt trin indsat mellem eksisterende trin 6 og 7 (før ClimbFinder-trinnet).

## Credentials (allerede i `.env`)

- `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN` — til det officielle API-verifikationskald. Access token fornyes af scriptet selv ved hvert kørsel via refresh-flowet; det korte access token, ejeren delte, gemmes ikke.
- Nye, mangler stadig: `STRAVA_EMAIL`, `STRAVA_PASSWORD` — til Playwright-loginnet mod Route Builder (separat fra API-app'en). Aldrig hardkodet, jf. sikkerhedsnoten i `ARKITEKTUR.md`.

## Risikobegrænsning

- Kun løb i `CYCLINGSTAGE_GPX_PAGES` (giro, tour-de-france, dauphiné, tour-de-suisse) har en klatre-GPX-kilde i forvejen — omfanget er derfor naturligt begrænset til dem.
- Tour de France prioriteres, jf. `stigningsagent.md` og `STRATEGI.md`.
- Pauser mellem Playwright-handlinger for at holde volumen/mønster lavt og undgå unødig opmærksomhed på kontoen.
- Oprettede Strava-ruter slettes igen efter brug (trin 7 ovenfor).

## Testplan

1. Kør `veloviewer_agent.py` for **én** kendt stigning med et allerede-velkendt Strava-segment (fx en TdF-2026-stigning), uden `--write-db`, og verificér manuelt at det matchede segment-ID er korrekt (sammenlign selv `veloviewer.com/segments/{id}` mod DB-data).
2. Kør for én hel etape (`--stage N`), stadig uden DB-skrivning, gennemgå log for match/ikke-match pr. stigning.
3. Ejeren godkender, derefter `--write-db` for samme etape.
4. Rul ud til resten af Tour de France 2026, derefter øvrige dækkede løb.

## Ikke i scope for denne omgang

- Statiske VeloViewer-billeder (fravalgt, se ovenfor).
- Løb uden GPX-kilde i `CYCLINGSTAGE_GPX_PAGES`.
- Ændringer i `climbfinder_agent.py`/`climb_profile_generator.py`s interne logik — de forbliver uændrede fallback-trin.
- Automatisk oprydning af **allerede eksisterende** fejlbehæftede ClimbFinder-matches — ortogonalt problem (STRATEGI.md nævner det som kendt issue, men det er ikke denne agents opgave at rette op på historiske ClimbFinder-fejl, kun at levere et bedre førstevalg fremadrettet).
