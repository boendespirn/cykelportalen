# Etape-side: to klassement-dropdowns (Tour de France 2026)

## Formål

Etape-siden (`/[slug]/stage/[n]`) skal gøre hver etape til en "færdig" landing page: én gang etapens resultat og klassementstillingen *som den var lige efter den etape* er hentet, ændrer siden sig ikke mere. Sådan kan en bruger efter touren gå tilbage til enhver etape og se, hvordan klassementet så ud på det tidspunkt — uden at det er overskrevet af senere etaper.

Scope: kun Tour de France 2026 (kan generaliseres til andre etapeløb senere, hvis det virker godt).

## Nuværende tilstand

- `agents/results_agent.py` scraper allerede korrekt: top-10 etaperesultat (`results`-tabellen) **og** alle 4 klassementer — GC, point, bjerge, ungdom (`classifications`-tabellen, med `after_stage_number` der fryser standen pr. etape). Ingen ændringer nødvendige her.
- `api.py` har i dag:
  - `GET /races/{slug}/stages/{stage_number}/results` — top-10 for etapen.
  - `GET /races/{slug}/stages/{stage_number}/gc` — **kun** GC-klassementet som det så ud efter den etape.
  - `GET /races/{slug}/classifications/{classif_type}` — GC/point/bjerge/ungdom, men altid **seneste** etape, ikke en bestemt etape.
- `cykel-frontend/app/[slug]/stage/[n]/page.tsx` viser i dag to stablede fuld-bredde blokke: "Etaperesultat" (top-10) og "Klassement efter etapen" (kun GC, ikke foldbar).
- `cykel-frontend/app/[slug]/SpoilerSection.tsx` har allerede en fane-switcher mellem de 4 trøjer (bruges på løbsoversigten), med race-specifik farve/label via `getJerseyConfig(raceSlug)`.

## Ændringer

### 1. Backend — `api.py`

Nyt endpoint:

```
GET /races/{slug}/stages/{stage_number}/classifications/{classif_type}
```

- `classif_type` valideres til `gc|points|mountains|youth` (samme tjek som eksisterende `get_classification()`).
- Samme `select`-felter som `get_classification()` (inkl. `points`), men filtreret på `after_stage_number=eq.{stage_number}` i stedet for at slå seneste etape op.
- Returformat matcher det eksisterende GC-stage-endpoint: `{"after_stage": stage_number, "standings": [...]}`, eller tomt array/`{"standings": []}` hvis ingen data findes for den etape+type.

Det eksisterende `/races/{slug}/stages/{stage_number}/gc`-endpoint fjernes, når frontend er lagt om til at bruge det nye generelle endpoint for alle 4 typer — først verificeres at intet andet kalder det gamle endpoint.

Ingen ændringer i `results_agent.py`.

### 2. Frontend-komponenter (`cykel-frontend/`)

- **`Disclosure`** (ny, lille, generisk komponent) — fold-ud/fold-sammen-wrapper udtrukket fra collapse-logikken i `SpoilerSection.tsx`. Props: `title`, `children`. Ejer kun åben/lukket-state (lukket som default). Ingen viden om klassement- eller resultatdata.
- **`ClassificationTabs`** (ny, udtrukket fra `SpoilerSection.tsx`'s eksisterende fane-switch) — tager de 4 standings-lister (gc/points/mountains/youth) + `raceSlug` som props, gengiver samme trøje-kort-faner og tabel som i dag. Bruges både i det nye højre panel og (uændret adfærd) i `SpoilerSection.tsx`.
- **`app/[slug]/stage/[n]/page.tsx`**: de to nuværende fulde-bredde blokke ("Etaperesultat", "Klassement efter etapen") fjernes og erstattes af:
  - Layout: `grid grid-cols-1 md:grid-cols-2 gap-4` — fuld bredde stablet på mobil, halv bredde side om side på desktop.
  - Venstre `Disclosure` ("Etape {n} resultat"): eksisterende top-10-markup (uændret data/visning), pakket ind i `Disclosure`.
  - Højre `Disclosure` ("Klassement efter etape {n}"): `ClassificationTabs` fodret med data fra 4 parallelle kald til det nye endpoint (ét pr. trøjetype: gc, points, mountains, youth).
  - Begge paneler lukkede som standard.

### 3. Fejlhåndtering

Hvis en klassementstype ikke har data for den pågældende etape (fx bjergtrøjen før nogen KOM-point er uddelt, eller et enkelt kald fejler), viser den fane "Ingen data endnu" i stedet for en tom tabel — samme mønster som findes i dag ved tomme arrays.

### 4. Kendt usikkerhed — bjergtrøjens 0-points-tilfælde

Ejeren har bekræftet at PCS' eget bjergklassement allerede viser lederen (fx Pogačar efter holdenkeltstarten) med 0 point, selvom ingen KOM-point er uddelt endnu — det er altså kildedata der skal scrapes korrekt, ikke en særregel vi skal bygge. Verificeres manuelt når Tour de France 2026 etape 1 er kørt (4. juli); hvis PCS-scrapingen af `mountains`-klassementet **ikke** viser lederen korrekt på dette tidspunkt, oprettes det som en opfølgende fejlrettelse i `results_agent.py`'s scraping af tabel 6 (bjergklassement) — ikke som del af denne feature.

## Test / verifikation

Manuel verifikation (via `run`-skill) af en TdF 2026-etapeside efter mindst én etape er kørt:
- Begge dropdowns folder korrekt ud/sammen.
- Alle 4 faner i højre panel viser data for den korrekte etape (ikke "seneste etape" hvis man ser på en tidligere etapeside).
- Layout er halv bredde side om side på desktop, stablet fuld bredde på mobil.
- Bjergtrøje-fanen viser lederen (evt. med 0 point) — flag som opfølgning hvis ikke.
