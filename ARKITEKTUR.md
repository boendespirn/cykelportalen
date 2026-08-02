# klassementet.dk — Arkitektur og pipelines

Dette er **kortet** over den eksisterende kodebase: hvilke pipelines findes, hvad gør de, og hvor ligger de. Agenterne bruger det til at finde deres værktøj.

**Princip:** Hver kørsel starter fra en frisk klon. Agenter læser den **faktiske kode** på hver kørsel (så de altid bruger nyeste version) — dette kort er bare indekset, der peger dem hen til den rigtige fil. Hardkodér aldrig pipeline-logik ind i agent-filerne; peg på scriptet i stedet.

Alle scripts ligger i `agents/`. Hemmeligheder hører hjemme i miljøvariabler — **aldrig** i koden (se sikkerhedsnoten til sidst).

---

## Backend og data

- **`api.py`** — FastAPI-backend.
- **Supabase** — database (bl.a. tabellen `stage_climbs`) og Storage (profil-/højdebilleder).

## Orkestrering

- **`race_prep_pipeline.py RACE-SLUG`** — gør et løb klar til publikation i 7 trin: 1) startliste, 2) etapedata + profilbilleder, 3) høj-kvalitets profiler, 4) rytterbilleder, 5) rytterstats, 6) stigningsprofiler (ClimbFinder), 7) stigningsprofiler-fallback (`climb_profile_generator.py`, for stigninger ClimbFinder ikke fandt/verificerede — se stignings-pipelinen nedenfor).
- **`daily_update.py`** — dagligt: startlister (løb der starter inden for 90 dage), etaper (løb uden etapedata), re-sync af manglende billeder, og noterer hvilke resultat-agenter der bør køres for igangværende løb.
- **`weekly_update.py`** — ugentligt: UCI-ranglister for alle ryttere.

---

## Stignings-/profil-pipeline (kerne for stigningsagenten)

Dataflow for korrekte stigningsprofiler:

1. **`stage_pcs_agent.py PCS-SLUG`** — scraper etapedata fra ProCyclingStats (Playwright, pga. Cloudflare).
2. **`gpx_climb_agent.py --race SLUG [--stage N | --all]`** — henter klatreinfo fra PCS og genererer `gradient_sections` i `stage_climbs`.
3. **`profile_reader_agent.py --race SLUG [--stage N | --all]`** — bruger **Claude vision** til at aflæse de rigtige klatredata fra højdeprofil-billedet (navn, km fra start, længde, gradient, kategori), erstatter syntetiske data, og kører ClimbFinder-søgning pr. klatrenavn.
4. **`veloviewer_agent.py --race SLUG [--stage N] [--all] [--overwrite] [--write-db]`** — **ny prioritet 1** for visuel stigningsprofil (før ClimbFinder). Finder det korrekte Strava-segment via Stravas officielle, offentlige `/segments/explore`-API (bounding box beregnet fra klatrens GPX-udsnit, samme vinduessøgning som `climb_profile_generator.py`), verificerer kandidater mod DB-data (længde/højdemeter/hældning-tolerance, samme mønster som `climbfinder_agent.py`s `metrics_ok()`) **plus et navnetjek** (`name_plausible_match()` i `veloviewer_strava_api.py`) — nødvendigt fordi explore-endpointet søger geografisk, ikke på navn. Skriver kun det bare `stage_climbs.veloviewer_segment_id`; frontend bygger selv VeloViewers embed-URL derfra. Ingen login/browser nødvendig. Kendt begrænsning: finder kun match blandt Stravas top-10 mest populære segmenter i boksen — rammer godt for berømte TdF-bjerge, mindre pålideligt for lokale stigninger i segment-tætte områder. Se `docs/superpowers/specs/2026-07-07-veloviewer-climb-profiles-design.md`.
5. **`climbfinder_agent.py --race SLUG [--stage N] [--all] [--overwrite]`** — finder CF-profilbilledet og gemmer `profile_image_url`. **Verificerer** CF-metrics (længde, finishElevation, gradient) mod DB-data og afviser forkerte match automatisk. Fallback: beregner summit-koordinater fra route_points og reverse-geokoder (Nominatim) → nyt søgeterm. Indeholder `SEARCH_OVERRIDES` (manuelle navne-rettelser; `None` = spring over) og `CLIMB_PREFIXES`.
6. **`climb_profile_generator.py --race SLUG (--stage N | --all) [--style full|minimal|both] [--write-db] [--overwrite]`** — **fast, automatisk fallback** for stigninger hverken `veloviewer_agent.py` eller `climbfinder_agent.py` fandt eller kunne verificere. Genererer klassementet.dk's egne profilbilleder direkte fra rå GPX-højdedata (cyclingstage.com), delt i 20 farvede sektioner efter hældning. Lokaliserer klimresegmentet i GPX-sporet via vinduessøgning mod DB'ens kendte højdemeter/hældning, og skriver **kun** til DB når `within_tolerance()` godkender det udledte segment mod DB-data — ellers logges stigningen som sprunget over, aldrig gættet på. Rører aldrig et eksisterende `profile_image_url` uden eksplicit `--overwrite`. GPX-kilden (`CYCLINGSTAGE_GPX_PAGES`) dækker p.t. kun et udvalg af løb (giro, tour de france, critérium du dauphiné, tour de suisse) — for øvrige løb springes etapen/løbet automatisk og ufarligt over.
7. **`climb_region_agent.py --race SLUG`** — klassificerer `stage_climbs.region` via ét Claude-kald.
8. **`elevation_image_agent.py [--race SLUG]`** — downloader højdeprofil-billeder fra PCS (Playwright) og gemmer i Supabase Storage.

