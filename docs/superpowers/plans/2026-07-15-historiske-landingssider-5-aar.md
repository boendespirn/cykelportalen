# Plan: Færdiggør landingssider for alle løb — indeværende sæson + sidste 5 år

*Oprettet: 2026-07-15. Ejerens direktiv: Google er begyndt at indeksere siden bredt — nu skal den også have noget at vise frem, ikke 404'er. Se `STRATEGI.md` §1a for det formelle mål.*

> **REVIDERET 2026-07-15 (samme dag):** Ejeren har efterfølgende indsnævret
> rækkevidden for **historiske** etapesider (år < indeværende sæson, altså
> hele Fase 2 nedenfor): de skal **ikke** have individuelle stignings-
> profiler. Det var den reelle flaskehals, og sløjfes helt for historiske
> sider — de skal give et overblik, ikke fuld dybde. Se
> `docs/superpowers/specs/2026-07-15-historiske-etapesider-letvaegt.md` for
> den fulde, reviderede sidestruktur (bl.a. tilføjet: AI-genereret historisk
> fortælling for kendte/nyhedsværdige etaper). Fase 0's klimapipeline-
> forudsætning nedenfor gælder derfor **kun** indeværende/kommende sæsoner
> (Fase 1) — ikke historisk backfill (Fase 2-3).

## Baggrund

`7daaf30` (2026-07-10, issue SEO-019) fjernede alle historiske etapesider (år < indeværende sæson) og returnerer nu 404 for dem via `isHistoricRaceSlug()` i `lib/historic-stage.ts`. Beslutningen var korrekt givet det, der var kendt på det tidspunkt: Ahrefs fandt 740+ langsomme sider (TTFB op til 4,7 sek, ~10 ucachede backend-kald pr. side, `getStartlist()` brugte `cache: "no-store"`), ingen af dem havde trafik, og de fleste var ikke indekseret.

Data-audit (2026-07-15) viser et dybere problem: det er ikke kun performance. Sæsonerne 2021-2025 har stort set **intet af det indhold**, der gør en etapeside "færdig" efter jeres egen struktur:

| Årgang | Løb | Etaper | Etaper m. profilbillede | Stigninger | Resultatrækker | Startlisterækker |
|---|---|---|---|---|---|---|
| 2026 | 36 | 115 | 85 | 165 | 1782 | 1103 |
| 2025 | 36 | 143 | **0** | **0** | 142 | **0** |
| 2024 | 35 | 143 | **0** | **0** | 139 | **0** |
| 2023 | 35 | 143 | **0** | **0** | 134 | **0** |
| 2022 | 35 | 126 | **0** | **0** | 110 | **0** |
| 2021 | 35 | 133 | **0** | **0** | 99 | **0** |

~700 historiske etaper på tværs af 176 løb har altså kun skeleton-data (stage-nummer, navn, distance, evt. dato) — ingen stigningsprofiler, ingen højdeprofilbilleder, ingen startlister, og formentlig kun vinder-rækker i `results` (142 rækker / 143 etaper ≈ 1 pr. etape, mod 1782/115 ≈ 15,5 pr. etape i 2026). At bare fjerne 404-guarden ville afsløre tomme/tynde sider, ikke rigtige landingssider — stik imod CLAUDE.md §5 ("ingen tomme artikler").

Yderligere blocker: **ingen af "forberedelses-agenterne" understøtter en årgang i dag.** `startlist_agent.py` har `YEAR = 2026` hardkodet på modulniveau; `race_prep_pipeline.py` arver samme år via `startlist_agent.PCS_TO_DB_SLUG`/`YEAR`. `ARKITEKTUR.md`s omtale af `historical_results_agent.py`/`historical_race_agent.py` er forældet dokumentation — filerne findes ikke i repoet.

## Målet

