# klassementet.dk — Arkitektur og pipelines

Dette er **kortet** over den eksisterende kodebase: hvilke pipelines findes, hvad gør de, og hvor ligger de. Agenterne bruger det til at finde deres værktøj.

**Princip:** Hver kørsel starter fra en frisk klon. Agenter læser den **faktiske kode** på hver kørsel (så de altid bruger nyeste version) — dette kort er bare indekset, der peger dem hen til den rigtige fil. Hardkodér aldrig pipeline-logik ind i agent-filerne; peg på scriptet i stedet.

Alle scripts ligger i `agents/`. Hemmeligheder hører hjemme i miljøvariabler — **aldrig** i koden (se sikkerhedsnoten til sidst).

---

## Backend og data

- **`api.py`** — FastAPI-backend.
- **Supabase** — database (bl.a. tabellen `stage_climbs`) og Storage (profil-/højdebilleder).

## Orkestrering

- **`race_prep_pipeline.py PCS-SLUG [--year N] [--stage N] [--historic]`** — gør et løb klar til publikation. **Trinnene står ikke i filen**: den henter dem fra `agent_catalog.JOBS["fuld_forberedelse"]`, altså præcis de samme trin som knappen i admin. Skal rækkefølgen ændres, ændres den i `agent_catalog.py`. `--stage N` kører kun én etape og springer de løbsdækkende trin over.
- **`daily_update.py`** — dagligt: startlister (løb der starter inden for 90 dage), etaper (løb uden etapedata), re-sync af manglende billeder, og noterer hvilke resultat-agenter der bør køres for igangværende løb.
- **`weekly_update.py`** — ugentligt: UCI-ranglister for alle ryttere.

---

## Stignings-/profil-pipeline (kerne for stigningsagenten)

Dataflow for korrekte stigningsprofiler:

1. **`stage_pcs_agent.py PCS-SLUG`** — scraper etapedata fra ProCyclingStats (Playwright, pga. Cloudflare).
2. **`gpx_climb_agent.py --race SLUG [--stage N | --all]`** — henter klatreinfo fra PCS og genererer `gradient_sections` i `stage_climbs`.
3. **`profile_reader_agent.py --race SLUG [--stage N | --all]`** — bruger **Claude vision** til at aflæse de rigtige klatredata fra højdeprofil-billedet (navn, km fra start, længde, gradient, kategori), erstatter syntetiske data, og kører ClimbFinder-søgning pr. klatrenavn.
4. **`veloviewer_agent.py --race SLUG [--stage N] [--all] [--overwrite] [--write-db]`** — **ny prioritet 1** for visuel stigningsprofil (før ClimbFinder). Finder det korrekte Strava-segment via Stravas officielle, offentlige `/segments/explore`-API (bounding box beregnet fra klatrens GPX-udsnit, samme vinduessøgning som `climb_profile_generator.py`), verificerer kandidater mod DB-data (længde/højdemeter/hældning-tolerance, samme mønster som `climbfinder_agent.py`s `metrics_ok()`) **plus et navnetjek** (`name_plausible_match()` i `veloviewer_strava_api.py`) — nødvendigt fordi explore-endpointet søger geografisk, ikke på navn. Skriver kun det bare `stage_climbs.veloviewer_segment_id`; frontend bygger selv VeloViewers embed-URL derfra. Ingen login/browser nødvendig. Kendt begrænsning: finder kun match blandt Stravas top-10 mest populære segmenter i boksen — rammer godt for berømte TdF-bjerge, mindre pålideligt for lokale stigninger i segment-tætte områder. Se `docs/superpowers/specs/2026-07-07-veloviewer-climb-profiles-design.md`.
5. **`climbfinder_agent.py`** — **UDE AF DRIFT (2026-09-09).** Taget ud af `agent_catalog.py` og af `race_prep_pipeline.py`: sitet viser udelukkende VeloViewers eget embed, så ClimbFinder-billeder havde ingen visningsvej. Filen ligger stadig på disken og kan køres manuelt, men må ikke lægges tilbage i en pipeline uden ejerens accept. Oprindelig funktion: finder CF-profilbilledet og gemmer `profile_image_url`. **Verificerer** CF-metrics (længde, finishElevation, gradient) mod DB-data og afviser forkerte match automatisk. Fallback: beregner summit-koordinater fra route_points og reverse-geokoder (Nominatim) → nyt søgeterm. Indeholder `SEARCH_OVERRIDES` (manuelle navne-rettelser; `None` = spring over) og `CLIMB_PREFIXES`.
6. **`climb_profile_generator.py --race SLUG (--stage N | --all) [--style full|minimal|both] [--write-db] [--overwrite]`** — **ikke længere et pipeline-trin (2026-09-09)**; stignings-pipelinen består nu alene af `veloviewer_agent.py`. Modulet er stadig i aktiv brug som **bibliotek**: `stage_profile_generator.py` og `veloviewer_agent.py` importerer dets GPX-kilde (`CYCLINGSTAGE_GPX_PAGES`), farveskala og vinduessøgning, så det må ikke fjernes. Kørt som script genererer det klassementet.dk's egne profilbilleder direkte fra rå GPX-højdedata (cyclingstage.com), delt i 20 farvede sektioner efter hældning. Lokaliserer klimresegmentet i GPX-sporet via vinduessøgning mod DB'ens kendte højdemeter/hældning, og skriver **kun** til DB når `within_tolerance()` godkender det udledte segment mod DB-data — ellers logges stigningen som sprunget over, aldrig gættet på. Rører aldrig et eksisterende `profile_image_url` uden eksplicit `--overwrite`. GPX-kilden (`CYCLINGSTAGE_GPX_PAGES`) dækker p.t. kun et udvalg af løb (giro, tour de france, critérium du dauphiné, tour de suisse) — for øvrige løb springes etapen/løbet automatisk og ufarligt over.
7. **`climb_region_agent.py --race SLUG`** — klassificerer `stage_climbs.region` via ét Claude-kald.
8. **`elevation_image_agent.py [--race SLUG]`** — downloader højdeprofil-billeder fra PCS (Playwright) og gemmer i Supabase Storage.

