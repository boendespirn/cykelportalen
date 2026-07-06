# Dagligt optimerings-scan og Telegram-digest

## Formål

I dag betyder "gå i gang med at arbejde" uden yderligere kontekst, at direktøren selv vælger et konkret, allerede kendt punkt fra `state/issues.md` og udfører det. Det fungerer fint for kendte bugs, men giver ikke et system, der løbende **finder nye** optimerings- og vækstpunkter og lader ejeren godkende dem, før noget sættes i gang.

Dette design gør "gå i gang med at arbejde uden kontekst" til en fast proces: et scan af sidens tilstand (data, design, UX, vækstmuligheder), der ender med at nye forslag lægges i `state/issues.md` og præsenteres for ejeren — i sessionen og via Telegram — til godkendelse, i stedet for at blive udført med det samme.

Formålet er at holde teamet i gang med forbedringer så ofte som muligt, uden at ejeren selv skal formulere lange prompts hver gang — samtidig med at strategiske/kostbare beslutninger (marketing-retning, design-ændringer, nye content-formater) altid kræver ejerens eksplicitte ja, i modsætning til almindelige databugs, som fortsat rettes automatisk efter `PROTOKOL.md`.

## Ikke i scope (bevidst droppet under design)

- **Intet automatisk tidspunkt/cron.** Oprindeligt tænkt som en Windows Task Scheduler-opgave kl. 7:30 dagligt, men ejeren kunne ikke oprette opgaven i Task Scheduler. Scannet kører derfor **udelukkende** når ejeren selv beder om det ("gå i gang med at arbejde"), aldrig på et fast klokkeslæt.
- **Vercel Analytics indgår ikke i første version.** Kræver at ejeren logger Vercel CLI ind lokalt (OAuth, kan ikke automatiseres). Tilføjes som opfølgning, når det er gjort.

## Nuværende tilstand (relevant for designet)

- `PROTOKOL.md` definerer allerede rollerne (kontrolagent, direktør, udførende agenter, research-agent, ejer) og statusflowet i `state/issues.md` (`NY → TILDELT → ESKALERET → AFVENTER_EJER → LØST`, samt `HENLAGT`). Dette design **genbruger** den statusmaskine — ingen nye statusser.
- `.claude/agents/kontrolagent.md` har i dag kun `Read, Grep, Glob, Bash, WebFetch, WebSearch` — ingen browser-/skærmbillede-adgang. `.mcp.json` i repo-roden har allerede en `playwright`-MCP-server konfigureret, så værktøjet er tilgængeligt, det er blot ikke givet til kontrolagenten endnu.
- `.claude/agents/research-agent.md` har allerede to spor: **reaktivt** (får et konkret problem fra direktøren) og **proaktivt** (researcher selv bredt). Dette design gør det reaktive spor til hovedvejen for nye optimeringsfund — research-agenten får en afgrænset brief pr. punkt, ikke en bred fritekst-opgave.
- `.claude/agents/seo-agent.md` har allerede adgang til `agents/gsc_agent.py` og har lige udført en frisk GSC-kontrol (SEO-001, 2026-07-06) — samme mønster genbruges i scannet.
- Telegram-kanalen er sat op og verificeret (OPS-006, LØST) — sessioner startet med `claude --channels plugin:telegram@claude-plugins-official` (nu automatisk via PowerShell-profilen) kan sende beskeder direkte til ejerens telefon.
- `STRATEGI.md` er opdateret (2026-07-07) til at afspejle, at indekserings-flaskehalsen er et autoritets-/linking-problem, at research-agenten løbende skal undersøge rodårsager til det, og at marketing-kvalitet/-kvantitet + løbsklargøring er en aktiv prioritet mens man venter på nye Google-rapporter.

## Design

### 1. Udløser: "gå i gang med at arbejde" uden kontekst

Når ejeren giver en kontekstløs instruktion om at arbejde, følger direktøren denne algoritme (i stedet for blot at vælge en opgave fra `issues.md`):

