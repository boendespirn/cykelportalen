# Alle løb med dansk TV — udvidelsesplan (inkl. cykelcross)

**Status:** forslag, afventer ejerens go på ét spørgsmål (afsnit 6). Skrevet 2026-10-14.
**Issue:** DATA-012. Beslægtet: DATA-011 (research-worker), OPS-010 (automatisering).

Målet: hvert løb, der sendes på en dansk streamingtjeneste eller TV-kanal, skal have en fyldestgørende landingsside — uden at nogen taster dem ind manuelt hver gang.

---

## 1. Den vigtigste opdagelse: TV-planer rækker kun 2-3 uger frem

Jeg gennemgik cykelkalenderens cross-kalender for hele sæsonen. Den rummer **182 løb** fra oktober 2026 til februar 2027 — men kun **6** af dem har en TV-markering i dag, og alle seks ligger før 1. november.

Det er ikke en mangel ved kilden. Det er sådan, broadcastere arbejder: sendeplaner offentliggøres løbende, typisk 2-3 uger før.

**Konsekvensen for planen er afgørende:** en manuel engangsgennemgang kan ikke finde "alle løb der sendes resten af året", for det er endnu ikke besluttet. Den ville give en liste, der er forældet om fjorten dage.

Den rigtige model er derfor todelt:

1. **Løbene oprettes nu** ud fra *sportskalenderen*, som er kendt et år frem.
2. **TV knyttes til løbet løbende** af workeren, efterhånden som sendeplanerne offentliggøres — hvilket den nu kan, efter rettelserne 2026-10-14.

Vi gætter altså aldrig på, om noget sendes. Vi opretter løbet, og workeren bekræfter TV, når det står der.

---

## 2. Hvilke løb — udvælgelseskriteriet

Cykelkalenderen har et **"Kun løb der sendes"**-filter, som er præcis ejerens kriterium. Men da filtret kun kender de næste par uger, bruger vi i stedet en **proxy, der holder hele sæsonen**:

> Et cross-løb kommer med, hvis det indgår i en af de fire serier, der systematisk sendes i Danmark:
> **UCI World Cup, Superprestige, X²O Trofee og HG Cross** (tidl. Exact Cross).

De fire serier er dem, HBO Max og Eurosport har rettigheder til. Lokale løb (Janev Cup, Portugal Cup, Swiss Cup, Kings CX m.fl.) udelades — de sendes ikke her, og de ville fylde 134 tomme sider.

Workeren markerer bagefter hvert løb `found`/`missing` på streaming, så vi får at vide, hvis et serieløb alligevel ikke sendes — frem for at antage det.

---

## 3. Det konkrete omfang (resten af 2026)

**Cykelcross — 24 herreløb, 24 dameløb:**

| Serie | Løb (herrer) |
|---|---|
| UCI World Cup | 8 |
| Superprestige | 7 |
| X²O Trofee | 5 |
| HG Cross | 4 |

Fra 17/10 (HG Cross Meulebeke) til 30/12 (Superprestige Diegem). Tætteste periode er julen: syv løb mellem 22. og 30. december.

**Landevej — stort set slut.** Sæsonen lukker 18.-19. oktober med Veneto Classic (oprettet), Tour of Guangxi (oprettet), Japan Cup og Chrono des Nations. Kun de sidste to mangler.

**Bane** — VM i banecykling sendes (TV 2 Sport X og HBO Max, set på oversigten 14/10). Bør vurderes separat; banedækning er et nyt produktområde, ikke bare nye rækker.

---

## 4. Cykelcross kræver en anden datamodel

Et cross-løb ligner ikke et landevejsløb, og det må siden afspejle.

**Skal IKKE have:**
- Højdeprofil. Et cross-løb er 5-8 omgange på en bane på 2-3 km. En højdekurve siger intet. `route_gpx` og `climbs` sættes til `not_applicable` i `race_data_sources`, så de aldrig havner i research-køen og aldrig tæller som et hul.

**Skal have:**
- **Streaming** — kanal og starttid. Vigtigst af alt for cross, fordi løbene ligger på hverdagsaftener og i julen.
- **Startliste** — PCS har dem.
- **Info** — bane, omgange, underlag (sand, mudder, brosten), vejr.
- **Resultater** — og her ligger det særlige: **seriens stilling**.

**Pointsystemet.** Hver af de fire serier har sin egen samlede stilling, og det er dét, fans følger hen over sæsonen — ikke det enkelte løb. En cross-landingsside uden seriestillingen er halv.

Vores `classifications`-tabel findes allerede (bruges til GC, bjerg, points i etapeløb). Den kan rumme en serie-stilling, hvis vi knytter den til serien frem for til løbet. Det kræver en lille udvidelse, ikke en ny tabel — men det er en designbeslutning, der bør tages bevidst.

**`race_type`.** I dag findes `stage_race` og `oneday`. Cross skal have sin egen værdi, `cyclocross`, så frontenden kan vælge layout og `race_completeness.py` kan vurdere det rigtigt. Uden den ville hvert cross-løb stå som "mangler højdeprofil" for evigt.

---

## 5. Sådan kører det bagefter

Når løbene er i databasen, gør de to eksisterende workere resten:

1. **`datakilde_research`** (dagligt kl. 03:00 UTC) ser de nye løb som "aldrig forsøgt" og lægger dem øverst i køen. Den finder startliste og resultater på PCS gratis, og streaming på cykelkalenderen. Spærretiden strammer selv til 1/uge, når der er under en måned til løbet, og 1/dag den sidste uge — altså præcis når sendeplanen offentliggøres.
2. **`tv_agent`** skriver sendetiderne til `broadcast_schedule`. Den finder nu også de løb, cykelkalenderen ikke selv har koblet til sin løbsdatabase — det var netop den fejl, der skjulte Tour of Guangxi på HBO Max.
3. **`raesinfo`/`fuld_forberedelse`** henter etapedata og startliste via skemalæggerens udløsere (7 dage / 48 t / 24 t / 6 t før).

Ingen af delene kræver, at nogen trykker.

---

## 6. Ét spørgsmål, der skal besvares først

**Skal damerløbene med?**

Databasen rummer i dag 36 løb — alle herrer. De 24 dameløb i cross-serierne køres samme dag, samme bane, og cykelkalenderen fører dem som selvstændige løb.

Det er ikke en teknisk beslutning, men en produktbeslutning: det fordobler antallet af sider, og det åbner et dækningsområde, siden ikke har i dag. Gør vi det halvt — dameløb uden startliste eller resultater — er det værre end slet ikke at have dem.

---

## 7. Rækkefølge

| Trin | Indhold |
|---|---|
| 1 | `race_type = 'cyclocross'` + `not_applicable` for `route_gpx`/`climbs` |
| 2 | Opret de 24 herreløb (+ 24 dameløb, hvis ja) og Japan Cup + Chrono des Nations |
| 3 | Kør `datakilde_research --seed` og lad køen tage dem |
| 4 | Frontend: cross-layout uden højdeprofil, med bane-info |
| 5 | Serie-stilling i `classifications` |

Trin 1-3 kan gøres i dag. Trin 4-5 er produktarbejde, der kan følge efter — landingssiderne er brugbare uden dem, bare ikke færdige.
