# klassementet.dk — Eskalerings- og kvalitetsprotokol

Denne fil definerer, hvordan problemer **opdages, routes, eskaleres og lukkes** på tværs af agent-teamet. Alle agenter følger den; direktøren håndhæver den. Den står under `CLAUDE.md` (loven) og `STRATEGI.md` (direktivet) — guardrails i `CLAUDE.md` kan aldrig overtrumfes.

---

## Roller i kæden

- **Kontrolagenten** — opdager fejl og optimeringspunkter via kritiske kontroller og rapporterer til direktøren.
- **Direktøren** — router, prioriterer, logger, eskalerer og kommunikerer med ejeren.
- **Udførende agenter** (fx stigningsagenten, SEO-agenten, marketing-agenten) — forsøger at løse tildelte problemer.
- **Research-agenten** — visionerer og researcher løsninger og bedre metoder, og leverer et brief.
- **Ejeren (dig)** — giver en ledetråd, når agenterne ikke kan løse det selv.

---

## Fejl-loggen: `state/issues.md`

Den eneste kilde til sandhed for problemer på tværs af kørsler. Hver kørsel starter fra en frisk klon uden hukommelse — derfor lever **alt** her, intet kun i hukommelsen.

Hvert issue har: `id`, `dato`, `kilde` (hvem opdagede det), `beskrivelse`, `status`, `forsøg`, `ansvarlig agent`, `seneste opdatering`, `løsning`.

**Statusser:** `NY → TILDELT → ESKALERET → AFVENTER_EJER → LØST` (samt `HENLAGT`).

**Direktørens første handling hver kørsel:** læs `state/issues.md` og tjek om ejeren har svaret på en tidligere Telegram-besked, og fortsæt derfra.

---

## Flowet

1. **Opdagelse:** kontrolagenten (eller en hvilken som helst agent) finder en fejl → rapporterer til direktøren med beskrivelse **og bevis**.
2. **Logning:** direktøren opretter/opdaterer et issue i `state/issues.md` (status `NY`).
3. **Tildeling:** direktøren tildeler issue til den rette udførende agent (fx stigningsagenten for stigningsdata) → status `TILDELT`. Notér forsøgsnummer.
4. **Forsøg:** agenten forsøger at løse det.
   - Løst **og** verificeret af kontrolagenten → status `LØST`.
   - Ikke løst → tilbage til direktøren.
5. **Eskaleringsgrænse:** efter **2 mislykkede forsøg** (eller hvis agenten erklærer sig blokeret) eskalerer direktøren → status `ESKALERET` → aktiverer research-agenten. *(Juster tallet her, hvis du vil.)*
6. **Research:** research-agenten leverer et brief — problemforståelse, mulige løsninger, og **præcist hvad den mangler** for at komme videre.
   - Konkret, implementerbar løsning → direktøren tildeler implementering → tilbage til trin 4.
   - Mangler input fra ejeren → status `AFVENTER_EJER` → trin 7.
7. **Menneske-handoff:** direktøren sender en Telegram-besked (samme kanal som al anden ejer-kommunikation, jf. OPS-006) med et kort, klart brief: hvad er problemet, hvad er prøvet, og præcis hvad der ønskes fra ejeren. **Aldrig hemmeligheder eller tokens i beskeden.** Notér i `issues.md`. Denne regel gælder bredt: så snart noget kræver ejerens stillingtagen — ikke kun ved `AFVENTER_EJER` — sender direktøren besked med det samme, frem for at vente til ejeren selv spørger.
8. **Ejer-svar:** ejeren svarer i tråden. Ved næste kørsel læser direktøren `#direktøren`, samler svaret op, opdaterer issue og fortsætter (typisk tilbage til research eller implementering).
9. **Lukning:** når kontrolagenten har verificeret rettelsen, sætter direktøren status `LØST` og noterer løsningen i `issues.md`, så vi lærer af den.

---

## Regler

- **Korrekthed og tillid over alt** (jf. `CLAUDE.md`).
- **Intet fix går live, før kontrolagenten har verificeret det** (definition of done).
- **Maks 2 forsøg pr. niveau** før eskalering — undgå uendelige loops mellem direktør og agent.
- **Alt skrives i `issues.md`** — kørsler er stateless, så intet må kun leve i hukommelsen.
- **Telegram-beskeder:** korte, konkrete, ét issue ad gangen, aldrig følsomme data.
- **Vækst-/optimeringsforslag kræver altid ejerens eksplicitte godkendelse før `TILDELT`** — i modsætning til almindelige bugs/datafejl, som auto-tildeles som normalt. Sådanne forslag mærkes i beskrivelsen med "Forslag (afventer godkendelse):" og forbliver `NY`, indtil ejeren siger ja.
- **Commit og push pr. opgave-statusændring.** Så snart et issues.md-issue skifter status (fx TILDELT → LØST), commit og push den ændring med det samme — batch ikke flere issues sammen i én afsluttende commit. Ejeren følger fremdrift live på `klassementet.dk/admin/opgaver`, som læser `issues.md` fra det seneste deploy; uden løbende push/deploy er dashboardet bagud.

---

## Definition of done

- **Udførende agent:** problem løst + kort bevis + kontrolagenten kan verificere.
- **Research-agent:** brief med problem, løsningsforslag og præcist behov.
- **Direktør:** `issues.md` opdateret + ejeren informeret, når det er relevant.