1. **Tjek `state/issues.md` for ubehandlede vækst-/optimeringsforslag** — poster med status `NY`, mærket som forslag (se format nedenfor), der endnu ikke er besvaret af ejeren.
2. **Findes der ubehandlede forslag:** præsentér dem for ejeren til godkendelse (i sessionen som tekst, og som Telegram-besked hvis ejeren ikke selv sidder i terminalen). Direktøren udfører **ikke** noget af det på egen hånd.
3. **Findes der ingen ubehandlede forslag** (alt er allerede besluttet/afvist, eller det er første gang): direktøren starter et nyt scan (afsnit 2), skriver eventuelle nye fund til `issues.md`, committer/pusher, og præsenterer/sender digest som i punkt 2.
4. Almindelige, konkrete opgaver (ejeren nævner en specifik bug, et specifikt issue-ID, en specifik feature) ændrer sig **ikke** — de udføres som hidtil. Denne algoritme gælder kun det generiske "gå i gang"-tilfælde.

### 2. Selve scannet

Tre specialist-agenter aktiveres:

**Kontrolagenten** (opgraderet værktøjsadgang: tilføj Playwright-værktøjer til `.claude/agents/kontrolagent.md`s `tools:`-liste, så den kan tage skærmbilleder) gennemgår kritisk et udsnit af de vigtigste sider (forside, et aktivt løb, en etapeside, en rytter-/holdside):

- Dens eksisterende opgave uændret: datakorrekthed (stigningsprofiler, nøgletal), døde links, brudte elementer.
- **Ny opgave:** identificér konkrete optimeringspunkter — navigation/UX-friktion, designmuligheder (effekter, layout, "flere effekter" ejeren efterspurgte), svaghed i marketing-/content-materialets kvalitet eller mængde, alt andet der virker som en reel forbedringsmulighed.
- Rapporterer **alt** til direktøren i sit vante format (Hvad/Hvor/Bevis/Alvor/Forslag) — bugs og optimeringspunkter i samme rapport, men tydeligt adskilt.

**Direktøren** modtager kontrolagentens fund og deler dem i to spor:

- **Databugs/fejl** → auto-tildeles den ansvarlige udførende agent, som hidtil efter `PROTOKOL.md`. Ingen ændring.
- **Optimeringspunkter** → direktøren vurderer relevans. For hvert punkt, der vurderes værd at forfølge, sendes en **afgrænset, konkret brief** til research-agenten: *"Find de bedste metoder til at eksekvere/optimere netop dette punkt — AI-værktøjer, plugins, skills, MCP-servere, API'er, datapunkter."* Punkter, der ikke vurderes relevante, logges stadig (som `HENLAGT` eller slet ikke, efter direktørens skøn), så de ikke tabes, men fylder ikke i digesten.

**Research-agenten** modtager den afgrænsede brief og leverer sit vante brief-format (Problem/Mulige løsninger/Anbefaling/Hvad jeg mangler), skarpt rettet mod netop det ene punkt — ikke bred fritekst-research. Det faste spor om at undersøge rodårsager til manglende Google-indeksering (jf. `STRATEGI.md` §1) hører også hjemme her, når relevant.

**Seo-agenten** kører en frisk GSC-kontrol (indeksering, striking-distance-søgeord, lav-CTR-sider) som fast del af scannet, samme metode som SEO-001-kontrollen 2026-07-06.

### 3. Hvordan fund bliver til `issues.md`-poster

- **Databugs** — uændret: logges, tildeles, rettes, verificeres af kontrolagenten, markeres `LØST`. Ingen godkendelse fra ejeren krævet undervejs (som i dag).
- **Optimerings-/vækstforslag** — logges **altid** med status `NY`, og beskrivelsen indledes tydeligt med **"Forslag (afventer godkendelse):"**, så de er umiddelbart genkendelige i `issues.md` og på `/admin/opgaver`-boardet, adskilt fra almindelige bugs. De sættes **aldrig** automatisk til `TILDELT` — kun når ejeren siger ja (i en session eller via Telegram-svar), tildeler direktøren dem videre til den rette udførende agent.
- Alt committes og pushes med det samme, jf. `PROTOKOL.md`s regel om commit pr. statusændring.

