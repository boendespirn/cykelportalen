# klassementet.dk — Arkitektur og pipelines

Dette er **kortet** over den eksisterende kodebase: hvilke pipelines findes, hvad gør de, og hvor ligger de. Agenterne bruger det til at finde deres værktøj.

**Princip:** Hver kørsel starter fra en frisk klon. Agenter læser den **faktiske kode** på hver kørsel (så de altid bruger nyeste version) — dette kort er bare indekset, der peger dem hen til den rigtige fil. Hardkodér aldrig pipeline-logik ind i agent-filerne; peg på scriptet i stedet.

Alle scripts ligger i `agents/`. Hemmeligheder hører hjemme i miljøvariabler — **aldrig** i koden (se sikkerhedsnoten til sidst).

---

## Backend og data

- **`api.py`** — FastAPI-backend.
- **Supabase** — database (bl.a. tabellen `stage_climbs`) og Storage (profil-/højdebilleder).

## Orkestrering

- **`race_prep_pipeline.py RACE-SLUG`** — gør et løb klar til publikation i 6 trin: 1) startliste, 2) etapedata + profilbilleder, 3) høj-kvalitets profiler, 4) rytterbilleder, 5) rytterstats, 6) stigningsprofiler (ClimbFinder).
- **`daily_update.py`** — dagligt: startlister (løb der starter inden for 90 dage), etaper (løb uden etapedata), re-sync af manglende billeder, og noterer hvilke resultat-agenter der bør køres for igangværende løb.
- **`weekly_update.py`** — ugentligt: UCI-ranglister for alle ryttere.

---

## Stignings-/profil-pipeline (kerne for stigningsagenten)

Dataflow for korrekte stigningsprofiler:

1. **`stage_pcs_agent.py PCS-SLUG`** — scraper etapedata fra ProCyclingStats (Playwright, pga. Cloudflare).
2. **`gpx_climb_agent.py --race SLUG [--stage N | --all]`** — henter klatreinfo fra PCS og genererer `gradient_sections` i `stage_climbs`.
3. **`profile_reader_agent.py --race SLUG [--stage N | --all]`** — bruger **Claude vision** til at aflæse de rigtige klatredata fra højdeprofil-billedet (navn, km fra start, længde, gradient, kategori), erstatter syntetiske data, og kører ClimbFinder-søgning pr. klatrenavn.
4. **`climbfinder_agent.py --race SLUG [--stage N] [--all] [--overwrite]`** — finder CF-profilbilledet og gemmer `profile_image_url`. **Verificerer** CF-metrics (længde, finishElevation, gradient) mod DB-data og afviser forkerte match automatisk. Fallback: beregner summit-koordinater fra route_points og reverse-geokoder (Nominatim) → nyt søgeterm. Indeholder `SEARCH_OVERRIDES` (manuelle navne-rettelser; `None` = spring over) og `CLIMB_PREFIXES`.
5. **`climb_region_agent.py --race SLUG`** — klassificerer `stage_climbs.region` via ét Claude-kald.
6. **`elevation_image_agent.py [--race SLUG]`** — downloader højdeprofil-billeder fra PCS (Playwright) og gemmer i Supabase Storage.

Relaterede: `gpx_agent.py`, `pcs_profile_image_agent.py`, `giro_profile_agent.py`.

---

## SEO / Search Console

- **`agents/gsc_agent.py`** — henter Search Console-data (performance pr. søgeord/side, sitemap-status, URL Inspection) via service account (`GSC_SERVICE_ACCOUNT_JSON` + `GSC_SITE_URL` i Railway). Finder striking-distance-søgeord (plads 4-20) og lav-CTR-sider til SEO-agenten. Kræver at service account-emailen er tilføjet som bruger i Search Console → Indstillinger → Brugere og tilladelser.
- **IndexNow** — `submit_indexnow()` i `api.py` POST'er til `api.indexnow.org` som baggrundsopgave, når en artikel godkendes (`/admin/articles/{id}/approve`). Nøglefil: `cykel-frontend/public/1a5a3688cfd86781c40cef01ce453403.txt` (offentlig, ikke hemmelig).
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