Relaterede: `gpx_agent.py`, `pcs_profile_image_agent.py`, `giro_profile_agent.py`.

**`agents/stage_profile_generator.py --race SLUG --stage N [--write-db] [--overwrite]`** — fallback for **hele etapens** højdeprofil (`stages.elevation_image_url`), til brug når PCS ikke har noget hel-etape-billede overhovedet (se STG-002, fx tour-de-france-2026 etape 3). Genbruger climb_profile_generator.py's GPX-kilde/farveskala, men tegner hele etapens spor og overlejrer kendte kategoriserede stigninger (fra `stage_climbs`) som markerede bånd med navn/gradient. Skriver kun når `elevation_image_url` er NULL, medmindre `--overwrite`. Manuelt/pr.-etape værktøj (ikke et fast pipeline-trin endnu) — kør når `elevation_image_agent.py` ikke fandt noget PCS-billede for en etape og løbet er dækket af `CYCLINGSTAGE_GPX_PAGES`.

**`agents/profile_image_digitizer.py`** — **højdekilde nr. 2, når der ikke findes GPX.** Udtrækker højdekurven (km → meter) direkte fra arrangørens **officielle** etapeprofilbillede og returnerer den i samme `[(km, højde_m)]`-form, som `render_stage_profile()` allerede tager. `stage_profile_generator.py` bruger den automatisk som fallback: GPX er stadig førstevalg, og alle løb med GPX-kilde er upåvirkede. Metode: spor det farvede fyld **nedefra og op** (så labellernes lodrette hjælpelinjer ikke forveksles med terræn), fjern markør-artefakter mod den lokale median (`_despike()`), kalibrér pixel→meter med mindste kvadraters linje på de **indre** officielle ankre, snap toppunkter til lokalt maksimum, og **tving til sidst kurven gennem hvert officielt anker** med en stykvis residual-korrektion ("rubber sheeting"), så både start/mål og alle kendte tophøjder rammer præcist (uden den viste etape 6's Słodyczki 1.025 m mod officielle 1.082 m). **Validerer altid mod samtlige officielle ankre og returnerer `None`, hvis `max_deviation_m` overskrides** — en ugyldig kurve kan ikke publiceres. Ankre og kilde står i `agents/profile_image_anchors.json`, ét sæt pr. løb med kildehenvisning og aflæsningsdato. Udrullet for tour-de-pologne-2026 (7/7 etaper, max afvigelse 3-59 m). **Licens:** vi udtrækker *fakta* (terrænets højde langs en offentlig vej) og viser aldrig kildebilledet — samme skelnen som `aso_roadbook_agent.py`. Ejeren godkendte fremgangsmåden 2026-08-02.

**Vigtigt:** `stage_pcs_agent.py`'s `save_stages()` udelader `elevation_image_url` fra sin upsert-payload når PCS ikke fandt et billede den kørsel — ellers ville `Prefer: resolution=merge-duplicates` nulstille et allerede sat billede (fx et `stage_profile_generator.py`-genereret) til NULL, hver gang etapen re-scrapes uden held (samme klasse fejl som STG-007's `--overwrite`-regression i climbfinder_agent.py).

