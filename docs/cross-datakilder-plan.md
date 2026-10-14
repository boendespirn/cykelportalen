# Datakilder til cykelcross — plan

**Skrevet 2026-10-14.** Status: **forslag, afventer ejerens go.** Intet af
nedenstående er bygget. Issue: DATA-012. Beslægtet: DATA-011 (research-worker).

Alt herunder er verificeret i browseren eller mod API'et den dag, det blev
skrevet — ikke gættet. Hvor noget er en formodning, står det eksplicit.

---

## 1. Udgangspunktet: hvorfor PCS ikke rækker

Frem til nu har cross-løbene kun været prøvet mod ProCyclingStats. To ting
viste sig:

- PCS **har** cross og bruger vores egen slug (`/race/hg-cross-heerderstrand-2026`
  — året inde i slug'en, ikke som sti-segment som landevej).
- Men PCS opretter først siden **tæt på løbsdagen**. 2026-10-14 fandtes 1 af
  vores 24. De øvrige 23 svarede HTTP 200 med "Page not found" i selve siden —
  en blød 404, som det gamle tjek (`200` og `> 2000 bytes`) ville have godkendt
  som en gyldig kilde.

PCS er altså en rigtig kilde, bare en sen og tynd én. Der findes bedre.

---

## 2. Kilderne og hvad de faktisk kan

### 2a. cyclocross24.com — rygraden

Findes **på dansk**: `https://cyclocross24.com/dk/race/<sted>/`.

| Data | Dækning | Note |
|---|---|---|
| Starttider pr. kategori | Alle løb | Fx Overijse: Herre Elite 15:10, Dame Elite 13:40 |
| Banekort (billede) | De fleste | **Må ikke vises** — se afsnit 5 |
| Historiske vindere | Alle løb | Overijse har 1960-2025; Meulebeke tilbage til 1958 |
| Seriens stilling | Alle løb | Links til Superprestige-, X2O- og World Cup-klassementer |
| Resultater | Efter løbet | Top 10 med navn, nation og tid |
| TV/streaming | Nogle | Siger ærligt fra, når der intet er endnu |
| Startlister | **Kun hollandske løb** | Links videre til KNWU — se 2b |

**Slug'en er stednavnet**, ikke vores slug: `superprestige-overijse-2026` →
`overijse`, men `x2o-trofee-koppenbergcross-2026` → `oudenaarde`. Den kan
altså ikke udledes af vores slug, men den står i `races.name`
("X2O Trofee **Oudenaarde** - Koppenbergcross"). Koblingen laves én gang og
verificeres med løbsdatoen, ikke med navnet alene.

### 2b. KNWU via Foys-API'et — startlisterne

`mijn.knwu.nl` er en JavaScript-app; hver URL svarer med den samme 6854-byte
skal (endnu en blød 404 at tage højde for). Men siden henter sine data fra et
**offentligt API uden login**:

```
Base:    https://api.foys.io/cycling/public-api/v1
Headere: x-federationid:   2e38d9ea-84bb-452a-b58b-669352b0a2c6
         x-organisationid: 2e38d9ea-84bb-452a-b58b-669352b0a2c6
```

Uden de to headere svarer API'et `404 Entity Race ... was not found`. Med dem:

| Endpoint | Giver |
|---|---|
| `/races/race-participants?raceId={id}&maxResultCount=999` | **Startlisten** |
| `/races/{id}` | Løbets metadata |
| `/events/{id}` og `/races/lookup?eventId={id}` | Alle kategorier i stævnet |
| `/rankings/lookup?raceId={id}&showRaceRelatedRankings=true` | **Rangeringer** |
| `/competitions/competition-races?raceId={id}` | Hvilke serier løbet tæller i |

Verificeret på Heerderstrand (raceId 105128): 30 deltagere, hver med

```json
{"bib": null, "personName": "Nathan Bouwman", "personNationality": "NED",
 "personLicenseOrganisationName": "WSV de Peddelaars",
 "personLicenseTypeName": "Junior (U19)", "raceTeamName": null,
 "status": "Approved"}
```

Det er struktureret JSON — langt bedre end at læse en PDF.

**Begrænsningen er afgørende:** KNWU er det *hollandske* forbund. Af vores 24
løb ligger **ét** i Holland (Heerderstrand). Resten er 19 belgiske, 2 tjekkiske,
1 britisk og 1 fransk. KNWU dækker altså 1 af 24.

### 2c. Arrangørernes egne sider

`hgcross.be/meulebeke/` har banebeskrivelsen i klartekst — græsmarker, tekniske
zoner, trapper, omgange på ca. 3 km — og starttider pr. kategori. Samme
struktur findes på `superprestigecyclocross.be` og `x2otrofee.be`.
`races.source_url` peger i dag på cykelkalenderens kalenderside for alle 24
løb, så arrangør-proben i research-agenten har reelt intet at arbejde med.

### 2d. De belgiske startlister — det åbne hul

Meulebekes arrangør skriver, at tilmelding kun sker gennem Cycling Vlaanderens
portal. Sidste sæson lagde Exact Cross deltager-PDF'er ud
(`exactcross.be/.../Meulebeke-Deelnemers-Vrouwen.pdf`), altså kort før løbet.

**Formodning, ikke verificeret:** Foys er en platform, flere forbund bruger —
Belgian Cycling kan tænkes at ligge på samme API med et andet
`x-federationid`. Det er ét opslag at afgøre og bør være første skridt, før
nogen bygger en PDF-læser.

---

## 3. Worker 1 — research-agenten bekræfter kilderne

`datakilde_research_agent` udvides med tre prober, i den rækkefølge den selv
bruger (billigst først). Den **skriver fortsat kun** til `race_data_sources`.

1. **cyclocross24** — slå stednavnet op i deres kalender, match på **dato +
   løbsnavn**, gem URL'en. Dækker `stage_info`, `results` og en ny type til
   seriestilling.
2. **KNWU/Foys** — kun når `country_code = NL`: find `raceId` via
   `/races/lookup?eventId=...`, bekræft at `/races/race-participants` giver
   mindst én deltager. Dækker `startlist`.
3. **Arrangøren** — følg cyclocross24's link til arrangørens side og gem den
   som `source_url`, så den eksisterende arrangør-probe får noget at arbejde med.

**Blød-404-spærren skal gælde alle tre.** PCS svarer 200 med "Page not found",
KNWU svarer 200 med en tom skal. `pcs_side_mangler()` (allerede bygget) skal
generaliseres til en `side_mangler()`, der også kender KNWU's skal — ellers
katalogiserer vi tomme sider som gyldige kilder.

---

## 4. Worker 2 — hente-agenterne, i kronologisk orden

Rækkefølgen er ejerens krav: **nærmeste løb først, og kun det, der faktisk kan
hentes.** Spærretiden i research-agenten strammer allerede af sig selv
(månedligt → ugentligt under en måned → dagligt den sidste uge), så de to
regler passer sammen uden ny mekanik.

Pr. løb, regnet fra løbsdatoen:

| Hvornår | Hvad hentes | Fra |
|---|---|---|
| **Så snart løbet findes** | Historiske vindere, seriens stilling | cyclocross24 |
| **14 dage før** | Baneinfo og starttider pr. kategori | arrangør + cyclocross24 |
| **7 dage før** | Sendetid (kører allerede dagligt) | cykelkalenderen |
| **48 t / 6 t før** | Startliste | KNWU (NL) · PCS (når siden findes) |
| **Efter mål** | Resultat, derefter opdateret seriestilling | cyclocross24 · PCS |

Det giver en side, der **bygger sig selv op** i stedet for at stå tom: først
historik og seriestilling, så bane og tider, så sendetid, så startliste, og
til sidst resultatet. Præcis den rækkefølge en fan får brug for dem i.

Jobbene lægges i `scheduler.py`s `FOER_LOEB` som de eksisterende regler.

---

## 5. Guardrail — banekortene må ikke vises

cyclocross24 har banekort som JPG. **De må ikke lægges på vores sider.** Samme
regel som LEG-001 og som ejerens beslutning om stigningsprofiler: vi må gerne
udtrække *fakta* fra et tredjepartsbillede — antal omgange, underlag, længde —
og skrive dem i vores egen tekst eller tegne vores eget, men kildebilledet selv
vises aldrig.

Banebeskrivelsen fra arrangørens side er derimod tekst og kan refereres
normalt med kildeangivelse.

---

## 6. Hvad ejeren skal tage stilling til

1. **Bygges planen?** Omfang: tre prober i research-agenten, én ny hente-agent
   til cyclocross24, én til KNWU/Foys, og fem nye regler i `scheduler.py`.
2. **Seriestillingen** — skemaet og endpointet er bygget (migration
   `classifications_series_standings`). cyclocross24 og Foys' `rankings/lookup`
   kan begge fylde den. Skal den hentes fra cyclocross24, som dækker alle fire
   serier?
3. **De belgiske startlister** — skal jeg først afgøre, om Belgian Cycling
   ligger på samme Foys-API? Hvis ikke, er alternativet at læse arrangørernes
   deltager-PDF'er, hvilket er en større og skrøbeligere opgave.