Samme struktur som Tour de France 2026's allerede-kørte etaper (stigningsprofil, favoritter/startliste, fulde resultater+klassement, TV, kort) skal findes for:
1. **Indeværende sæson (2026)** — alle løb, ikke kun TdF. Højeste prioritet, allerede delvist i gang via stigningsagenten.
2. **De sidste 5 afsluttede sæsoner (2021-2025)** — genopbygget fra bunden, ikke bare "un-404'et".

## Fase 0 — Forudsætninger (skal være på plads FØR nogen historisk side genåbnes)

Uden disse to ting gentager vi nøjagtig SEO-019-fejlen, bare 5× i skala.

1. **Årgang-parameterisér pipeline-scripts.** `startlist_agent.py`, `stage_pcs_agent.py`, `results_agent.py`/`giro_results_agent.py`, og `race_prep_pipeline.py` skal tage løbets årstal (fra DB-slugget, fx `tour-de-france-2023`) i stedet for det hardkodede `YEAR=2026`, så PCS-URL'er peger på det rigtige historiske race-år (PCS-mønster: `procyclingstats.com/race/{slug}/{year}/...`). Verificér samtidig at PCS' historiske resultatside-struktur matcher det, `results_agent.py` netop blev rettet til (RES-004, 2026-07-15) — historiske sider kan sagtens have et andet DOM-mønster end indeværende sæson.
2. **Ret TTFB-roden, ikke bare symptomet:**
   - `getStartlist()` i `[slug]/stage/[n]/page.tsx` bruger `cache: "no-store"` — en afsluttet etapes startliste ændrer sig aldrig. Skift til `next: { revalidate }` med en lang TTL (eller ingen — statisk for altid via `generateStaticParams`).
   - Overvej ét samlet backend-endpoint for etapesiden i stedet for ni parallelle kald (reducerer antal round-trips, ikke kun cache-tid).
   - Historiske (afsluttede) etaper bør have markant længere `revalidate` end de nuværende 300 sek — data er permanent frosset.
3. **Verificér på én testetape** (fx `tour-de-france-2025` etape 1) at TTFB kommer ned i normalt leje, før arbejdet skaleres til 700 etaper.

## Fase 1 — Indeværende sæson (2026) færdiggøres først

