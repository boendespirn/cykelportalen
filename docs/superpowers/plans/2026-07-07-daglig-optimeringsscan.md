# Dagligt optimerings-scan og Telegram-digest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gør "gå i gang med at arbejde uden kontekst" til en struktureret proces: kontrolagenten finder ikke kun bugs men også optimeringspunkter, research-agenten får afgrænsede briefs pr. punkt fra direktøren, alle vækst-/optimeringsforslag kræver ejerens eksplicitte godkendelse før `TILDELT`, og menneske-handoff sker via Telegram i stedet for det forældede Slack-spor.

**Architecture:** Ren dokumentations-/protokolændring — ingen ny kode, ingen nye tjenester. Fire markdown-filer opdateres (`kontrolagent.md`, `research-agent.md`, `PROTOKOL.md`, `ORKESTRATOR.md`), og ét nyt issue logges i `state/issues.md`. Hver fil læses af fremtidige Claude-sessioner som instruktion, så "testen" for hver opgave er at læse filen tilbage og verificere ordlyden, samt at grep'e for at bekræfte alle Slack-referencer er væk.

**Tech Stack:** Markdown (agent-definitioner med YAML-frontmatter), git.

## Global Constraints

- Al tekst skrives på dansk (jf. `CLAUDE.md`: "Alt arbejde foregår på dansk").
- Ingen ændring må bryde `CLAUDE.md`s guardrails (§7) — dette er rene protokol-/rolledefinitioner, ingen produktions- eller datalogik berøres.
- Commit pr. fil/statusændring (jf. `PROTOKOL.md`s regel om commit pr. opgave-statusændring) — ikke én stor batch-commit til sidst.
- Design-spec er allerede godkendt og committet: `docs/superpowers/specs/2026-07-07-daglig-optimeringsscan-design.md` (commit `6f446da`). Denne plan implementerer den 1:1 — ingen nye beslutninger, kun eksekvering.

---

### Task 1: Kontrolagenten får Playwright-adgang og opgaven "find optimeringspunkter"

**Files:**
- Modify: `.claude/agents/kontrolagent.md`

**Interfaces:**
- Consumes: intet (selvstændig agent-definition).
- Produces: kontrolagenten kan fremover kaldes med Playwright-værktøjer tilgængelige (`mcp__playwright__browser_navigate` m.fl.), og dens outputformat inkluderer et "bug vs. optimeringspunkt"-flag, som Task 3/4 (direktørens rutediagram) forudsætter.

- [ ] **Step 1: Udvid `tools:`-linjen i frontmatter**

Nuværende linje 4:
```
tools: Read, Grep, Glob, Bash, WebFetch, WebSearch
```

Erstat med:
```
tools: Read, Grep, Glob, Bash, WebFetch, WebSearch, mcp__playwright__browser_navigate, mcp__playwright__browser_snapshot, mcp__playwright__browser_take_screenshot, mcp__playwright__browser_resize, mcp__playwright__browser_wait_for, mcp__playwright__browser_console_messages, mcp__playwright__browser_network_requests, mcp__playwright__browser_close, mcp__playwright__browser_tabs
```

(Kun læse-/observations-værktøjer fra Playwright-sættet — ikke `click`, `type`, `evaluate`, `fill_form` m.fl., da kontrolagenten aldrig må ændre noget, jf. dens eksisterende "Du må ALDRIG"-regel.)

- [ ] **Step 2: Tilføj nyt punkt 4 i "Hvad du kontrollerer"**

Find sektionen (linje 12-19), som slutter med punkt 3 ("Social-content..."). Tilføj lige efter punkt 3, før linjen `## Sådan arbejder du`:

```markdown
4. **Optimeringspunkter (vækst og oplevelse).** Ud over bugs skal du proaktivt identificere konkrete forbedringsmuligheder: navigations-/UX-friktion, designmuligheder (visuelle effekter, layout, letforståelig struktur), og svaghed i marketing-/content-materialets kvalitet eller mængde. Brug Playwright (`browser_navigate` + `browser_take_screenshot`/`browser_snapshot`) til at se sider, som en bruger reelt ville se dem — ikke kun rå HTML via WebFetch. Rapportér disse adskilt fra bugs (se format nedenfor). Du vurderer ikke selv løsningsmetoder — det er research-agentens opgave, når direktøren sender punktet videre.
```

