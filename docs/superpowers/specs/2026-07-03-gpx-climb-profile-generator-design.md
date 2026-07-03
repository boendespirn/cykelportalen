# GPX-baseret stigningsprofil-generator — design

Dato: 2026-07-03
Status: Godkendt af ejer, klar til implementeringsplan.

## Baggrund og problem

`stage_climbs.profile_image_url` afhænger i dag udelukkende af, at `climbfinder_agent.py` finder og verificerer et matchende billede på ClimbFinder. Når intet verificeret match findes (fx pga. STG-004: strammere verifikationstolerancer clearede flere forkerte matches), viser stigningen intet visuelt profil-kort overhovedet — `ClimbProfile.tsx`'s `hasVisualProfile()` kræver enten `profile_image_url` eller ikke-tomme `gradient_sections`, og `gradient_sections` er i praksis altid `NULL` (STG-003: `profile_reader_agent.py` sætter det aldrig).

Test-case: Tour de France 2026, etape 2 (Tarragona → Barcelona). 4 stigninger, hvoraf 2 (Côte de Begues, Côte de l'Estadi Olímpic) mangler helt et profilbillede efter STG-004-oprydningen.

## Mål

Generér vores egne stigningsprofil-billeder direkte fra GPX-højdedata, stilistisk inspireret af ClimbFinder (terrænsilhuet delt i 10 farvede sektioner efter hældning), som fallback når intet verificeret ClimbFinder-match findes.

## Datagrundlag (verificeret under design)

- Rå GPX-filer fra cyclingstage.com indeholder fuld opløsning `<ele>`-højdedata (bekræftet: 5.043 punkter for TdF 2026 etape 2, ~35 m mellem punkter). Den eksisterende `gpx_agent.py` smider højde væk og gemmer kun lat/lon, downsamplet til 400 punkter for hele etapen — utilstrækkeligt til stigningsniveau-detalje. Den nye generator henter og parser derfor GPX'en direkte, uafhængigt af `stages.route_points`.
- GPX'ens egen kumulative distance (178,8 km for etape 2) matcher ikke den officielle etapedistance (168,5 km) pga. GPS-støj i sving. `km_from_start`/`length_km` (fra `stage_climbs`, sat af `profile_reader_agent.py`'s Claude-vision-aflæsning) er kalibreret til den officielle distance og kan derfor ikke bruges som absolut opslag i GPX'ens distance-rum.
- Pillow er allerede projektafhængighed (bruges af `image_generator.py`, `fb_article_image.py` m.fl.) — ingen nye dependencies nødvendige.
- ClimbFinders eget farveskema blev pixel-samplet fra to referencebilleder (moderat + stejl stigning) til kalibrering, men brugerens egen spec (hvid→rød→mørkerød→sort) er den autoritative kilde til vores farveskala, ikke et pixel-for-pixel match af CF.

## Arkitektur

Nyt script: `agents/climb_profile_generator.py`, som et supplement (ikke erstatning) til den eksisterende stignings-pipeline (`stage_pcs_agent.py` → `gpx_climb_agent.py` → `profile_reader_agent.py` → `climbfinder_agent.py` → `climb_region_agent.py` → `elevation_image_agent.py`, jf. `ARKITEKTUR.md`). Det er fallback-generatoren, der kører efter `climbfinder_agent.py` for stigninger uden verificeret match.

Flow pr. stigning:

1. Hent etapens rå GPX (samme cyclingstage.com-kilde som `gpx_agent.py`), parse `<ele>` sammen med lat/lon — ingen downsampling.
2. Lokalisér stigningens segment i GPX-sporet via proportional position: `start_fraction = km_from_start / stage.distance_km`, mappet ind i GPX'ens egen kumulative distance-rum. `length_km` bruges til at afgrænse segmentets slutning, tilsvarende proportionalt skaleret.
3. Valider slicet: sammenlign udledt højdemeter/gennemsnitshældning fra GPX-segmentet mod DB'ens `elevation_m`/`avg_gradient` (samme ånd som `climbfinder_agent.py`'s `metrics_ok()`). Uden for tolerance → flag og spring over i stedet for at generere et forkert billede (jf. CLAUDE.md §7: udgiv aldrig uverificeret data).
4. Del segmentet i 10 lige lange (efter distance) sektioner, beregn gennemsnitshældning pr. sektion. Korte stigninger (<1 km, få GPX-punkter) interpoleres/udglattes for at undgå støjede sektionsgrænser.
5. Render PNG (Pillow), mørkt tema, i to stilvarianter (se nedenfor).
6. Upload til Supabase Storage (`stage-profiles`-bucket, sti `generated/{climb_id}.png` for produktion, `test/{climb_id}-{variant}.png` for testkørslen).
7. Patch `stage_climbs.profile_image_url` (samme felt som ClimbFinder bruger — ingen frontend-ændringer nødvendige) og sæt `source = "generated"` til sporbarhed.

## Farveskala (gradient → farve)

Kontinuerlig, stykkevis-lineær interpolation mellem kontrolpunkter:

| Hældning | Farve |
|---|---|
| 0% | hvid `#FFFFFF` |
| 4% | lys rav `#FDE0A6` |
| 7% | orange `#F5943C` |
| 10% | rød `#D62828` |
| 13% | mørkerød `#7A0C1E` |
| 15%+ | sort `#0A0A0A` |

Hældning under 0% (lokale dyk) flades til 0%-hvid — der er ingen separat "nedkørsel/fladt"-gråtone som hos ClimbFinder, da billedet kun dækker selve stigningssegmentet.

## Rendering — to stilvarianter

Fælles: mørk baggrund (matcher sitets `slate-950`/`slate-900`), lys/hvid tekst og akselinjer, kontinuerligt farvet terrænsilhuet (ikke søjler) i samme opløsning som ClimbFinders billeder (2400×1200), så eksisterende `<img>`/lightbox-UI i `ClimbProfile.tsx` fungerer uændret.

- **Fuldt sæt**: titel (stigningsnavn + længde/gns.-hældning), y-akse højdemeter-gitterlinjer, x-akse km-markører, %-label pr. sektion, start-/tophøjde i meter, "klassementet.dk"-brandmærke.
- **Minimalt**: kun den farvede terrænkurve + start-/tophøjde. Ingen akser, ingen %-labels pr. sektion.

## Etape 2-testplan

1. Byg generatoren.
2. Kør for alle 4 etape-2-stigninger i **begge** stilarter → 8 billeder, uploadet til `test/`-stien (ikke patchet ind i `profile_image_url` endnu).
3. Ejeren vurderer og vælger stilart (evt. med tilpasningsønsker).
4. Genkør for etape 2 med den valgte stilart — denne gang patches `profile_image_url` for rigtigt, men **kun** for stigninger uden verificeret ClimbFinder-match (Côte de Begues, Côte de l'Estadi Olímpic). De to stigninger med allerede-verificerede CF-billeder (Santa Creu d'Olorda, Castell de Montjuïc) overskrives ikke, medmindre ejeren beder om det.

## Ikke i scope for denne omgang

- Rollout til andre etaper/løb end TdF 2026 etape 2 — afventer visuel godkendelse af stilarten først.
- Rettelse af STG-003 (`gradient_sections` aldrig sat af `profile_reader_agent.py`) — ortogonalt problem, rører ikke ved denne generator.
- Ændringer i `ClimbProfile.tsx` — genbruger eksisterende `profile_image_url`-visning uændret.