### 4. Telegram-digest

Efter scannet (eller når ubehandlede forslag findes ved punkt 1.2) sendes én samlet Telegram-besked via `reply`-værktøjet, grupperet i to lister:

- **Bugs/datafejl fundet og allerede sat i gang** — kort, informativt, ingen handling krævet fra ejeren.
- **Vækst-/optimeringsforslag, der venter på godkendelse** — hvert punkt som én linje: issue-ID + kort beskrivelse.

Besked afsluttes med en klar opfordring, fx: *"Svar 'ja <ID>' eller tag det op, når du er klar."*

### 5. Sidegevinst: generel "sig til når noget kræver min stillingtagen"-regel

Ejeren har separat bedt om, at direktøren fremover sender en Telegram-besked, så snart noget kræver ejerens stillingtagen — ikke kun ved dette scan. `PROTOKOL.md`s menneske-handoff-trin (§7) nævner i dag stadig Slack `#direktøren`, som er forældet efter OPS-006 (Telegram erstattede Slack). Dette rettes som del af denne ændring: handoff sker via Telegram-beskeden (samme `reply`-værktøj), ikke Slack.

## Ændringer i filer

1. **`.claude/agents/kontrolagent.md`** — udvid `tools:`-linjen med Playwright MCP-værktøjerne (navigate, snapshot/screenshot m.fl.), og tilføj en kort sektion om det nye "optimeringspunkt"-fund ud over databugs.
2. **`.claude/agents/research-agent.md`** — præcisér at det reaktive spor (afgrænset brief fra direktøren pr. konkret punkt) er hovedvejen for nye fund fra kontrolagenten; det proaktive spor er sekundært.
3. **`PROTOKOL.md`** — §7 (menneske-handoff): erstat Slack `#direktøren` med Telegram; tilføj kort regel om at nye optimeringsforslag altid kræver ejerens eksplicitte godkendelse før `TILDELT` (i modsætning til almindelige bugs).
4. **`state/issues.md`** — ingen skemaændring; ny konvention: optimeringsforslag mærkes i beskrivelsen med "Forslag (afventer godkendelse):".
5. **Direktørens egen adfærd** (denne fil / fremtidige sessioners system-kontekst) — algoritmen i afsnit 1 anvendes, når ejeren beder om arbejde uden konkret kontekst.

`STRATEGI.md` er allerede opdateret separat (committet `a7c50df`) og kræver ingen yderligere ændring for dette design.

## Fejlhåndtering / afgrænsning

- Hvis kontrolagenten ikke finder nogen optimeringspunkter (ren kontrol), sendes stadig en kort digest ("ingen nye fund i dag") — samme princip som kontrolagentens eksisterende regel om at en ren kontrol også er et resultat.
- Hvis research-agenten for et givet punkt ikke kan finde en konkret, eksekverbar metode, leverer den stadig sit brief med "Hvad jeg mangler" udfyldt — punktet logges som `NY`/afventer, ikke som et løst forslag.
- Ingen automatisk fejl-fallback er nødvendig, da scannet altid sker i en session, ejeren selv har startet (ingen baggrundsjob, der kan fejle usynligt).

## Opfølgning (uden for denne spec)

- Vercel Analytics tilføjes til scannets datagrundlag, når Vercel CLI er logget ind lokalt.
- Hvis ejeren senere får sat en Task Scheduler-opgave op (eller finder en anden mekanisme), kan et fast tidspunkt genovervejes — designet her er bevidst uafhængigt af det, så det kan tilføjes uden at ændre selve scan-logikken.