- [ ] **Step 3: Præcisér output-formatet til at skelne bug fra optimeringspunkt**

Find linjen (nuværende linje 29): `For hvert fund, angiv:` og listen der følger. Tilføj en ny linje lige efter listen (før "Slut altid af med..."):

```markdown
Angiv altid tydeligt, om fundet er en **bug** (databug, dødt link, brudt element — hasterelateret) eller et **optimeringspunkt** (forbedringsmulighed uden akut fejl). De to behandles forskelligt af direktøren: bugs auto-tildeles og rettes som hidtil; optimeringspunkter kræver ejerens eksplicitte godkendelse, før nogen agent går i gang.
```

- [ ] **Step 4: Verificér ved at læse filen tilbage**

Læs `.claude/agents/kontrolagent.md` i sin helhed og bekræft:
- `tools:`-linjen indeholder de 9 nye Playwright-værktøjer.
- Punkt 4 findes under "Hvad du kontrollerer".
- Bug/optimeringspunkt-skellet er nævnt i output-sektionen.

- [ ] **Step 5: Commit**

```bash
git add .claude/agents/kontrolagent.md
git commit -m "feat(kontrolagent): tilføj Playwright-adgang og optimeringspunkt-opgave"
```

---

### Task 2: Research-agenten gøres reaktiv-først med afgrænsede briefs

**Files:**
- Modify: `.claude/agents/research-agent.md`

**Interfaces:**
- Consumes: intet.
- Produces: research-agentens primære arbejdsform (afgrænset brief pr. punkt fra direktøren) matcher det, direktørens rutediagram (Task 4) forudsætter, når den sender et kontrolagent-fundet optimeringspunkt videre.

- [ ] **Step 1: Omskriv "Dine to opgaver"-sektionen**

Find sektionen (nuværende linje 12-19):

```markdown
## Dine to opgaver

1. **Reaktivt (eskalering):** Direktøren giver dig et problem, en agent ikke kunne løse. Forstå det til bunds, tænk kreativt og bredt, og find mulige løsninger — også utraditionelle.
2. **Proaktivt (løbende):** Research bedre og mere akkurate kilder og metoder til:
   - **stigningsprofiler** (mere pålidelige kilder/metoder end nuværende)
   - **rytterdata** (form, resultater, startlister)
   - **lovligt frie billeder** (licensbureauer, embeds, Wikimedia Commons, holdenes pressekits)
   - samt generelle forbedringer, der kan øge trafik, autoritet eller brugeroplevelse i tråd med strategien.
```

Erstat med:

```markdown
## Dine to opgaver

1. **Reaktivt (hovedsporet):** Direktøren giver dig et konkret, afgrænset punkt — enten et problem en agent ikke kunne løse, **eller et optimeringspunkt kontrolagenten har fundet under en kritisk gennemgang af siden** (fx svag marketing-content, en navigations-friktion, et forældet stigningsprofil-format). Din opgave er præcis: find de bedste metoder til at eksekvere/optimere netop DETTE ene punkt — AI-værktøjer, plugins, skills, MCP-servere, API'er, datapunkter. Tænk kreativt og bredt, men hold dig til det konkrete punkt, du har fået.
2. **Proaktivt (sekundært):** Kun når du ikke er aktiveret på et konkret punkt, kan du selv research bedre og mere akkurate kilder og metoder til:
   - **stigningsprofiler** (mere pålidelige kilder/metoder end nuværende)
   - **rytterdata** (form, resultater, startlister)
   - **lovligt frie billeder** (licensbureauer, embeds, Wikimedia Commons, holdenes pressekits)
   - samt generelle forbedringer, der kan øge trafik, autoritet eller brugeroplevelse i tråd med strategien.
   - **Indeksering:** en fast del af dette spor er løbende at undersøge de reelle årsager til, at Google ikke indekserer siden (autoritetssignaler, intern linking, sammenlignelige sites), jf. `STRATEGI.md` §1 — ikke kun vente passivt.
```

- [ ] **Step 2: Verificér ved at læse filen tilbage**

