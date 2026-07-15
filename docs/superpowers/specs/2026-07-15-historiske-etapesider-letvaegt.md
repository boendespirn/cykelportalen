# Spec: Historiske etapesider (før 2026) — letvægtsstruktur uden stigningsprofiler

*Ejerens direktiv 2026-07-15, revision af den oprindelige backfill-plan
(`docs/superpowers/plans/2026-07-15-historiske-landingssider-5-aar.md`).*

## Formål og skelnen

Historiske etapesider (år < indeværende sæson) skal give læseren et **overblik**
over etapen. Kommende/indeværende etaper får fortsat **fuld dybde** (stignings-
profiler, lokale favoritter, TV/streaming, m.m.). Denne skelnen er bevidst og
permanent — ikke et midlertidigt kompromis, der skal indhentes senere.

Baggrund: stigningsprofil-pipelinen (STG-023-arbejdet) var den største flaske-
hals for at få historiske sider ud hurtigt. Ved at sløjfe den for historiske
sider helt kan vi levere reelt, indekserbart materiale nu, mens landingssiderne
allerede er begyndt at ranke på søgeord.

## Indhold på en historisk etapeside

**Med:**
- Header (etapenummer, start–mål, dato, distance, etapetype) — som nu.
- Højdeprofilbillede for **hele etapen** (`stages.elevation_image_url`, sat af
  `pcs_profile_image_agent.py`/`elevation_image_agent.py`) — **ikke** individuelle
  stigningsprofiler.
- Rute/kort — samme geocoding-logik som nu.
- Startliste (fuld).
- Favoritter — samme anbefalingslogik som nu (specialitet + UCI-ranking +
  kaptajn-flag), **uden** "lokal favorit"-mærkning/-vægtning. Vi henter ikke
  udvidet rytterdata (hjemby-/træningsregion) for rene historiske ryttere —
  de data opdateres kun, når rytteren rent faktisk stiller til start i et
  nyt/indeværende løb.
- Danske ryttere i feltet — som nu.
- Top 10 etaperesultat — som nu (`results_agent.py` er allerede begrænset til
  top 10).
- Klassement — men **kun løbets endelige/afsluttende resultat** (GC/point/
  bjerge/ungdom, som det så ud ved målstregen i sidste etape), **ikke**
  etape-for-etape-akkumuleret (det er en live-race-mekanik, jf. eksisterende
  regel om ingen live-funktioner). Samme endelige klassement vises uændret på
  alle etapesider for det pågældende løb — kræver en frontend-ændring, da
  `getEffectiveClassification()` i dag forsøger et etape-frosset øjebliksbillede
  først.
- Historisk fortælling/narrativ (**nyt**, se nedenfor).

**Uden (bevidst udeladt for historiske sider):**
- Individuelle stigningsprofiler/gradient-nedbrydning (`gpx_climb_agent.py`,
  `climbfinder_agent.py`, `climb_profile_generator.py`) — sløjfes helt for
  historiske sider. STG-023-fixet fra tidligere i dag er stadig værdifuldt for
  indeværende/kommende sæsoner, men er ikke længere en forudsætning for at
  åbne historiske sider.
- "Lokal favorit"-mærkning.
- TV/streaming-sektion — kræver ingen kodeændring, skjules allerede naturligt
  når `broadcastAll` er tom (hvilket den altid vil være for afsluttede løb).
- Særskilt rytterbillede-/rytterstats-opdatering for rene historiske ryttere —
  sker kun som naturlig bivirkning, hvis rytteren senere optræder på en ny
  startliste (ingen særskilt pipeline-handling nødvendig).
- Enhver live-tracking-mekanik.

## Historisk fortælling (nyt)

- AI-genereret tekst i historisk kommentator-sprog, der beskriver hvordan
  etapen udspillede sig — for etaper hvor resultatet gør dem kendte/
  nyhedsværdige. Kriterium for "kendt/nyhedsværdig" afventer ejerens input
  (se åbne spørgsmål).
- **Skal altid funderes i verificerbare kilder** — aldrig gættet/hallucineret
  fra ren parametrisk viden, jf. `CLAUDE.md` §6 og NEWS-001-læringen
  (hallucinerede links/fakta i tidligere artikler var en alvorlig, dyrt
  rettet fejl). Konkret kildegrundlag afventer ejerens input.
- **Variation er et eksplicit krav:** struktur og formulering skal variere på
  tværs af etaper — undgå skabelon-duplikeret tekst. Dette er både en SEO-
  hensyn (duplicate content skader ranking) og et brand-hensyn (`CLAUDE.md`
  §5: kun det vigtige, ingen tomme/generiske tekster).
- Lagres i nyt felt `stages.historic_recap` (text, nullable) — adskilt fra det
  eksisterende `stages.description`, som bruges til fremadrettede
  pre-race-beskrivelser af kommende etaper (anden tone og formål: forudsigende
  vs. tilbageskuende).

## Åbne spørgsmål (afventer ejeren — stillet i sessionen 2026-07-15)

1. **Kildegrundlag:** hvilken kilde/kilder skal AI'en bruge til at skrive
   verificerbart om, hvordan en historisk etape forløb?
2. **"Kendt/nyhedsværdig"-kriterium:** hvornår skrives der en fuld fortælling
   vs. kun en kort faktuel opsummering?
