# Opgave: cross-layout i frontenden

**Til:** en frisk session. **Fra:** session 2026-10-14. **Issue:** DATA-012, trin 4-5.
Alt nedenfor er verificeret i den session, der skrev dette — men **tjek koden igen**, den kan have flyttet sig.

---

## Situationen

Databasen rummer nu **24 cykelcross-løb** (17/10-30/12 2026) med `races.race_type = 'cyclocross'`.
Det første køres **lørdag 17/10** (HG Cross Meulebeke, HBO Max).

**Frontenden kender ikke løbstypen.** Den forgrener kun to steder:

```ts
cykel-frontend/app/[slug]/page.tsx:482   const isOneDay = race.race_type === "oneday" || race.race_type === "one_day";
cykel-frontend/app/[slug]/page.tsx:598   const isOneDay = race.race_type === "oneday";
```

Et cross-løb er hverken `oneday` eller `one_day`, så det falder i **etapeløbs-grenen** og vises i dag som et etapeløb med klassement og etapeliste. Det er den fejl, opgaven skal rette.

`api.py` leverer allerede `race_type` (linje ~670 og ~716), så der mangler ingen backend-ændring for selve forgreningen.

---

## Hvad en cross-side SKAL vise

Prioriteret efter, hvad en cykelfan kommer efter:

1. **Hvornår og hvor kan jeg se det** — kanal og starttid. Vigtigst af alt, fordi cross køres på hverdagsaftener og hen over julen. Data ligger i `broadcast_schedule` (`broadcaster`, `start_time`, `broadcast_date`).
2. **Startliste** — samme komponent som landevej; PCS har dem.
3. **Baneinfo** — omgange, underlag (sand, mudder, brosten), længde pr. omgang. *Findes ikke i databasen endnu* — se "Åbne beslutninger".
4. **Resultat** — løbets podie.
5. **Seriens stilling** — se nedenfor.

## Hvad den IKKE skal vise

- **Ingen højdeprofil.** Et cross-løb er 5-8 omgange på en bane på 2-3 km; en højdekurve siger intet. Billedet gates i dag af `elevation_image_source === "generated"` (hjælperen omkring `page.tsx:37-42`), og cross-løbene har ingen, så det falder allerede væk af sig selv — men gør det **eksplicit**, så ingen senere kommer til at generere ét.
- **Intet klassement/GC**, ingen etapeliste, ingen bjerg- eller pointtrøje.
- **Ingen stigninger.** `race_data_sources` har allerede `route_gpx` og `climbs` som `not_applicable` for cross.

---

## Åbne beslutninger (tag dem bevidst — spørg ejeren)

**1. Seriens samlede stilling.** Det er dét, fans følger hen over vinteren — ikke det enkelte løb. De fire serier er UCI World Cup, Superprestige, X²O Trofee og HG Cross; serien står i `races.category`.

`classifications`-tabellen findes og bruges til GC/bjerg/point i etapeløb. Den kan rumme en serie-stilling, hvis den knyttes til **serien** frem for til løbet. Lille udvidelse, men en rigtig datamodel-beslutning — ikke noget man laver i forbifarten.

**2. Baneinfo har ingen kolonne.** Omgange og underlag findes ikke i `stages`. Mulighederne er en ny kolonne, genbrug af `stages.description`, eller at droppe det i første omgang. Siden er brugbar uden.

---

## Acceptkriterier

- [ ] Et cross-løb vises med sit eget layout, ikke som etapeløb
- [ ] Ingen højdeprofil, intet klassement, ingen etapeliste
- [ ] TV-kanal og starttid står øverst og er det første, man ser
- [ ] Startliste vises, når den findes — ellers en ærlig tom-tilstand
- [ ] `oneday` og `stage_race` er **uændrede** (tjek før og efter)
- [ ] Mobilvisning holder (cross-trafik er aften- og mobiltung)

---

## Sådan ser du det live

```
https://klassementet.dk/hg-cross-meulebeke-berencross-2026   (17/10, HBO Max)
https://klassementet.dk/uci-cx-world-cup-koksijde-2026        (20/12)
https://klassementet.dk/superprestige-diegem-2026             (30/12)
```

Kontrolløb, der IKKE må ændre sig: `tour-de-france-2026` (etapeløb), `il-lombardia-2026` (endagsløb), `veneto-classic-2026` (endagsløb med egen profil).

---

## Baggrund, hvis du får brug for den

- `docs/tv-daekning-plan.md` — hvorfor netop disse 24 løb, og hvorfor TV knyttes på løbende
- `state/issues.md` → DATA-012
- `CLAUDE.md` §5 — brandets krav til layoutet: rent, hurtigt, kun det vigtige
