# VeloViewer-baseret stigningsprofil (ny prioritet 1) — design

Dato: 2026-07-07 (arkitektur forenklet 2026-07-08 efter test)
Status: Backend (`veloviewer_agent.py` + `veloviewer_strava_api.py`) bygget og testkørt mod tour-de-france-2026 etape 6 — 2/5 stigninger verificeret matchet (Côte de Mauvezin, Col du Tourmalet), 3/5 korrekt faldet tilbage til eksisterende pipeline. **Frontend-ændringen (`ClimbProfile.tsx`) og `--write-db`-kørsel mod produktion mangler stadig** — afventer ejerens godkendelse før rigtig DB-skrivning.

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

**Opdatering 2026-07-08 (efter test): browserautomatisering droppet.** Den oprindelige plan brugte Playwright til at logge ind og oprette en rute i Strava Route Builder, for derefter at læse dens "Segments"-faneblad. Under test viste det sig at:

- Stravas login-side er beskyttet af reCAPTCHA — automatisk login er hverken muligt eller ønsket, og kontoen bruger nu engangskoder (ikke password) for login.
- Segment-markørerne i Route Builder er tegnet på et Mapbox vector-tile-lag (canvas), ikke almindelige HTML-links — at udtrække deres ID'er pålideligt ville kræve enten at afkode binære vector tiles eller klikke præcist på markører (risikabelt: et forkert klik tilføjer et rutepunkt i stedet).
- Stravas officielle, **offentlige** API har derimod et `/segments/explore`-endpoint (bounding box → kandidat-segmenter), som viste sig at ramme plet for præcis vores højst-prioriterede case: **berømte Tour de France-bjerge er blandt de mest populære segmenter i deres område** (verificeret: Col du Tourmalet fundet med navnet "Col du Tourmalet (par Sainte Marie de Campan)", identisk med det ejeren selv fandt manuelt i Strava-appen).

Flow pr. stigning (i `agents/veloviewer_agent.py`, ingen browser/login nødvendig):

1. **Udtræk klatre-GPX'en**: genbrug vinduessøgningen fra `climb_profile_generator.py` (`download_stage_gpx`, `cumulative_distances_km`, `locate_climb_segment`) til at finde stigningens lat/lon-udsnit. Ingen ny parsing-logik — kalder direkte ind i de eksisterende funktioner.
2. **Beregn bounding box** om GPX-udsnittet, udvidet med 20% på hver led (`compute_padded_bbox()`), og kald Stravas officielle `GET /segments/explore` (OAuth via `STRAVA_CLIENT_ID`/`STRAVA_CLIENT_SECRET`/`STRAVA_REFRESH_TOKEN`, allerede i `.env`) — returnerer op til 10 kandidat-segmenter, rangeret efter Stravas egen popularitet.
3. **Verificér hver kandidat** via `GET /segments/{id}` mod DB'ens `length_km`/`avg_gradient`/`elevation_m`: samme tolerance-mønster som `climbfinder_agent.py`s `metrics_ok()` (±33% længde, ±35%/min. 150m højdemeter, ±1.5% hældning) — **plus et navnetjek** (`name_plausible_match()`): mindst ét betydende ord fra DB-klatrenavnet skal indgå i segmentnavnet. Dette ekstra guard var nødvendigt, fordi `/segments/explore` søger rent geografisk, ikke på navn — et testfund viste at "Col d'Aspin" ellers talmæssigt matchede "Ste Marie - Tourmalet 10kms" (en del af nabo-klatren Tourmalet), præcis den kendte fejlklasse fra STG-004/STG-009 (rigtige tal, forkert bjerg). Alle hentede Strava-felter (navn, distance, hældning, højdemeter) bruges **kun i denne sammenligning, i hukommelsen** — skrives aldrig til DB eller logges nogen steder synligt for andre.
4. **Ingen kandidat består begge tjek** → stigningen springes over og logges som "intet VeloViewer-match", falder tilbage til eksisterende `climbfinder_agent.py` → `climb_profile_generator.py`-kæde. Aldrig gæt (samme princip som resten af pipelinen, jf. `CLAUDE.md` §7). Kendt begrænsning: navnetjekket er streng substring-matching, ikke stavefejl-tolerant — et testfund ("Loucroup" i DB vs. "Loucrup" i Strava-segmentnavnet) blev korrekt men unødvendigt afvist. Acceptabelt: en tabt (men sikker) match er bedre end en forkert.
5. **Match fundet** → skriv **kun** `stage_climbs.veloviewer_segment_id` (nyt DB-felt, se nedenfor). Rører aldrig et allerede sat `veloviewer_segment_id` uden `--overwrite` (samme mønster som de andre scripts).

**Kendt begrænsning ved denne metode:** `/segments/explore` returnerer kun top-10 mest populære segmenter i boksen — ikke en udtømmende liste. For mindre kendte, lokale stigninger i segment-tætte områder (bekræftet under test: en forstadsklatre uden for TdF) kan det rigtige segment blive skygget af mere populære naboer, og intet match findes. Det er en accepteret begrænsning: sådanne stigninger falder tilbage til den eksisterende pipeline, præcis som designet allerede forudsatte.

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

- `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN` — eneste påkrævede credentials. Bruges til både `/segments/explore` og `/segments/{id}`. Access token fornyes af scriptet selv ved hvert kørsel via refresh-flowet.
- `STRAVA_EMAIL`/`STRAVA_PASSWORD` er **ikke længere nødvendige** (browserlogin droppet, se ovenfor) — kan fjernes fra `.env` igen.

## Risikobegrænsning

- Kun løb i `CYCLINGSTAGE_GPX_PAGES` (giro, tour-de-france, dauphiné, tour-de-suisse) har en klatre-GPX-kilde i forvejen — omfanget er derfor naturligt begrænset til dem.
- Tour de France prioriteres, jf. `stigningsagent.md` og `STRATEGI.md`.
- Pause (1s) mellem Strava API-kald pr. kandidat-segment, for at holde volumen lav.
- Ingen konto-automatiseringsrisiko tilbage: metoden bruger udelukkende Stravas officielle, offentlige API — ingen login, ingen browser, ingen ToS-gråzone.

## Testplan

1. ✅ Kørt for tour-de-france-2026 etape 6 (`--overwrite`, ingen `--write-db`): Côte de Mauvezin (segment 1936607) og Col du Tourmalet (segment 37855763) verificeret matchet; Côte de Loucroup, Col d'Aspin og Gavarnie-Gèdre korrekt uden match (falder tilbage).
2. Byg frontend-ændringen (`ClimbProfile.tsx`) og verificér visuelt i browser at embed'en virker for et rigtigt matchet segment-ID.
3. Ejeren godkender, derefter `--write-db` for etape 6.
4. Rul ud til resten af Tour de France 2026, derefter øvrige dækkede løb.

## Ikke i scope for denne omgang

- Statiske VeloViewer-billeder (fravalgt, se ovenfor).
- Løb uden GPX-kilde i `CYCLINGSTAGE_GPX_PAGES`.
- Ændringer i `climbfinder_agent.py`/`climb_profile_generator.py`s interne logik — de forbliver uændrede fallback-trin.
- Automatisk oprydning af **allerede eksisterende** fejlbehæftede ClimbFinder-matches — ortogonalt problem (STRATEGI.md nævner det som kendt issue, men det er ikke denne agents opgave at rette op på historiske ClimbFinder-fejl, kun at levere et bedre førstevalg fremadrettet).
