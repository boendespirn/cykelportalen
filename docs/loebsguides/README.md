# Løbsguider — hvor dataen kommer fra, løb for løb

Formålet er ét: **næste sæson skal ikke begynde forfra.** Hver fil i denne mappe
beskriver ét løb — hvilket slug kilderne kender det under, hvilke kilder der
faktisk leverede data i 2026, hvad der manglede, og hvornår de enkelte jobs skal
køre. Filerne er skrevet 2026-10-12/13 ud fra databasen og en rå kontrol af hver
eneste PCS-URL.

Læs denne fil først. Den rummer metoden og de fælder, der går igen; løbsfilerne
rummer kun det, der er særligt for dét løb.

---

## 1. Kildematrix — hvem leverer hvad

| Data | Kilde | Agent | Kan den fejle tavst? |
|---|---|---|---|
| Startliste | PCS `/race/<slug>/<år>/startlist` | `startlist_agent.py` | **Ja** — ukendt slug giver tom liste uden fejl |
| Etapedata (rute, distance, højdemeter) | PCS `/race/<slug>/<år>/stage-N` — for endagsløb løbets **forside** | `stage_pcs_agent.py` | **Ja** — forsiden har anden markup end etapesiderne (DATA-005) |
| GPX-rute | cyclingstage: dedikeret side, fælles index eller løbets rute-underside | `gpx_agent.py`, `climb_profile_generator` | Nej — manglende konfiguration meldes |
| Stigninger | PCS' `-climb`-billeder på `/info/profiles`, læst med vision og verificeret mod GPX | `climb_vision_agent.py` | Nej — hver stigning kontrolleres mod GPX |
| Stigningsprofil | Egen tegning fra GPX (Stravas segment-API er lukket, STG-033) | `climb_profile_generator` | Nej |
| Hel-etape-profil | Egen tegning fra GPX, med stigningerne lagt ovenpå | `stage_profile_generator.py` | Nej, men **rækkefølgen** betyder noget: stigninger først, ellers bliver profilen nøgen |
| Resultat + klassement | PCS `/stage-N/result` (etapeløb) eller `/result` (endagsløb) | `results_agent.py` | **Ja** — tom tabel blev før meldt som "ikke kørt endnu" (RES-006) |
| Etapereferat | PCS LiveStats `/stage-N/live` | `stage_recap_agent.py` | Nej — findes **slet ikke** for endagsløb (RES-008) |
| Samlet ræsreferat | Vores egen database (etapereferaterne) | `race_recap_agent.py` | Nej — kræver 80 % referatdækning |
| TV-tider | cykelkalenderen.dk | `tv_agent.py` | **Ja** — løbet skal stå i `RACE_KEYWORDS`, ellers kasseres sendingen |

## 2. Rækkefølgen — og hvorfor den er sådan

1. **Startliste** — alt andet hænger på rytterne. `results_agent` kan kun gemme
   en placering for en rytter, der findes i `riders`.
2. **Etapedata** — ruten, distancen, start og mål.
3. **GPX** — forudsætningen for både stigningsprofiler og hel-etape-profilen.
4. **Stigninger** (vision + GPX-kontrol) — *før* profilerne tegnes.
5. **Profiler** — stigningsprofiler og derefter hel-etape-profilen, så
   stigningerne kan lægges ovenpå.
6. **TV-tider** — tæt på løbet; de offentliggøres sent.
7. **Resultat og klassement** — efter målstregen, og gentaget til det står der.
8. **Referat** — etapereferat pr. etape, samlet ræsreferat efter sidste etape.

## 3. De fem fælder, der går igen

1. **PCS' løbsforside og etapesider deler ikke markup.** Forsiden bruger
   `div.bold`-labels, etapesiderne `.title`/`.value`, og resultatsiden for et
   endagsløb bruger `div.resultCont` (ental) uden `td.ridername`. En scraper,
   der kun kender den ene form, finder nul felter og fejler tavst (DATA-005,
   RES-006).
2. **PCS skifter slug uden varsel — og svarer med en TOM side, ikke en 404.**
   Kontrollen 2026-10-12/13 fandt fem: `tour-of-flanders` → `ronde-van-vlaanderen`,
   `e3-saxo-bank-classic` → `e3-harelbeke`, `ronde-van-brugge` →
   `classic-brugge-de-panne`, `cadel-evans-great-ocean-road-race` →
   `great-ocean-road-race`, og **hele Dauphinéen**, som PCS nu kalder
   `tour-auvergne-rhone-alpes` (dens etape-URL'er pegede stadig på
   `criterium-du-dauphine` og hentede derfor intet). Dertil `milan-san-remo` og
   `grand-prix-de-quebec`/`-montreal` i `startlist_agent`. Fordi siden er tom og
   ikke en fejl, ser det ud som om løbet ikke er kørt endnu.
