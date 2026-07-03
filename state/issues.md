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
| SEO-002 | MIDDEL | AFVENTER_EJER | ejer | Sitemap indsendt til GSC (✓). Tilbage: opsæt GSC service account så agenten aktivt kan læse og handle på GSC-data (se guide). |
| MKT-001 | LAV | HENLAGT | ejer | TikTok auto-post uden API for risikabelt (account-ban). Afventer officiel TikTok Content Posting API-adgang. |
| SEO-003 | HØJ | NY | seo-agent | Tilføj canonical URL (`alternates.canonical`) til alle fem `generateMetadata`-funktioner (race, stage, rider, team, artikel). |
| SEO-004 | HØJ | NY | seo-agent | Tilføj `BreadcrumbList` JSON-LD på etapesider (`/[slug]/stage/[n]/page.tsx`). |
| SEO-005 | MIDDEL | NY | seo-agent | Tilføj `Person` JSON-LD på rytterprofiler (`/riders/[slug]/page.tsx`). |
| SEO-006 | HØJ | NY | seo-agent | Forbedrede, keyword-målrettede meta-beskrivelser på løbsider — start med Tour de France. |
| SEO-007 | MIDDEL | NY | seo-agent | Implementér IndexNow: nøglefil i `/public/` + POST til `api.indexnow.org` ved artikelpublicering. |
| SEO-008 | MIDDEL | NY | seo-agent | Byg `agents/gsc_agent.py`: henter GSC-performance-data, finder striking-distance-søgeord og lav-CTR-sider, leverer rapport til direktøren. |
| MKT-002 | LAV | NY | marketing-agent | IG-karrusel er daglig (`instagram_carousel_daily.py`); ønskes ugentlig. Kør ugentlig cadence eller justér scriptet. |
| MKT-003 | MIDDEL | NY | marketing-agent | Verificér at FB-linket faktisk lægges i **første kommentar** (ikke i opslaget) i `fb_article_image.py` / `api.py`. |
| MKT-004 | LAV | NY | ejer | Meta Page-token udløber ~hver 60. dag → tilbagevendende re-auth via `facebook_auth.py`. |
| OPS-001 | MIDDEL | AFVENTER_EJER | ejer | Forbind connectorer til routinen: Slack (#direktøren — gjort), Search Console (GSC service account). |
| OPS-002 | MIDDEL | LØST | ejer | Alle routinemiljøvariabler sat i Railway. Løst 2026-06-28. |
| OPS-003 | MIDDEL | AFVENTER_EJER | ejer | Konfigurér routinens netværks-allowlist (Supabase, climbfinder.com, procyclingstats.com, Nominatim, graph.facebook.com, searchconsole.googleapis.com, pagespeedonline.googleapis.com, api.indexnow.org). |
