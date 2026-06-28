# klassementet.dk — STRATEGI (bestyrelsens direktiv)

*Sidst opdateret: juni 2026*

Dette er det foranderlige direktiv. Det læses **hver kørsel** og vægter over generelle antagelser — men **aldrig over de hårde guardrails i `CLAUDE.md`**. Når virkeligheden ændrer sig, opdateres denne fil; `CLAUDE.md` står fast.

---

## Nuværende fase: Operationalisering

Strategien lige nu er at få **produktet og baglandet til at køre fuldstændigt**, så det Claude-baserede agent-team kører nærmest fuldt operationelt. Vi kører tests og sætter systemer op — samtidig med at vi bygger på de tre vigtigste initiativer herunder.

**Dette er en midlertidig fase.** Når botsene pålideligt leverer det forventede resultat, skifter direktivet fokus til ren vækst (se exit-kriteriet til sidst). Indtil da er målet at få motoren til at virke.

Den dobbelte hensigt gælder hele tiden: eksekvér hurtigt på at få **trafik nu**, og byg samtidig mod den store, langsigtede **SEO-trafik** — og giv altid alle besøgende den bedste oplevelse med korrekt, god data.

---

## Sidens nuværende tilstand (kendte problemer)

- **Climbfinder:** mange bugs i at finde og vise de rigtige stigningsprofiler.
- **Marketing:** der er endnu ingen fuldt automatiseret marketing, der faktisk kører automatisk, når ejeren godkender artikler.
- **Det største problem — indeksering:** Google indekserer ikke siden. Den vurderer p.t. siderne til ikke at være vigtige nok ift. andre sider. Uden indeksering ingen eksponeringer, ingen trafik — og dermed ingen forretning. Dette er den eksistentielle flaskehals.

---

## Aktuelle prioriteter (i rækkefølge)

### 1. Indeksering — den eksistentielle flaskehals

- Implementér **SEO native i Next.js** (Metadata API, `sitemap.ts`, JSON-LD struktureret data), tilslut Google Search Console, og opsæt IndexNow.
- Brug AI til at arbejde med **SERP-/meta-tekster** for at maksimere click-through rate, når Google belønner os med eksponeringer.
- Forbedr sidens **sitemap** (native i Next.js) for at hjælpe Google på vej.
- Parallelt: producér **ca. 3 nyheder om ugen**, der hver linker **internt** til en anden relevant side (intern linking styrker indeksering og autoritet).
  - **Workflow:** artikel-/marketingagenten præsenterer sine **10 bedste artikelidéer** om ugen → **ejeren vælger**, hvilke der publiceres. Menneskelig godkendelse er påkrævet før publicering.
- **Mål:** fortsæt ugentligt, indtil **hele siden er indekseret**.

### 2. Marketing-setup — automatiseret trafikvækst

- Byg et marketing-setup, så siden kan vækste med trafik via **Facebook, Instagram og TikTok**.
- Slå det vigtigste op på de medier på en god måde, der **styrker brandet — aldrig skader det** (jf. brand-afsnittet i `CLAUDE.md`: lækkert, kun det vigtige, ingen clickbait).

### 3. Data-korrekthed — stigningsagenten

- Sikr at al vores data passer — herunder at vi viser de **aktuelle bjergstigninger for Tour de France** korrekt.
- Opdater **stigningsagenten** med nye metoder til at finde de rigtige stigningsprofiler for de enkelte stigninger, rytterne skal køre op ad i et løb. *Den detaljerede fremgangsmåde ligger i stigningsagentens egen fil.*
- **Tidskritisk:** Tour de France 2026 køres **4.–26. juli**. Da TdF er årets største trafikbegivenhed og sidens north star, har korrekt stigningsdata for løbet reelt en deadline ved løbsstart. Overvej at rykke denne prioritet frem i ugen op til 4. juli.

---

## Exit-kriterie for denne fase

Når agent-teamet pålideligt leverer de forventede resultater — indeksering er på skinner, marketing kører automatisk efter godkendelse, og dataen er korrekt — opdateres dette direktiv, og fokus skifter til **ren vækst**: trafik og Google-placeringer mod målet om nr. 1 på *"Tour de France etaper"* i 2027.