3. **Det samme PCS-slug står fire forskellige steder** — `stage_pcs_agent`,
   `startlist_agent`, `tv_agent` og `races.pcs_url` — og de er ikke enige. Det er
   hovedårsagen til, at klassikerne stod uden startliste hele 2026.
4. **Et endagsløb er etape 1.** Løbssiden er dets eneste side (`/stage/1`
   redirecter, SEO-021), så alt, der ellers hørte til en etapeside, skal hentes
   og vises der. Se afsnittet om endagsløb i `ARKITEKTUR.md`.
5. **Det, der ikke bliver trykket på, bliver ikke hentet.** 2026's største hul
   er ikke en teknisk fejl: syv WorldTour-etapeløb står helt uden etaper, og
   Vueltas sidste fire etaper stod uden resultat til 2026-10-13, fordi ingen
   kørte jobbet efter løbets slutning.

**En sjette, fundet 2026-10-13:** *PCS kan lægge hele sin resultat-markup om.*
`#resultsCont` og `td.ridername` findes ikke længere på nogen side. Alle
fanebladers tabeller ligger nu i `div.resultCont`, hvor kun den AKTIVE mangler
klassen `hide`, og kolonnerne identificeres af `data-code` i `<thead>`.
`results_agent.py` er skrevet om til den form (RES-009). Lærestregen: læs
kolonnerne ud af headeren frem for at hardkode indekser, og lad "ingen tabel
fundet" være en fejl, ikke en stilhed.

## 4. Sådan verificerer du en kilde, før sæsonen går i gang

For hvert løb på kalenderen:

1. Hent `https://www.procyclingstats.com/race/<slug>/<år>/result` og tjek, at
   der er en `div.resultCont` med mindst fem rækker. **Tom side = forkert slug**,
   ikke "løbet er ikke kørt".
2. Slå samme slug op i `startlist_agent.PCS_RACE_SLUGS` og
   `stage_pcs_agent.PCS_RACE_SLUGS`. Står løbet der ikke, hentes startlisten
   aldrig.
3. Tjek at `races.pcs_url` i databasen peger på det samme slug.
4. Kør `Datakilde-scan` (`agents/datakilde_scan_agent.py`) — den finder nye
   GPX-kilder og uenigheder mellem PCS' rutedata og vores egen række.

## 5. Statusoversigt 2026

Tallene er fra 2026-10-13, efter resultat-backfillen. "Resultater" tæller etaper
med mindst én placering.