Læs `.claude/agents/research-agent.md` og bekræft, at "Reaktivt" nu er mærket "hovedsporet", "Proaktivt" er mærket "sekundært", og at det nye indekserings-underpunkt er til stede.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/research-agent.md
git commit -m "feat(research-agent): gør reaktivt spor til hovedvej for kontrolagent-fund"
```

---

### Task 3: PROTOKOL.md — Telegram erstatter Slack, ny godkendelsesregel for vækstforslag

**Files:**
- Modify: `PROTOKOL.md`

**Interfaces:**
- Consumes: intet.
- Produces: den formelle protokolregel "vækst-/optimeringsforslag kræver ejerens godkendelse før `TILDELT`", som Task 4 (ORKESTRATOR.md) og Task 5 (issues.md-loggen) refererer til.

- [ ] **Step 1: Opdatér kontrolagent-rollebeskrivelsen**

Find (nuværende linje 9):
```
- **Kontrolagenten** — opdager fejl via kritiske kontroller og rapporterer til direktøren.
```

Erstat med:
```
- **Kontrolagenten** — opdager fejl og optimeringspunkter via kritiske kontroller og rapporterer til direktøren.
```

- [ ] **Step 2: Opdatér "Direktørens første handling hver kørsel"**

Find (nuværende linje 25):
```
**Direktørens første handling hver kørsel:** læs `state/issues.md` og tjek Slack `#direktøren` for nye svar fra ejeren, og fortsæt derfra.
```

Erstat med:
```
**Direktørens første handling hver kørsel:** læs `state/issues.md` og tjek om ejeren har svaret på en tidligere Telegram-besked, og fortsæt derfra.
```

- [ ] **Step 3: Opdatér menneske-handoff-trinnet (§7 i flowet)**

Find (nuværende linje 41):
```
7. **Menneske-handoff:** direktøren poster i Slack `#direktøren` et kort, klart brief: hvad er problemet, hvad er prøvet, og præcis hvad der ønskes fra ejeren. **Aldrig hemmeligheder eller tokens i beskeden.** Notér i `issues.md`.
```

Erstat med:
```
7. **Menneske-handoff:** direktøren sender en Telegram-besked (samme kanal som al anden ejer-kommunikation, jf. OPS-006) med et kort, klart brief: hvad er problemet, hvad er prøvet, og præcis hvad der ønskes fra ejeren. **Aldrig hemmeligheder eller tokens i beskeden.** Notér i `issues.md`. Denne regel gælder bredt: så snart noget kræver ejerens stillingtagen — ikke kun ved `AFVENTER_EJER` — sender direktøren besked med det samme, frem for at vente til ejeren selv spørger.
```

- [ ] **Step 4: Opdatér "Regler"-sektionen — Slack-beskeder → Telegram-beskeder, og ny godkendelsesregel**

Find (nuværende linje 53):
```
- **Slack-beskeder:** korte, konkrete, ét issue ad gangen, aldrig følsomme data.
```

Erstat med:
```
- **Telegram-beskeder:** korte, konkrete, ét issue ad gangen, aldrig følsomme data.
- **Vækst-/optimeringsforslag kræver altid ejerens eksplicitte godkendelse før `TILDELT`** — i modsætning til almindelige bugs/datafejl, som auto-tildeles som normalt. Sådanne forslag mærkes i beskrivelsen med "Forslag (afventer godkendelse):" og forbliver `NY`, indtil ejeren siger ja.
```

- [ ] **Step 5: Verificér ingen resterende Slack-referencer**

```bash
grep -in "slack" PROTOKOL.md
```
Forventet: intet output (ingen match).

- [ ] **Step 6: Commit**

```bash
git add PROTOKOL.md
git commit -m "fix(protokol): erstat Slack med Telegram, tilføj godkendelsesregel for vækstforslag"
```

---

### Task 4: ORKESTRATOR.md — Telegram overalt, ny "gå i gang uden kontekst"-algoritme, første commit

**Files:**
- Modify: `ORKESTRATOR.md` (i dag untracked — dette er filens første commit)

**Interfaces:**
- Consumes: refererer til `docs/superpowers/specs/2026-07-07-daglig-optimeringsscan-design.md` (allerede committet).
- Produces: den direktør-adfærd, ejeren aktiverer med et kontekstløst "gå i gang med at arbejde".

- [ ] **Step 1: Opdatér header-afsnittets connector-reference**

Find (nuværende linje 3):
```
Dette er teksten, du indsætter som **prompt på din daglige routine**. Den aktiverer direktør-rollen oven på den fælles forfatning. Versionsstyr den her i repoet, så ændringer er sporbare. Routinen skal have adgang til repoet, til `Task`-værktøjet (så direktøren kan delegere til subagenter), og til Slack-connectoren (kanal `#direktøren`).
```

Erstat med:
```
Dette er teksten, du indsætter som **prompt på din daglige routine**, eller instruktionen der gælder, når ejeren beder om arbejde uden konkret kontekst i en almindelig session. Den aktiverer direktør-rollen oven på den fælles forfatning. Versionsstyr den her i repoet, så ændringer er sporbare. Routinen/sessionen skal have adgang til repoet, til `Task`-værktøjet (så direktøren kan delegere til subagenter), og til Telegram-kanalen (session startet med `claude --channels plugin:telegram@claude-plugins-official`).
```

- [ ] **Step 2: Opdatér punkt 3 i "Start hver kørsel med at læse dig ind"**

Find (nuværende linje 15):
```
3. Tjekke Slack `#direktøren` for nye svar fra ejeren, og samle dem op i de relevante issues.
```

Erstat med:
```
3. Tjekke om ejeren har svaret på en tidligere Telegram-besked, og samle det op i de relevante issues.
```

- [ ] **Step 3: Tilføj ny sektion "Når ejeren beder om arbejde uden konkret kontekst"**

Indsæt som ny sektion **efter** "## Sådan arbejder du" (efter nuværende linje 25) og **før** "## Menneske-handoff":

```markdown
## Når ejeren beder om arbejde uden konkret kontekst