---

## Datakilde-dækning (og hvad man gør, når den mangler)

Vores stignings- og profildata står og falder med **to eksterne kilder**, og de dækker ikke alle løb:

1. **PCS** — klatredata (`gpx_climb_agent.py`) og profilbilleder. Dækker de fleste løb, men ofte først tæt på løbsstart for mindre WorldTour-løb.

   **Vigtigt (fundet 2026-08-02):** `gpx_climb_agent.py` scraper kun etapens *hovedside*. De rigtige klatredata ligger på undersiden **`/info/profiles`**, som ud over hel-etape-profilen har en **profil pr. stigning med gradient-tabel pr. delstrækning** (La Flamme Rouge). Det er derfor, agenten meldte "ingen klatredata" for Tour de Pologne og i stedet fabrikerede syntetiske stigninger — dataen var der hele tiden. `elevation_image_agent.py:132` besøger allerede siden, men filtrerer `-climb`-billederne fra. Tjek altid `/info/profiles`, før et løb erklæres for udækket. Bemærk også, at `pcs_profile_image_agent.py` kan vælge et `-map-`-rutekort frem for den rigtige `-profile-`-fil (skete for Pologne etape 1, 6 og 7).
2. **cyclingstage.com** — rå GPX (`CYCLINGSTAGE_GPX_PAGES` i `climb_profile_generator.py`). Både per-stigning-fallbacken og hel-etape-profilen (`stage_profile_generator.py`) genbruger denne kilde, så et løb uden GPX-kilde kan **hverken** få stigningsprofiler eller hel-etape-profil.

**Kendt hul (verificeret 2026-07-31 mod cyclingstages rå 2026-index, 88 links):** Tour de Pologne, San Sebastián, Cyclassics, Renewi Tour, Bretagne Classic, GP Québec, GP Montréal, Il Lombardia og Guangxi findes **ikke** på cyclingstage. For Pologne har PCS desuden ingen klatredata på nogen af de 7 etaper (bekræftet ved genkørsel). Kæden knækker altså i første led — alt nedstrøms er afhængigt af den.

**Omvendt hul (samme kontrol):** `CYCLINGSTAGE_GPX_PAGES` konfigurerer kun 5 løb, men cyclingstage udgiver GPX for ~20 — heriblandt **alle fem Monuments** og flere WorldTour-etapeløb, vi allerede har i databasen (Milano-Sanremo, Paris-Roubaix, Ronde van Vlaanderen, Liège, Amstel, Strade Bianche, E3, Omloop, Dwars door Vlaanderen, Gent-Wevelgem, Kuurne, Brabantse Pijl, Paris-Nice, Tirreno-Adriatico, Itzulia, Tour of the Alps, O Gran Camino). Bemærk at endagsløb bruger mønsteret `…/2026/route.gpx` **uden** etapenummer, mens `get_gpx_url_for_stage()` kun matcher `stage-(\d+)…\.gpx` — Monuments kræver derfor også en regex-udvidelse, ikke kun en config-linje. Se DATA-003 i `state/issues.md`.

### Regel: manglende datakilde eskaleres, den løses ikke selv

Når et løb ikke kan få samme datadækning som de løb, vi normalt henter data for:

1. **Fastslå ved kilden**, om dataen reelt ikke findes, eller om vores konfiguration bare ikke peger på den. Verificér **råt** — hent siden og læs de faktiske links. Opsummerende værktøjer kan finde på plausible URL'er, der ikke eksisterer (bekræftet 2026-07-31: seks konstruerede cyclingstage-URL'er gav alle 404).
2. **Accepter problemet og rapportér det.** Byg ikke selv en ny kilde-integration.
3. **Bed ejeren bekræfte, at research-agenten må sættes på** at finde alternative datakilder, som ejeren derefter godkender.

Begrundelsen er strategisk, ikke kosmetisk: ujævn dækning giver tynde landingssider, tynde sider giver høj bounce rate, og det er det vigtigste enkeltmål i SEO-strategien. En ny datakilde er desuden en ny løsningsmekanisme og kræver godkendelse først (`CLAUDE.md` §7 og §9.5).

