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
| STG-001 | HØJ | NY | stigningsagent | Climbfinder-bugs: forkerte/manglende stigningsprofiler. **Prioritér Tour de France før 4. juli.** |
| SEO-001 | HØJ | NY | seo-agent | Google indekserer ikke siden (vurderes ikke vigtig nok). Native sitemap + intern linking + on-page-struktur + GSC-tilslutning. |
| SEO-002 | MIDDEL | LØST | seo-agent | Sitemap indsendt til GSC (✓). Service account virker og henter rigtige data (testkørt 2026-07-03). |
| MKT-001 | LAV | HENLAGT | ejer | TikTok auto-post uden API for risikabelt (account-ban). Afventer officiel TikTok Content Posting API-adgang. |
| SEO-003 | HØJ | LØST | seo-agent | Canonical URL (`alternates.canonical`) tilføjet 2026-07-03 til alle fem `generateMetadata`-funktioner (race, stage, rider, team, artikel), med bevaret RSS `alternates.types`. Build + typecheck verificeret grønt. |
| SEO-004 | HØJ | LØST | seo-agent | `BreadcrumbList` JSON-LD tilføjet 2026-07-03 på etapesider (`/[slug]/stage/[n]/page.tsx`): Klassementet → løb → etape. Typecheck grønt. |
| SEO-005 | MIDDEL | LØST | seo-agent | Verificeret 2026-07-03: `Person` JSON-LD var allerede implementeret på rytterprofiler (`/riders/[slug]/page.tsx`) i en tidligere kørsel — blot ikke markeret som løst. |
| SEO-006 | HØJ | NY | seo-agent | Forbedrede, keyword-målrettede meta-beskrivelser på løbsider — start med Tour de France. |
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