Hvis ejeren beder dig gå i gang med at arbejde uden at pege på noget konkret (intet issue-ID, ingen specifik opgave):

1. Tjek `state/issues.md` for ubehandlede vækst-/optimeringsforslag — poster med status `NY`, mærket "Forslag (afventer godkendelse):".
2. **Findes der nogen:** præsentér dem for ejeren (i sessionen, og som Telegram-besked hvis relevant) til godkendelse. Udfør intet af det selv.
3. **Findes der ingen:** kør et scan — aktivér kontrolagenten (databugs OG optimeringspunkter), send relevante optimeringsfund videre til research-agenten med en afgrænset brief pr. punkt, og lad seo-agenten køre en frisk GSC-kontrol. Log alle fund i `state/issues.md` (bugs som altid; optimeringsforslag altid som `NY`/"Forslag (afventer godkendelse):"), commit/push, og præsentér/send digest som i punkt 2.
4. Denne algoritme gælder kun det generiske, kontekstløse tilfælde — peger ejeren på noget konkret, udføres det direkte som hidtil.

Se `docs/superpowers/specs/2026-07-07-daglig-optimeringsscan-design.md` for det fulde design.
```

- [ ] **Step 4: Opdatér "Menneske-handoff"-sektionen**

Find (nuværende linje 27-29):
```markdown
## Menneske-handoff

Når et issue når `AFVENTER_EJER`, så postér i Slack `#direktøren` et kort, klart brief: hvad er problemet, hvad er prøvet, og præcis hvad du har brug for fra ejeren. Medtag **aldrig** hemmeligheder eller tokens. Notér i `issues.md`, og fortsæt med andre opgaver imens.
```

Erstat med:
```markdown
## Menneske-handoff