**Kilde-hierarki, i prioriteret rækkefølge:**

1. **Officiel roadbook (PDF/site)** — stærkest både fagligt og licensmæssigt, fordi vi udtrækker **fakta** (stigningskategorier, km, hældning, mellemsprints) og ikke billeder. Mønsteret findes allerede i `aso_roadbook_agent.py` (letour.fr, lavuelta.es). Bekræftet tilgængelig for Tour de Pologne: `tourdepologne.pl/wp-content/uploads/2026/roadbook-2026.pdf` (HTTP 200, 121 MB).
2. **cyclingstage GPX** — rå rutedata, som vi selv renderer profiler ud fra.
3. **Intet** — markér løbet som udækket frem for at gætte.

**Licens er ikke til forhandling:** færdige profilbilleder fra tredjepart er præcis det, LEG-001 ryddede op efter. GPX-/rutedata og roadbook-fakta er langt mere forsvarlige. Enhver ny billedkilde skal licensvurderes eksplicit, jf. `CLAUDE.md` §7.

---

## SEO / Search Console

- **`agents/gsc_agent.py`** — henter Search Console-data (performance pr. søgeord/side, sitemap-status, URL Inspection) via service account (`GSC_SERVICE_ACCOUNT_JSON` + `GSC_SITE_URL` i Railway). Finder striking-distance-søgeord (plads 4-20) og lav-CTR-sider til SEO-agenten. Kræver at service account-emailen er tilføjet som bruger i Search Console → Indstillinger → Brugere og tilladelser.
- **IndexNow** — `submit_indexnow()` i `api.py` POST'er til `api.indexnow.org` som baggrundsopgave. Trigges to steder: (1) når en artikel godkendes (`/admin/articles/{id}/approve`), (2) i `daily_update.py`s `notify_indexnow()` for løbets side + alle dens etapesider, hver gang startliste eller etapedata er blevet oprettet/opdateret for løbet i den kørsel (SEO-010). Nøglefil: `cykel-frontend/public/1a5a3688cfd86781c40cef01ce453403.txt` (offentlig, ikke hemmelig). **Vigtigt:** Google understøtter ikke IndexNow-protokollen (kun Bing, Yandex, Naver, Seznam, Yep) — det er et billigt supplement til crawl-signalet for de søgemaskiner, aldrig en genvej til Google-indeksering. Google-indeksering afhænger af sitemap.xml, intern linking og webstedets opfattede autoritet/vigtighed, ikke IndexNow.
- **`GET /admin/issues`** (i `api.py`) — parser `state/issues.md` til JSON. Bruges af opgave-dashboardet på `/admin/opgaver` i frontenden.

## Øvrige domæner (indeks ud fra filnavne — bekræft gerne detaljer)

- **Ryttere:** `startlist_agent.py`, `rider_photo_agent.py`, `fix_rider_photos.py`, `rider_stats_agent.py`, `rider_speciality_agent.py`, `hometown_agent.py`, `local_favorite_agent.py`.
- **Resultater:** `results_agent.py`, `giro_results_agent.py`, `historical_results_agent.py`, `run_results.py`.
- **Løb:** `race_agent.py`, `race_description_agent.py`, `historical_race_agent.py`, `read_races.py`.
- **Nyheder:** `news_agent.py`, `news_publisher_agent.py`, `ai_news_processor.py`, `rss_news_scraper.py`.
- **Social/marketing:** `social_agent.py`, `facebook_auth.py`, `fb_article_image.py`, `fb_branding.py`, `instagram_*` (auth, carousel, pinned, image, post), `brand_logo.py`, `image_generator.py`, `intro_content.py`.
- **Kort/billeder:** `mapillary_agent.py`, `elevation_image_agent.py`.

---

## Sikkerhed (skal rettes)

- `climbfinder_agent.py` indeholder p.t. et **hardkodet ClimbFinder-login** i klartekst. Flyt det til miljøvariabler (fx `CF_EMAIL`, `CF_PASSWORD`) og skift passwordet.
- Gennemgå alle scripts for andre hardkodede nøgler. Intet følsomt må committes til repoet eller indgå i en agent-fil.
