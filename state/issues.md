# issues.md — fejl- og opgavelog

Den eneste kilde til sandhed for problemer og opgaver på tværs af kørsler (jf. `PROTOKOL.md`). Direktøren er eneste skriver. Hver kørsel læses denne fil først.

**Statusser:** `NY → TILDELT → ESKALERET → AFVENTER_EJER → LØST` (samt `HENLAGT`).
**Prioritet:** HØJ / MIDDEL / LAV.

Direktøren udvider hvert issue med dato, forsøg og løsning, efterhånden som der arbejdes.

| ID | Prioritet | Status | Ansvarlig | Beskrivelse |
|----|-----------|--------|-----------|-------------|
| SIK-001 | HØJ | LØST | ejer | Hardkodet CF-login flyttet til `os.getenv(CF_EMAIL/CF_PASSWORD)` i koden; ejer har skiftet password og sat env vars i Railway. Løst 2026-06-28. |
| SIK-002 | HØJ | LØST | ejer | Alle eksponerede nøgler/tokens roteret og opdateret i Railway. Løst 2026-06-28. |
| SIK-003 | MIDDEL | NY | kontrolagent | Audit alle scripts i `agents/` for andre hardkodede nøgler eller hemmeligheder. |
| STG-001 | HØJ | LØST | stigningsagent | To rod-bugs fundet og rettet 2026-07-03 for tour-de-france-2026: (1) `stage_pcs_agent.py` valgte blindt første `/profiles/`-billede på PCS-siden — greb ofte rutekort/mål-zoom i stedet for højdeprofilen (ramte etape 1, 2, 3, 12). Rettet med filnavns-filter. (2) `climbfinder_agent.py` ryddede aldrig gamle forkerte billede-matches, når en klatring senere fik `SEARCH_OVERRIDES[navn]=None` — 10 stigninger viste billeder fra helt andre bjerge/lande (fx Côte de Larringes viste et billede fra Pau). Tilføjet `clear_stale_override_images()`. Genkørt + verificeret: 20/21 etaper har nu korrekt højdeprofil, 61/72 stigninger har verificeret ClimbFinder-billede. Se STG-002 og STG-003 for reststoffer. |
| STG-002 | MIDDEL | NY | research-agent | Etape 3 (tour-de-france-2026, Granollers–Les Angles) har ingen hel-etape-højdeprofil — bekræftet ægte PCS-kildedata-mangel, ikke en bug. Nuværende frontend-fallback viser i stedet automatisk første stignings egen profil. Overvej at generere eget elevationsdiagram fra `route_points`/GPX i stedet for at være afhængig af PCS's billede. |
| STG-003 | MIDDEL | NY | stigningsagent | `gradient_sections` er `NULL` for samtlige stigninger i hele databasen (ikke kun TdF) — `gpx_climb_agent.py` sætter feltet ved indsættelse, men `profile_reader_agent.py` nulstiller/sætter det aldrig, når det senere erstatter synthetiske data med Claude-vision-data. Konsekvens: de 11 TdF-stigninger uden ClimbFinder-billede har slet ingen visuel profil-fane (ingen fallback-diagram). |
| OPS-005 | LAV | LØST | direktør | `elevation_image_agent.py` fandtes ikke i git-historikken — kun uncommitted i ejerens arbejdsmappe, med reel risiko for at gå tabt. Committet 2026-07-03 (fundet og reddet af stigningsagenten under STG-001-arbejde). Bemærk: `agents/`-mappen indeholder stadig en rod af dobbelt-scripts (rod + `agents/*.py` + `agents/* - Kopi.py`); bør ryddes op på et tidspunkt, men er bevidst ikke rørt for at undgå at introducere fejl uden for scope. |
| SEO-001 | HØJ | NY | seo-agent | Google indekserer ikke siden (vurderes ikke vigtig nok). Native sitemap + intern linking + on-page-struktur + GSC-tilslutning. |
| SEO-002 | MIDDEL | LØST | seo-agent | Sitemap indsendt til GSC (✓). Service account virker og henter rigtige data (testkørt 2026-07-03). |
| MKT-001 | LAV | HENLAGT | ejer | TikTok auto-post uden API for risikabelt (account-ban). Afventer officiel TikTok Content Posting API-adgang. |
| SEO-003 | HØJ | LØST | seo-agent | Canonical URL (`alternates.canonical`) tilføjet 2026-07-03 til alle fem `generateMetadata`-funktioner (race, stage, rider, team, artikel), med bevaret RSS `alternates.types`. Build + typecheck verificeret grønt. |
| SEO-004 | HØJ | LØST | seo-agent | `BreadcrumbList` JSON-LD tilføjet 2026-07-03 på etapesider (`/[slug]/stage/[n]/page.tsx`): Klassementet → løb → etape. Typecheck grønt. |
| SEO-005 | MIDDEL | LØST | seo-agent | Verificeret 2026-07-03: `Person` JSON-LD var allerede implementeret på rytterprofiler (`/riders/[slug]/page.tsx`) i en tidligere kørsel — blot ikke markeret som løst. |
| SEO-006 | HØJ | LØST | seo-agent | Meta-beskrivelser på løbsider (`/[slug]/page.tsx`) opdateret 2026-07-03: inkluderer nu datointerval, etape-antal (nøgleord "etaper" — matcher north star), og gren-specifik tekst for endagsløb vs. etapeløb. Gælder alle løb, inkl. Tour de France. Build + typecheck grønt. |
| SEO-007 | MIDDEL | LØST | seo-agent | IndexNow implementeret 2026-07-03: nøglefil i `cykel-frontend/public/`, `submit_indexnow()` i `api.py` kaldes som baggrundsopgave ved artikel-godkendelse (`/admin/articles/{id}/approve`). Nøglen er ikke hemmelig (IndexNow-protokollen kræver offentlig nøglefil). |
| SEO-008 | MIDDEL | LØST | seo-agent | `agents/gsc_agent.py` bygget og testkørt 2026-07-03 med rigtige Railway-credentials (`GSC_SERVICE_ACCOUNT_JSON_B64` + `GSC_PROPERTY_URL=sc-domain:klassementet.dk`). Fandt reelle data: kun 10 sider med søgeeksponeringer sidste 28 dage, TDF-siden ranker pos. 25.7 med 0% CTR. |
| SEO-009 | HØJ | LØST | direktør | **Soft-404 rettet på alle 6 dynamiske sidetyper** (løb, etape, hold, rytter, artikel, advertorial): manglende indhold returnerede HTTP 200 med "ikke fundet"-tekst i stedet for rigtig 404. Fundet via GSC-rapport: en ugyldig URL (`tour-de-france-løb`, ingen matchende race i DB) var indekseret og konkurrerede mod den rigtige TDF-side. Rettet 2026-07-03 med `notFound()` fra `next/navigation` på alle 6 sider. Build + typecheck grønt. |
| MKT-002 | LAV | NY | marketing-agent | IG-karrusel er daglig (`instagram_carousel_daily.py`); ønskes ugentlig. Kør ugentlig cadence eller justér scriptet. |
| MKT-003 | MIDDEL | NY | marketing-agent | Verificér at FB-linket faktisk lægges i **første kommentar** (ikke i opslaget) i `fb_article_image.py` / `api.py`. |
| MKT-004 | LAV | NY | ejer | Meta Page-token udløber ~hver 60. dag → tilbagevendende re-auth via `facebook_auth.py`. |
| OPS-001 | MIDDEL | LØST | seo-agent | Forbind connectorer til routinen: Slack (#direktøren — gjort), Search Console (GSC service account testkørt succesfuldt 2026-07-03 med rigtige credentials). |
| OPS-002 | MIDDEL | LØST | ejer | Alle routinemiljøvariabler sat i Railway. Løst 2026-06-28. |
| OPS-003 | MIDDEL | AFVENTER_EJER | ejer | Konfigurér routinens netværks-allowlist (Supabase, climbfinder.com, procyclingstats.com, Nominatim, graph.facebook.com, searchconsole.googleapis.com, pagespeedonline.googleapis.com, api.indexnow.org). |
| OPS-004 | LAV | LØST | direktør | Opgave-dashboard bygget 2026-07-03: `GET /admin/issues` i `api.py` parser denne fil til JSON, vist som Kanban-board på `klassementet.dk/admin/opgaver` (grupperet efter status, farvet efter prioritet, viser ansvarlig). Build + typecheck verificeret grønt. |