Så snart noget kræver ejerens stillingtagen — et issue når `AFVENTER_EJER`, et vækst-/optimeringsforslag venter på godkendelse, eller andet — send en Telegram-besked med det samme: et kort, klart brief om hvad problemet/forslaget er, hvad der er prøvet, og præcis hvad du har brug for fra ejeren. Medtag **aldrig** hemmeligheder eller tokens. Notér i `issues.md`, og fortsæt med andre opgaver imens.
```

- [ ] **Step 5: Opdatér "Afslut hver kørsel"-sektionen**

Find (nuværende sidste linje):
```
Afslut med en kort statusrapport i Slack `#direktøren`: hvad blev gjort, hvad er i gang, og hvad afventer ejeren. Hold det skarpt — det er ejerens daglige overblik.
```

Erstat med:
```
Afslut med en kort statusrapport via Telegram: hvad blev gjort, hvad er i gang, og hvad afventer ejeren. Hold det skarpt — det er ejerens daglige overblik.
```

- [ ] **Step 6: Verificér ingen resterende Slack-referencer**

```bash
grep -in "slack" ORKESTRATOR.md
```
Forventet: intet output.

- [ ] **Step 7: Commit (første gang denne fil versionsstyres)**

```bash
git add ORKESTRATOR.md
git commit -m "feat(orkestrator): Telegram erstatter Slack, tilføj 'gå i gang uden kontekst'-algoritme"
```

---

### Task 5: Log ændringen selv i state/issues.md

**Files:**
- Modify: `state/issues.md`

**Interfaces:**
- Consumes: commit-hash fra Task 1-4 (indsæt de faktiske hashes, når de foreligger, i stedet for pladsholdere).
- Produces: intet yderligere — dette er slutpunktet i kæden.

- [ ] **Step 1: Tilføj ny række til tabellen i `state/issues.md`**

Indsæt som ny sidste række (efter nuværende sidste `SEO-012`-række, før filens afsluttende linjeskift):

```markdown
| OPS-009 | MIDDEL | LØST | direktør | **Ny adfærd: "gå i gang med at arbejde" uden kontekst udløser nu et struktureret optimerings-scan i stedet for at direktøren selv vælger en opgave.** Design: `docs/superpowers/specs/2026-07-07-daglig-optimeringsscan-design.md`. Kontrolagenten (nu med Playwright-skærmbillede-adgang) finder både bugs og nye optimeringspunkter (design, UX, marketing-kvalitet/kvantitet); bugs auto-tildeles som hidtil, men optimeringsforslag logges altid som `NY`/"Forslag (afventer godkendelse):" og kræver ejerens eksplicitte ja, før nogen agent går i gang — aldrig automatisk `TILDELT`. Relevante forslag sendes til research-agenten med en afgrænset, konkret brief pr. punkt (ikke bred fritekst-research). `PROTOKOL.md` og `ORKESTRATOR.md` opdateret: Slack `#direktøren` erstattet af Telegram overalt (jf. OPS-006), og en generel regel tilføjet om at sende Telegram-besked, så snart noget kræver ejerens stillingtagen. Ingen automatisk tidspunkt/cron — ejeren kunne ikke oprette en Windows Task Scheduler-opgave, så scannet udløses udelukkende af ejerens egen "gå i gang"-instruktion. |
```

- [ ] **Step 2: Verificér tabellen stadig er velformet**

```bash
grep -c "^|" state/issues.md
```
Forventet: tallet er ét højere end før denne ændring (én ny tabelrække tilføjet, ingen ødelagt formatering).

- [ ] **Step 3: Commit og push alt fra denne plan samlet**

```bash
git add state/issues.md
git commit -m "chore(issues): log OPS-009 - dagligt optimerings-scan sat op"
git push origin master
```

(De fire foregående commits fra Task 1-4 er allerede skabt lokalt undervejs; dette er det samlede push til `origin/master` for hele planen.)

---

## Self-Review

**Spec-dækning:**
- §1 (trigger-algoritme) → Task 4, Step 3 (ORKESTRATOR.md-sektion).
- §2 (scan-indhold, kontrolagent/research-agent/seo-agent) → Task 1 + Task 2.
- §3 (issue-skrivning, "Forslag (afventer godkendelse)") → Task 3, Step 4 (protokolregel) + Task 4, Step 3 (algoritme nævner formatet) + Task 5 (eksempel i praksis).
- §4 (Telegram-digest-format) → dækket af Task 4 Step 3's henvisning til digest; selve beskedformuleringen er direktørens løbende arbejde, ikke en fil at redigere — ingen yderligere task nødvendig.
- §5 (generel Telegram-notifikationsregel) → Task 3, Step 3 + Task 4, Step 4.
- "Ændringer i filer"-listen i spec'en → alle 5 punkter dækket 1:1 af Task 1-5.

**Placeholder-scan:** Ingen "TBD"/"implementér senere" — al tekst, der skal indsættes, er skrevet fuldt ud i hvert step.

**Konsistens:** "Forslag (afventer godkendelse):"-formatet er identisk i Task 3 (protokolregel), Task 4 (algoritme) og Task 5 (eksempel-issue). Statusnavnene (`NY`, `TILDELT`, `AFVENTER_EJER`) matcher `PROTOKOL.md`s eksisterende skala overalt — ingen nye statusser opfundet.