- **Tour de France 2026** (kører nu, størst trafik): sikr at samtlige 21 etaper har komplet data. Etape 1-5 er allerede afviklet og bør allerede virke (year=2026 rammer ikke `isHistoricRaceSlug()`) — kort sanity-tjek af dem er en hurtig, adskilt opgave fra selve historik-sporet. Kendte åbne huller: STG-016/017/018 (gradient-verificering), STG-021 (VeloViewer for etape 1-4, 15-17, 19-21, blokeret af Stravas daglige read-loft).
- **Øvrige 35 løb i 2026** der allerede er kørt i år (Tour Down Under, UAE Tour, Strade Bianche, Milano-Sanremo, Paris-Nice, Ronde van Vlaanderen, Paris-Roubaix, Amstel Gold, Liège, Giro d'Italia hvis relevant, osv.): kør `race_prep_pipeline.py` for hver for at få samme dybde som TdF.

## Fase 2 — Historisk backfill, 2021-2025 (176 løb, ~700 etaper)

Prioriteret efter søgeværdi (CLAUDE.md §9: trafik/autoritet før "kun det vigtige" — store løb med lav etape-mængde er billigst at gøre først):

1. **Tour de France 2021-2025** (5 løb, ~105 etaper) — north star-søgeordet selv. Absolut højst.
2. **Giro d'Italia + Vuelta a España 2021-2025** (10 løb, ~210 etaper) — de øvrige to grand tours.
3. **De 5 Monuments** (Milano-Sanremo, Ronde van Vlaanderen, Paris-Roubaix, Liège-Bastogne-Liège, Il Lombardia) × 5 år (25 løb, ~25 etaper — étdagsløb, hurtige) — højt søgevolumen for etape-mængden.
4. **Øvrige WorldTour-etapeløb** (Paris-Nice, Tirreno-Adriatico, Critérium du Dauphiné, Tour de Suisse, Volta a Catalunya, UAE Tour, Tour de Romandie, Tour de Pologne m.fl.) × 5 år.
5. **Resterende étdagsløb** (Strade Bianche, Amstel Gold, Flèche Wallonne, E3, Gent-Wevelgem, Bretagne Classic, Cyclassics, GP Montréal/Québec, Tour of Guangxi m.fl.) × 5 år.

**Reviderede trin pr. løb (letvægt, jf. spec 2026-07-15-historiske-etapesider-letvaegt.md)** —
ikke længere alle 9 trin i `race_prep_pipeline.py`, kun de trin der understøtter
den reviderede sidestruktur:
1. Startliste (PCS har fulde historiske startlister)
2. Etapedata + hel-etape-profilbilleder (trin 2-3 i pipelinen — **ikke** trin 4-5
   [rytterbilleder/-stats] eller 6-8 [individuelle stigningsprofiler] — sløjfes
   bevidst for historiske sider)
3. Fulde resultater + endeligt klassement (trin 9, `--all-stages`)
4. **Nyt:** historisk fortælling — AI-genereret narrativ for kendte/
   nyhedsværdige etaper, skrevet til nyt felt `stages.historic_recap`.
   Afventer ejerens svar på kildegrundlag og "kendt/nyhedsværdig"-kriterium
   (se spec-dokumentet) før dette trin kan bygges.

*(Den oprindelige 9-trins-liste med stigningsprofiler gælder fortsat for
indeværende/kommende sæsoner, Fase 1 ovenfor — ikke for historisk backfill.)*

## Fase 3 — Genåbn siderne (kun for løb med reelt komplet data)

- Erstat den blanke årstals-check i `isHistoricRaceSlug()` med et reelt datafuldstændigheds-tjek — for historiske sider nu: `stages.distance_km`/`elevation_image_url` (hel-etape) sat + startliste + resultater til stede (**ikke** `stage_climbs`, som bevidst ikke findes for historiske sider jf. revisionen ovenfor). Undgå at genåbne en side, der stadig kun har skeleton-data. Et løb bør kun blive linket/indekseret, når det er færdigt efter den (reviderede, lettere) definition.
- Lang `revalidate` for afsluttede løb (de ændrer sig aldrig — ugentlig eller statisk).
- Geninsæt intern linking, som SEO-019 fjernede: rytter-palmares, løbssidens etapeliste, stignings-søgeresultater.
- Medtag i `sitemap.ts` igen for løb med verificeret komplet data.
- IndexNow-submit + evt. samlet GSC "anmod om indeksering" for de først-færdige (TdF-årene).

## Fase 4 — Løbende kvalitetskontrol

- Kontrolagenten stikprøvetjekker et repræsentativt udsnit mod PCS/eksterne kilder (samme metode som STG-016/017/018) — 700 nye sider kan ikke alle tjekkes, men TdF-årene bør tjekkes 100%, øvrige stikprøvevis.

## Omfang / realistisk tempo

~176 løb × 7 pipeline-trin. Playwright-scraping er langsomt (ét løb ad gangen realistisk), og eksterne kilder er rate-limited (Strava 1000 kald/dag, jf. STG-021; ClimbFinder login-rate). Dette er dage-til-uger, ikke én session — bedst kørt som en fortsat, tildelt baggrundsproces (fx N løb pr. dag/kørsel), i samme stil som `daily_update.py`.

## Relateret / afhænger af

- **OPS-011** (Vercel `/_next/image` 402): ejeren melder Vercel Pro-opgradering løst dette (2026-07-15) — bør verificeres og lukkes, da hundredvis af genoprettede sider med rytterfotos ellers rammer samme fejl.
- **STG-021**: VeloViewer-backfill for resten af TdF 2026 er allerede i gang og bør færdiggøres inden det samme mønster skaleres til 5 års historik.
