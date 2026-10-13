# Automatiseringen — sådan kører den

Opdateret 2026-10-13, da systemet gik i luften. Planen, der lå til grund, står i
[`automatisering-plan.md`](automatisering-plan.md); **denne fil beskriver det,
der faktisk kører.**

Alle klokkeslæt er **UTC**. Dansk tid er UTC+2 om sommeren, UTC+1 om vinteren.

---

## 1. Hvad kører hvor

| Del | Hvor | Hvad den gør |
|---|---|---|
| Frontend | Vercel | klassementet.dk |
| API | Railway, service **`web`** | `api.py` — læser databasen, serverer admin-dashboardet |
| **Skemalægger** | Railway, service **`worker`** | `scheduler.py` — lægger forfaldne jobs i kø hvert 5. minut |
| **Runner** | Railway, service **`worker`** | `runner.py` — henter jobs fra køen og udfører dem, poller hvert 15. sekund |
| Kø og data | Supabase | tabellen `agent_runs` er køen; alt andet er dataen |

Worker-servicen kører de to processer side om side (`deploy/worker/start.sh`).
Dør én af dem, dør containeren, og Railway starter den igen — en halvt levende
worker, hvor køen fyldes uden at blive tømt, er værre end en genstart.

Imaget er Playwrights eget (`deploy/worker/Dockerfile`), så Chromium følger med.
API-servicen bygges som hidtil og er urørt.

**Ejerens PC indgår ikke længere.** `runner.py` behøver ikke køre lokalt.

## 2. Hvad udløser hvad — og hvornår

### Før løbet (pr. løb, regnet fra løbets startdato kl. 10 lokal tid)

| Tidspunkt | Job | Hvorfor netop der |
|---|---|---|
| **7 dage før** | `fuld_forberedelse` | Rute, stigninger, profiler og tekst. En uge til at opdage, at en kilde mangler |
| **48 timer før** | `startliste` | PCS har sjældent hele feltet tidligere |
| **24 timer før** | `tv_tider` + `raesinfo` | TV-tider offentliggøres sent, og ruten kan nå at ændre sig |
| **6 timer før** | `startliste` | Sene afbud |
| **Ved start** | `startliste` | Endelige startnumre |

### Under løbet (pr. etape — et endagsløb er etape 1)

Resultatjagten kører i **to lag**, fordi vi ikke kender løbets tidszone: 20 af
2026-sæsonens 36 løb har tom `country_code`, heriblandt Guangxi, Tour Down Under
og UAE Tour.

1. **Kender vi det forventede måltidspunkt** — fra TV-sendingens sluttid, eller
   fra etapens starttid plus distance ÷ 40 km/t — så: **mål + 1 time**, derefter
   **hver halve time, 6 gange**.
2. **Altid derudover:** en **timevis fejning 05:00-21:00 UTC** på løbsdagen plus
   **00:00, 01:00 og 02:00** dagen efter, så en sen europæisk etape også er
   dækket.

Højst **20 forsøg pr. etape**, og hele jagten stopper i samme øjeblik, etapen
har et resultat i databasen. Aflyste etaper (`data_status = cancelled`)
forsøges aldrig.

### Efter løbet

| Tidspunkt | Job |
|---|---|
| Sidste etapedag kl. 20 lokal tid | `raesreferat` (kun etapeløb) |

### Uafhængigt af løb

| Tidspunkt | Hvad |
|---|---|
| **06:00 UTC dagligt** | Telegram-sammendrag: hvad kørte i går, hvad fejlede, hvilke kørte etaper mangler stadig resultat |

## 3. Beskeder

| Hvornår | Kanal | Indhold |
|---|---|---|
| Et job fejler (exit ≠ 0, eller dommen `error`) | Telegram, straks | Job, løb, etape, exit-kode og de sidste seks linjer af loggen |
| Hver morgen 06:00 UTC | Telegram | Gårsdagens kørsler, fejl, og **kørte etaper uden resultat** |

Advarsler sender ikke besked. En kanal, der bipper ved hvert normalt job, holder
man op med at læse — de står i stedet i `/admin/pipelines`.

Det daglige sammendrag er det vigtigste af de to: en fejlet kørsel melder sig
selv, men **dét, der aldrig kørte, gør ikke** — og det var præcis Vuelta-hullet,
hvor fire etaper stod uden resultat i en måned.

## 4. Sikkerhed og spærrer

- **Skemalæggeren udfører intet.** Den skriver kun rækker i `agent_runs`,
  nøjagtig som knappen i admin. Runneren modtager aldrig en kommando — kun et
  `job_key`, som den selv slår op i `agent_catalog.JOBS`. Et ukendt job afvises.
- **Ét job ad gangen.** To tunge Playwright-kørsler samtidig løb tør for
  hukommelse under Vuelta-backfillen.
- **Samme regel kan ikke køe det samme job to gange.** Reglens navn står i
  `agent_runs.args.regel`, og skemalæggeren tjekker de sidste to døgn, før den
  skriver.
- **To timers tilbageblik:** var skemalæggeren nede, da et tidspunkt passerede,
  tages jobbet med alligevel.
- **Afbryd-knappen i admin virker uændret**, også på skemalagte kørsler.

## 5. Sådan ser du efter den

```bash
railway logs --service worker          # hvad laver den lige nu
railway status                         # kører servicen
python scheduler.py --dage 14          # hvad er planlagt de næste 14 dage
python scheduler.py --dry-run          # hvad er forfaldent lige nu (skriver intet)
python agents/pcs_source.py --tjek     # svarer alle PCS-URL'er stadig
```

Kørslerne med deres fulde log står som altid i `/admin/pipelines`.

**Sæt den på pause:** stop `worker`-servicen i Railway. Køen bliver stående, og
intet går tabt — jobs tages, når den starter igen.

## 6. Det, der IKKE er automatiseret

- **Referat af endagsløb.** PCS har ingen LiveStats-tidslinje for dem, så
  kilden findes ikke (RES-008). Blokken på løbssiden tænder af sig selv, hvis
  vi en dag får en kilde.
- **Nye GPX-kilder** kræver en kodeændring (`CYCLINGSTAGE_GPX_PAGES`), fordi en
  ny kilde skal verificeres, før den må bruges. `Datakilde-scan` finder dem og
  skriver dem i loggen; den skriver aldrig selv.
- **Vagthund.** Dør workeren helt, er der ingen, der siger til — det daglige
  sammendrag udebliver bare. En GitHub Action, der spørger hver time, er næste
  skridt.
- **Kalenderen for næste sæson.** 2027-løbene skal oprettes med `pcs_url`, før
  skemalæggeren har noget at regne på. Kør `agents/pcs_source.py --tjek --aar 2027`
  før sæsonstart: en tom PCS-side betyder forkert slug, ikke "ikke kørt endnu".