Relaterede: `gpx_agent.py`, `pcs_profile_image_agent.py`, `giro_profile_agent.py`.

**`agents/stage_profile_generator.py --race SLUG --stage N [--write-db] [--overwrite]`** — fallback for **hele etapens** højdeprofil (`stages.elevation_image_url`), til brug når PCS ikke har noget hel-etape-billede overhovedet (se STG-002, fx tour-de-france-2026 etape 3). Genbruger climb_profile_generator.py's GPX-kilde/farveskala, men tegner hele etapens spor og overlejrer kendte kategoriserede stigninger (fra `stage_climbs`) som markerede bånd med navn/gradient. Skriver kun når `elevation_image_url` er NULL, medmindre `--overwrite`. Manuelt/pr.-etape værktøj (ikke et fast pipeline-trin endnu) — kør når `elevation_image_agent.py` ikke fandt noget PCS-billede for en etape og løbet er dækket af `CYCLINGSTAGE_GPX_PAGES`.

**`agents/profile_image_digitizer.py`** — **højdekilde nr. 2, når der ikke findes GPX.** Udtrækker højdekurven (km → meter) direkte fra arrangørens **officielle** etapeprofilbillede og returnerer den i samme `[(km, højde_m)]`-form, som `render_stage_profile()` allerede tager. `stage_profile_generator.py` bruger den automatisk som fallback: GPX er stadig førstevalg, og alle løb med GPX-kilde er upåvirkede. Metode: spor det farvede fyld **nedefra og op** (så labellernes lodrette hjælpelinjer ikke forveksles med terræn), fjern markør-artefakter mod den lokale median (`_despike()`), kalibrér pixel→meter med mindste kvadraters linje på de **indre** officielle ankre, snap toppunkter til lokalt maksimum, og **tving til sidst kurven gennem hvert officielt anker** med en stykvis residual-korrektion ("rubber sheeting"), så både start/mål og alle kendte tophøjder rammer præcist (uden den viste etape 6's Słodyczki 1.025 m mod officielle 1.082 m). **Validerer altid mod samtlige officielle ankre og returnerer `None`, hvis `max_deviation_m` overskrides** — en ugyldig kurve kan ikke publiceres. Ankre og kilde står i `agents/profile_image_anchors.json`, ét sæt pr. løb med kildehenvisning og aflæsningsdato. Udrullet for tour-de-pologne-2026 (7/7 etaper, max afvigelse 3-59 m). **Licens:** vi udtrækker *fakta* (terrænets højde langs en offentlig vej) og viser aldrig kildebilledet — samme skelnen som `aso_roadbook_agent.py`. Ejeren godkendte fremgangsmåden 2026-08-02.

**Vigtigt:** `stage_pcs_agent.py`'s `save_stages()` udelader `elevation_image_url` fra sin upsert-payload i **to** tilfælde:

1. **når PCS ikke fandt et billede den kørsel** — ellers ville `Prefer: resolution=merge-duplicates` nulstille et allerede sat billede (fx et `stage_profile_generator.py`-genereret) til NULL, hver gang etapen re-scrapes uden held (samme klasse fejl som STG-007's `--overwrite`-regression i climbfinder_agent.py);
2. **når etapen har `elevation_image_source='generated'`** (`strip_generated_image_urls()`) — ellers erstatter PCS-URL'en vores eget PNG, mens `source` bliver stående på `'generated'`, og da frontenden gater på `source === "generated"` (LEG-001), vises et PCS-billede som vores eget. PCS svarer 403 på hotlinks, så billedet kan slet ikke indlæses. Det ramte 20 af 21 Vuelta 2026-etaper (STG-030).

**Regel for alle agenter:** `elevation_image_url` og `elevation_image_source` hører sammen — skriv aldrig den ene uden at forholde dig til den anden. Samme fejl er nu fundet fem gange (STG-029, STG-030); `pcs_profile_image_agent.py` og `stage_pcs_agent.py` har hver sin guard mod den.

---

## Datakilde-dækning (og hvad man gør, når den mangler)

Vores stignings- og profildata står og falder med **to eksterne kilder**, og de dækker ikke alle løb:

1. **PCS** — klatredata (`gpx_climb_agent.py`) og profilbilleder. Dækker de fleste løb, men ofte først tæt på løbsstart for mindre WorldTour-løb.

   **Vigtigt (fundet 2026-08-02/03):** PCS' klatredata står **ikke som tekst** nogen steder — hverken på etapens hovedside eller på `/info/profiles` (verificeret råt med Playwright 2026-08-03). Den ligger udelukkende i **billederne** på `/info/profiles`, som ud over hel-etape-profilen har **én profil pr. stigning med gradient-tabel pr. delstrækning** (La Flamme Rouge). `gpx_climb_agent.py`s regex mod hovedsidens HTML kan derfor pr. definition ikke finde dem; vejen er et **vision-pass** (`profile_reader_agent.py`). Agenten opfandt tidligere stigninger i stedet — den fallback er **fjernet 2026-08-03**, så en etape uden verificerbare data nu efterlades tom (`CLAUDE.md` §6). Tjek altid `/info/profiles`-billederne, før et løb erklæres for udækket: `elevation_image_agent.py:132` besøger allerede siden, men filtrerer `-climb`-billederne fra.
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

## Pipeline-dashboard (`/admin/pipelines`)

Overblik over hvad der er kørt, hvor gammelt det er, hvor fuldstændigt et løbs data er — og knapper til at starte en agent eller en hel pipeline.

- **Hvorfor en runner på ejerens PC:** agenterne kræver Playwright/Chromium, ClimbFinder-login og lokale GPX-kilder. Railway kører kun `uvicorn api:app`. Knappen i browseren udfører derfor intet selv — den lægger en række i `agent_runs` med `status='queued'`, som `runner.py` henter og udfører. **PC'en skal være tændt, for at en knap gør noget**; ellers ligger jobbet i køen, til runneren starter.
- **`agent_catalog.py`** — det autoritative katalog over, hvad der må køres, og hvilke kommandoer hvert `job_key` svarer til. Ligger i kode, ikke i databasen: runneren skal alligevel have en hardkodet allowlist, og to kilder til sandhed ville komme ud af trit. **Fra nettet kan man kun vælge hvilket forudgodkendt job, hvilket løb og hvilken etape — aldrig hvad der køres.** Indfør aldrig et felt, hvor kommandoen kommer udefra.
  - Et job består af ét eller flere **trin** (én kommando pr. trin), som runneren kører i rækkefølge i den samme kørsel med den samme log. Det er dét, der gør `raesinfo` til én knap i stedet for seks.
  - Hvert trin beskriver selv, hvad det skal have med, når jobbet køres for **hele løbet** (`whole`) og for **én etape** (`stage`). `stage=None` betyder, at trinnet ikke kan afgrænses — det springes over i etape-tilstand i stedet for at køre hele løbet bag ryggen på den, der bevidst valgte én etape.
  - Et job kan pege på andre job_keys i stedet for at gentage deres trin (`fuld_forberedelse` gør det), så kopier ikke kan komme ud af trit.
  - **Jobs (2026-09-09):** `startliste`, `raesinfo` (etapedata → PCS-profilbilleder → egen hel-etape-højdeprofil → stigningsrækker → ASO-roadbook → TV-tider), `stigningsprofiler` (VeloViewer), `rytterstats`, `fuld_forberedelse`, `resultater`, `referater`, `historisk_fortaelling` + de løbsløse `nyheder_rss`, `nyheder_ai`, `tv_tider`, `daglig_pipeline`. `LEGACY_LABELS` holder navnene på de udgåede job, så historikken stadig kan læses.
- **`runner.py`** — startes med `python runner.py` og poller køen hvert 15. sekund. Ét job ad gangen (to tunge Playwright-kørsler samtidig løb tør for hukommelse 2026-09-08). Sender hjerteslag til `runner_status`, så dashboardet kan vise, om et klik reelt bliver udført. Nulstiller ved opstart kørsler, der hang i `running` efter et nedbrud. Et trin, der fejler, stopper ikke de øvrige — kørslens exitkode bliver den første fejl, og loggen slutter med en trin-for-trin-oversigt.
- **Fortryd og afbryd:** et klik sætter `agent_runs.not_before = now() + 30 sek` (`CANCEL_WINDOW_SECONDS` i `api.py`), og runneren tager ikke jobbet før da. Uden det ville et klik, der ramte lige før runnerens poll, allerede skrive i databasen, inden man nåede at fortryde. **I køen** sætter Afbryd `status='cancelled'` med det samme, og intet er ændret. **Under kørslen** sætter Afbryd `cancel_requested`; runneren læser flaget hvert 5. sekund og dræber processen med hele dens træ (`taskkill /F /T` — Playwright starter Chromium som barneproces, og den ville ellers leve videre). Det, en afbrudt kørsel allerede nåede at gemme, bliver stående.
- **`race_completeness.py`** — beregner fuldstændighed pr. løb ud fra databasen. Hvert tjek svarer `ok`, `mangler` eller **`ikke_muligt`**. Den tredje tilstand er afgørende: uden den ville en aflyst etape stå som et permanent rødt kryds, man lærer at ignorere. `ikke_muligt` trækker ikke ned i procenten. Kolonnen `stages.data_status` markerer de etaper (`cancelled`/`shortened`/`no_result`), og `results_agent.py` sætter den selv, når PCS skriver, at etapen er aflyst.
- **`run_validator.py`** — efter hver kørsel: tag før/efter-billede af de tjek, jobbet skulle udbedre, og lad Claude (haiku) dømme `ok`/`advarsel`/`fejl` med én sætning. **Exitkode 0 betyder ikke, at data er rigtigt** — `tv_agent.py` sluttede 2026-09-09 med exit 0 efter at have fundet 11 programmer og gemt nul. Deterministiske signaler (exitkode, traceback) afgøres i koden; modellen må skærpe dommen, aldrig blødgøre den.
- **Endpoints:** `/admin/pipelines/{jobs,runner,races,races/{slug},run,runs,runs/{id}}` og `POST /admin/pipelines/runs/{id}/cancel` i `api.py`, alle bag `x-admin-key`. `races/{slug}` leverer også `stages[]` til etape-dropdownen, så omfangsvælgeren altid viser de etaper, der faktisk står i databasen.

---

## Etapereferater (PCS LiveStats)

- **`agents/stage_recap_agent.py`** — skriver `stages.stage_recap`: et kort dansk referat af, hvordan en kørt etape forløb. Kilde er PCS' LiveStats-tidslinje på `…/race/<løb>/<år>/stage-N/live`.
- **Hele tidslinjen:** live-siden viser kun de ~30 nyeste hændelser. Knappen "view more events" (`a.ViewFullTimeline[data-last_seqnr]`) kalder `POST /rce/livestats_viewmore5b.php` med `{action: timeline, race: <var id på siden>, seqnr: <last_seqnr>}` og får resten som rå `<li>`-HTML. Agenten kalder samme endpoint direkte — ingen browser nødvendig.
- **Støjfiltrering:** ~80% af tidslinjen er PCS-statistikwidgets. De kendes strukturelt på `<table>`, `div.chartCont`, `div.bar-cont` eller `div.infoSnippet`; rene løbshændelser har kun tekst. Kun fire tabeltyper slipper igennem (gruppesammensætning, spurtresultater, foreløbigt resultat, klassement efter etapen).
- **Copyright (`CLAUDE.md` §7):** PCS-teksten bruges kun som faktagrundlag. Referatet skrives på ny på dansk via Anthropic API, og kildeteksten gemmes aldrig i databasen.
- **Aflyste etaper:** mangler etaperesultat (fx Vuelta 2026 E3, afbrudt i uvejr) skrives referatet alligevel, med eksplicit besked til modellen om ikke at nævne en vinder.

---

## Øvrige domæner (indeks ud fra filnavne — bekræft gerne detaljer)

- **Ryttere:** `startlist_agent.py`, `rider_photo_agent.py` (**ude af drift 2026-09-09** — vi må ikke bruge PCS' rytterfotos; filen ligger stadig på disken, men er ude af kataloget, ude af `race_prep_pipeline.py` og ude af fuldstændighedstjekket), `fix_rider_photos.py`, `rider_stats_agent.py`, `rider_speciality_agent.py`, `hometown_agent.py`, `local_favorite_agent.py`.
- **Resultater:** `results_agent.py`, `giro_results_agent.py`, `historical_results_agent.py`, `run_results.py`.
- **Etapereferater:** `agents/stage_recap_agent.py` (kørte etaper, PCS LiveStats → `stages.stage_recap`), `agents/historic_recap_agent.py` (historiske løb, TourTracker → `stages.historic_recap`).
- **Løb:** `race_agent.py`, `race_description_agent.py`, `historical_race_agent.py`, `read_races.py`.
- **Nyheder:** `news_agent.py`, `news_publisher_agent.py`, `ai_news_processor.py`, `rss_news_scraper.py`.
- **Social/marketing:** `social_agent.py`, `facebook_auth.py`, `fb_article_image.py`, `fb_branding.py`, `instagram_*` (auth, carousel, pinned, image, post), `brand_logo.py`, `image_generator.py`, `intro_content.py`.
- **Kort/billeder:** `mapillary_agent.py`, `elevation_image_agent.py`.

---

## Sikkerhed (skal rettes)

- `climbfinder_agent.py` indeholder p.t. et **hardkodet ClimbFinder-login** i klartekst. Flyt det til miljøvariabler (fx `CF_EMAIL`, `CF_PASSWORD`) og skift passwordet.
- Gennemgå alle scripts for andre hardkodede nøgler. Intet følsomt må committes til repoet eller indgå i en agent-fil.
