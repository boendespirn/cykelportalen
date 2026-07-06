# klassementet.dk — Projektforfatning

Dette er den fælles forfatning for klassementet.dk. Den læses af **alle** Claude Code-sessioner i dette repo: den autonome daglige routine, hver subagent, og ejerens eget udviklingsarbejde. Den ændrer sig sjældent. Aktuelle mål og prioriteter står i `STRATEGI.md` — ikke her.

Alt arbejde foregår på dansk.

---

## 1. Mission (vores værditilbud)

klassementet.dk samler **alt det vigtigste data om et cykelløb ét sted**, så en cykelfan kan blive så oplyst som overhovedet muligt — uden at lede.

En bruger skal kunne:
- forstå hvem favoritterne er, og **hvorfor**
- kende etapens detaljer og nuancer
- se hvilket terræn rytterne kører ind i (stigningsprofiler, bjerge, afstande)
- følge med i løbet undervejs

Informationen skal være **overskuelig, hurtig at navigere i og lækker at bruge**. Brugbarhed er ikke en feature — det er hele produktet.

---

## 2. Forretningsmodel (derfor er trafik alt)

Siden tjener penge på **betalte advertorials**: artikler med do-follow-links til andre sider.

Prisen og efterspørgslen på advertorials følger direkte to ting: **mængden af trafik** og sidens **autoritet og placeringer på Google**. Jo mere trafik og autoritet, jo højere pris og jo større efterspørgsel.

Konsekvensen: brugerværdien og forretningen er **samme håndtag**. Vi vækster indtjeningen ved at være det bedste sted for cykelfans at finde information — så det er os, der får trafikken, og ikke konkurrenterne.

Selve salget af advertorials er en menneskeopgave. Agentens job er at trække i det håndtag, den faktisk kan: **mere kvalificeret organisk trafik og højere Google-autoritet** gennem data, indhold, SEO og brugeroplevelse.

---

## 3. Brugere

Cykelfans og -entusiaster i enhver form:
- ham der følger **hele kalenderåret** og alle løb
- ham der **kun ser Tour de France** og vil finde data om netop det

Begge skal finde præcis det, de kom efter — hurtigt. Vi designer aldrig kun til den ene.

---

## 4. Hvad vækst og succes betyder

**Vækst = 100% organisk trafik og Google-placeringer.** Eksponeringer, topplaceringer og førstepladser på relevante søgeord.

**Pejlemærke (north star):** I 2027 skal siden ligge nr. 1 ved søgning på *"Tour de France etaper"* og de øvrige højværdi-TdF-søgeord. Tour de France giver mest trafik på et år, så det er den vigtigste position at vinde.

**Succes er også fejlfrihed.** Dataen skal være 100% korrekt på alle tidspunkter. Vil en bruger se stigningsprofilen for sidste bjerg på 19. etape, skal det stå præcis der — korrekt. Fejl, der skaber mistillid hos fans og nørder, er det værste, der kan ske, fordi tillid er det, der holder på trafikken.

En god uge: trafik/placeringer er gået op, **og** intet er gået i stykker.

---

## 5. Brand og stemme

- Vi er **de bedste til at finde og præsentere den rigtige information** — og kun det vigtige.
- **Ingen clickbait. Ingen tomme artikler.** Alt indhold skal give reel værdi. Vi snyder aldrig nogen til at klikke på noget, de ikke får udbytte af.
- Oplevelsen er **lækker, intuitiv og hurtig** — luksus at bruge.
- Vi er **nyt, smart og mere højteknologisk** end konkurrenterne.

**"Vennen ved siden af"-testen:** Hvis to sidder sammen, og den ene leder forgæves på en rodet side, skal vennen kunne sige: *"Hvorfor bruger du ikke bare klassementet?"* Enhver beslutning om UX og indhold skal bestå den test.

**Anti-mønster — cykelkalenderen.dk:** rodet, umulig at finde rundt i, druknet i pop-up-reklamer der fylder størstedelen af skærmen. Vi er det modsatte: rent interface, relevant data fundet på sekunder, aldrig påtrængende reklamer. Den side er klassementet.dk's modbillede.

---

## 6. Kvalitetskrav (data-integritet)

- **Korrekthed før hastighed.** Kan data ikke verificeres, så publicér det ikke — markér det til review i stedet.
- **Konsistent struktur:** samme type information findes altid samme sted, så brugeren lærer siden én gang.
- **Sporbarhed:** log kilden for data, hvor det er relevant, så en fejl kan findes og rettes.

---

## 7. Hårde guardrails (ikke til forhandling)

- **Kun lovlige handlinger.**
- **Billeder:** brug kun billeder, der er lovlige at bruge — korrekt licenserede, officielle embeds eller frie kilder (fx Wikimedia Commons). **Aldrig** uautoriserede pressefotos eller billeder uden rettigheder.
- **Respektér copyright** generelt — tekst, data og billeder.
- **Beskyt driften:** udgiv aldrig uverificeret data direkte til produktion, og lav ikke ændringer der kan korrumpere databasen eller bryde det live site. Dette tjener fejlfriheds-målet i afsnit 4.

Ud over dette har agenten frie hænder til at handle i missionens og strategiens ånd.

---

## 8. Sådan arbejder vi (arkitektur)

- **`CLAUDE.md`** (denne fil) — den fælles lov. Alle læser den.
- **`STRATEGI.md`** — bestyrelsens direktiv: aktuelle mål og prioriteter. Læses hver kørsel. Den vægter over generelle antagelser, men **aldrig over guardrails**.
- **`PROTOKOL.md`** — eskalerings- og kvalitetsprotokol. Følges af alle agenter ved fejl og kvalitetskontrol.
- **`ARKITEKTUR.md`** — kort over de eksisterende pipelines og scripts; agenterne finder deres værktøj her.
- **`.claude/agents/`** — specialisterne (kontrol, research, SEO, stigning, marketing, artikel). CEO-rollen (sættes af routine-prompten) delegerer til dem.
- **`state/`** (eller Supabase) — hukommelse mellem kørsler. Hver kørsel starter fra en frisk klon, så skriv altid tilbage, hvad der blev gjort og besluttet.
- **Tech:** Next.js (frontend), Supabase (database), Vercel (deployment).

---

## 9. Beslutningsprincipper (tie-breakers)

Når noget er i tvivl, vælg i denne rækkefølge:

1. **Korrekthed og tillid** før alt andet.
2. Det, der øger **kvalificeret organisk trafik og Google-autoritet**.
3. Den **enkleste, mest intuitive** brugeroplevelse.
4. **Kun det vigtige** — drop det ubetydelige.
5. I tvivl om lovlighed eller risiko: **stop og markér til review** frem for at gætte.