| Løb | Dato | Type | Etaper | Resultater | Startliste | Stigninger | TV |
|---|---|---|---|---|---|---|---|
| [Santos Tour Down Under](santos-tour-down-under.md) | 2026-01-21 | etape | 5 | 5/5 | 0 | 0 | 0 |
| [Mapei Cadel Evans Great Ocean Road Race - Men](mapei-cadel-evans-great-ocean-road-race-men.md) | 2026-02-01 | endags | 1 | 1/1 | 0 | 0 | 0 |
| [UAE Tour](uae-tour.md) | 2026-02-16 | etape | 7 | 7/7 | 146 | 0 | 0 |
| [Omloop Nieuwsblad](omloop-nieuwsblad.md) | 2026-02-28 | endags | 1 | 1/1 | 0 | 0 | 0 |
| [Strade Bianche](strade-bianche.md) | 2026-03-07 | endags | 1 | 1/1 | 0 | 0 | 0 |
| [Paris-Nice](paris-nice.md) | 2026-03-08 | etape | 8 | 7/8 | 0 | 0 | 0 |
| [Tirreno-Adriatico](tirreno-adriatico.md) | 2026-03-09 | etape | 7 | 7/7 | 0 | 0 | 0 |
| [Milano-Sanremo](milano-sanremo.md) | 2026-03-21 | endags | 1 | 1/1 | 0 | 0 | 0 |
| [Volta Ciclista a Catalunya](volta-ciclista-a-catalunya.md) | 2026-03-23 | etape | 7 | 7/7 | 0 | 0 | 0 |
| [Ronde Van Brugge - Tour of Bruges](ronde-van-brugge-tour-of-bruges.md) | 2026-03-25 | endags | 1 | 1/1 | 0 | 0 | 0 |
| [E3 Saxo Classic](e3-saxo-classic.md) | 2026-03-27 | endags | 1 | 1/1 | 0 | 0 | 0 |
| [In Flanders Fields - From Middelkerke to Wevelgem](in-flanders-fields-from-middelkerke-to-wevelgem.md) | 2026-03-29 | endags | 1 | 1/1 | 0 | 0 | 0 |
| [Dwars door Vlaanderen - A travers la Flandre](dwars-door-vlaanderen-a-travers-la-flandre.md) | 2026-04-01 | endags | 1 | 1/1 | 0 | 0 | 0 |
| [Ronde van Vlaanderen](ronde-van-vlaanderen.md) | 2026-04-05 | endags | 1 | 1/1 | 0 | 0 | 0 |
| [Itzulia Basque Country](itzulia-basque-country.md) | 2026-04-06 | etape | 6 | 6/6 | 0 | 0 | 0 |
| [Paris-Roubaix Hauts-de-France](paris-roubaix-hauts-de-france.md) | 2026-04-12 | endags | 1 | 1/1 | 0 | 0 | 0 |
| [Amstel Gold Race](amstel-gold-race.md) | 2026-04-19 | endags | 1 | 1/1 | 0 | 0 | 0 |
| [La Flèche Wallonne](la-fleche-wallonne.md) | 2026-04-22 | endags | 1 | 1/1 | 0 | 0 | 0 |
| [Liège-Bastogne-Liège](liege-bastogne-liege.md) | 2026-04-26 | endags | 1 | 1/1 | 0 | 0 | 0 |
| [Tour de Romandie](tour-de-romandie.md) | 2026-04-29 | etape | 5 | 5/5 | 0 | 0 | 0 |
| [Eschborn-Frankfurt](eschborn-frankfurt.md) | 2026-05-01 | endags | 1 | 1/1 | 0 | 0 | 0 |
| [Giro d'Italia](giro-d-italia.md) | 2026-05-08 | etape | 21 | 21/21 | 184 | 40 | 33 |
| [Tour Auvergne Rhône-Alpes (Critérium du Dauphiné)](criterium-du-dauphine.md) | 2026-06-07 | etape | 8 | 7/8 | 170 | 28 | 26 |
| [Copenhagen Sprint](copenhagen-sprint.md) | 2026-06-14 | endags | 1 | 1/1 | 198 | 0 | 0 |
| [Tour de Suisse](tour-de-suisse.md) | 2026-06-17 | etape | 5 | 5/5 | 140 | 9 | 14 |
| [Tour de France](tour-de-france.md) | 2026-07-04 | etape | 21 | 21/21 | 184 | 88 | 67 |
| [DSSK (Donostia San Sebastian Klasikoa)](dssk-donostia-san-sebastian-klasikoa.md) | 2026-08-01 | endags | 1 | 1/1 | 176 | 0 | 0 |
| [Tour de Pologne](tour-de-pologne.md) | 2026-08-03 | etape | 7 | 7/7 | 116 | 13 | 0 |
| [ADAC Cyclassics](adac-cyclassics.md) | 2026-08-16 | endags | 1 | 1/1 | 5 | 0 | 0 |
| [Renewi Tour](renewi-tour.md) | 2026-08-19 | etape | 5 | 5/5 | 9 | 0 | 0 |
| [La Vuelta Ciclista a España](la-vuelta-ciclista-a-espana.md) | 2026-08-22 | etape | 21 | 20/21 | 179 | 58 | 0 |
| [Bretagne Classic - CIC](bretagne-classic-cic.md) | 2026-08-30 | endags | 1 | 1/1 | 6 | 0 | 0 |
| [Grand Prix Cycliste de Québec](grand-prix-cycliste-de-quebec.md) | 2026-09-11 | endags | 1 | 1/1 | 7 | 0 | 0 |
| [Grand Prix Cycliste de Montréal](grand-prix-cycliste-de-montreal.md) | 2026-09-13 | endags | 1 | 1/1 | 6 | 0 | 0 |
| [Il Lombardia](il-lombardia.md) | 2026-10-10 | endags | 1 | 1/1 | 174 | 9 | 3 |
| [Tour of Guangxi](tour-of-guangxi.md) | 2026-10-13 | etape | 6 | 0/6 | 158 | 0 | 0 |

## 6. Hvad 2026 lærte os

- **Grand Tours blev passet, resten gjorde ikke.** Tour de France er komplet;
  klassikerne havde hverken startliste, stigninger, TV eller resultat, før
  backfillen 2026-10-12/13 hentede alle 21.
- **Manuelle knapper giver huller præcis dér, hvor opmærksomheden slipper** —
  typisk efter sidste etape og på løb uden for sæsonens højdepunkter.
- **Kilderne råder vi ikke over.** Strava lukkede segment-API'et midt i sæsonen
  (STG-033), ClimbFinder kræver nu en API-nøgle, og PCS har hverken tidslinje
  for endagsløb eller klatredata som tekst. Hver gang var svaret det samme:
  verificér, dokumentér, og byg på det, vi selv kan tegne ud fra GPX.
- **Den dyreste fejltype er den tavse.** Fire af årets fem største datahuller
  blev meldt som "ingen data endnu" af en agent, der kørte grønt igennem.





