# Plan: rutekort og seriestillinger for cykelcross

Skrevet 2026-11-08 efter ejerens ønske. Begge dele er **nye kilder**, så intet
bygges, før ejeren har godkendt planen (CLAUDE.md §9.5, hukommelsens regel om
nye løsninger).

## 1. Rutekort på crossløbenes landingssider

**Hvad findes (kontrolleret råt 2026-11-08):** arrangørerne lægger et
parcoursplan op som billede — fx `koppenbergcross.be/praktische-info/` med
`parcoursplan-koppenberg_01-1280x720.jpg`. Det er arrangørens grafik, ikke fri
data.

**Problemet er licensen, ikke teknikken.** CLAUDE.md §7: kun billeder, vi har ret
til. Et parcoursplan er arrangørens ophavsret, og vores egen regel for
tredjepartsbilleder er "udtræk fakta, tegn vores eget design, vis aldrig
kildebilledet". Tre muligheder, i anbefalet rækkefølge:

1. **Fakta + link (kan bygges nu, ingen ret nødvendig).** En agent finder
   parcoursplanen på løbets officielle side og gemmer *adressen på
   arrangørens side* og de fakta, der står der (omgangslængde, sandpartier,
   trapper, broer, Koppenberg-stigningen). Landingssiden viser fakta i
   "Baneinfo" og knappen "Se rutekortet hos arrangøren →".
2. **Tilladelse fra serierne (kræver ejeren).** Golazo (X2O-sitene),
   Superprestige og HG Cross kan give lov til at vise kortene med kildeangivelse.
   Én henvendelse pr. serie dækker alle deres løb. Det er en menneskeopgave —
   via kontaktformularer, så ejeren forbliver anonym.
3. **Egen tegning (senere, hvis 2 ikke lykkes).** Et skematisk banekort i vores
   eget design ud fra fakta. Tungere, og et parcoursplan er ofte for stiliseret
   til at kunne aflæses præcist.

**Byggeplan for 1:** `cross_course_agent.py` → kigger på løbets egen side
(samme opslag som startlisteagenten: X2O-sitets `/praktische-info/`,
hgcross.be/<by>/, Superprestiges kalenderside), gemmer link og fakta i
`stages.description`/`fun_facts` (feltet, Baneinfo allerede viser) og
`race_data_sources` (type `course_map`). Trin i `fuld_forberedelse`, så den
kører 30/14/7-1 dage før hvert løb.

## 2. Samlede stillinger pr. serie

**Vi må ikke regne stillingen ud selv.** Vi gemmer kun top 10 pr. løb, og en
rytter, der blev nr. 12 i ét løb, får point, vi ikke kender. Et selvberegnet
klassement ville være forkert for alle uden for top 10 — og ofte også i top 10.
Derfor hentes den officielle stilling.

| Serie | Officiel kilde (fundet 2026-11-08) | Form |
|---|---|---|
| X2O Trofee | `x2otrofee.be/klassement-elite-mannen/` | HTML-tabel, fuld stilling **på tid** (Nys 1:01:16 efter Koppenberg) |
| Superprestige | `superprestigecyclocross.be/nl/klassement` | Top 3 på siden + fuld stilling som PDF ("Bekijk"), **point** (Vanthourenhout 29) |
| World Cup | ikke fundet endnu — UCI's egen side, evt. PCS | **skal findes** (research-agenten) |
| HG Cross | ingen stillingsside på hgcross.be | serien ser ikke ud til at have en samlet stilling — bekræftes |

**Byggeplan:**
- Ny tabel `series_standings` (serie, sæson, plads, rytter, point **eller** tid,
  kilde-URL, opdateret) — én række pr. rytter, erstattes ved hver hentning.
- `cross_standings_agent.py`, ét lille modul pr. kilde (samme mønster som
  `cross_results_agent.py`), med kontrol: stillingens fører skal kunne genfindes
  i vores egne resultater, og antallet af afviklede løb skal stemme.
- Trin i jobbet `resultater`, så stillingen hentes lige efter hvert løbs resultat.
- Frontend: stillingen øverst på hver serieunderside (`/races/cykelcross/<serie>`)
  og en lille "Stillingen i serien"-boks på løbssiden.

## Hvad ejeren skal sige ja/nej til

1. Rutekort: start med **fakta + link** (1), og skal vi skrive til serierne om lov (2)?
2. Stillinger: må vi hente de **officielle** stillinger fra X2O og Superprestige
   som beskrevet, og sætte research-agenten på World Cup-kilden?
