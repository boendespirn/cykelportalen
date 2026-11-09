---
name: gpx-fra-rute
description: Byg en GPX-rute til et løb/etape, der ikke har en GPX-kilde (cyclingstage), ud fra arrangørens kort, køreplan, roadbook eller profilbillede — og udgiv den kun, hvis den består kontrollen mod de officielle tal. Brug når nogen beder om "GPX fra kortet", "lav ruten selv", eller når et løb mangler GPX og derfor ikke kan få profiler/VeloViewer.
---

# GPX fra rute

Ejer-godkendt 2026-11-08. Værktøjet er `agents/gpx_builder.py`; denne fil er
opskriften. Læs `CLAUDE.md` §6–7 først — **en rute, der ikke kan verificeres,
udgives ikke.** Det er hele pointen med skillet.

## Hvornår

- Løbet/etapen har **ingen** GPX hos cyclingstage (tjek
  `climb_profile_generator.get_gpx_url_for_stage()` — cyclingstage vinder altid,
  når den findes).
- Der findes officielle oplysninger om ruten: interaktivt kort, køreplan
  (itinerary / cronotabella / horaire), roadbook eller et profilbillede med
  byetiketter.

## Kilder — i denne rækkefølge

1. **Arrangørens eget spor** (metode `track`). Åbn etapesiden med Playwright,
   kig i netværkstrafikken efter GeoJSON / KML / GPX / kodet polyline, som det
   interaktive kort tegner. Gem filen under `output/` og peg `track` på den.
   Mest præcist, for det er arrangørens egen streg.
2. **Køreplanen** (metode `itinerary`). Tættest og bedst:
   - **ASO** (letour.fr, lavuelta.es, Paris-Nice …): fanen *itinerary* på
     `/en/stage-N` — hver by + km fra start, og rækken for km 0 har ofte
     **koordinaterne** for den flyvende start. `aso_roadbook_agent.py` læser
     allerede tabellen (`tr.itinerary__*`). Tom indtil kort før løbet.
   - **RCS** (Giro, Tirreno, Lombardia): cronotabella/planimetria i
     roadbooken (udkommer om foråret). Indtil da: profilbilledets
     **byetiketter** (`km` under aksen, `højde - navn` over kurven).
3. **Kun et kortbillede**: aflæs byer og passer fra billedet og brug metode 2.
   **Aldrig** pixel-tracing af selve stregen — for upræcist.

Licens: vi bruger **fakta** (hvilke veje, hvilke byer, hvilke km), aldrig
kildebilledet. GPX'en markeres med kilde, og ruten er OSM-afledt (ODbL) —
kreditér "© OpenStreetMap-bidragydere", hvis selve GPX'en nogensinde vises.

## Spec-filen

`data/gpx/<race-slug>/stage-<N>.json`:

```json
{
  "race": "giro-d-italia-2027", "stage": 20, "official_km": 180.0,
  "method": "itinerary",
  "neutral_start": true,
  "source": "giroditalia.it/en/the-route/ — officielt profilbillede, byetiketter",
  "read_at": "2026-11-08",
  "waypoints": [
    {"name": "Pordenone", "km": 0.0, "ele": 25, "q": "Pordenone, Italia"},
    {"name": "Passo Duron", "km": 141.4, "ele": 1069, "q": "Forcella Duron, Paularo, Udine, Italia"},
    {"name": "Monte Zoncolan", "km": 180.0, "ele": 1730, "q": "Monte Zoncolan, Italia"}
  ]
}
```

- `km` er **officielle km fra start**; `ele` officiel højde, hvis kendt.
  `km: null` = styrepunkt uden kontrol.
- `q` er søgeteksten til Nominatim. Skriv **kommune/provins med** —
  navnebrødre er reglen, ikke undtagelsen ("Passo Duron" alene gav et pas i
  Dolomitterne; "Gradisca" findes to steder i Friuli).
- Kendte koordinater skrives direkte som `lat`/`lon` + `geo` (hvorfra). Scriptet
  skriver selv geokodningen tilbage i specen, så næste kørsel er ens og en fejl
  kan rettes i hånden.
- `neutral_start: false` på enkeltstarter (km 0 er rampen).
- `method: "track"` + `"track": "<sti eller URL>"` for arrangørens spor.

### Det, der afgør om ruten bliver rigtig

- **Tag alle bjergpasser med** (PM/GPM-rækkerne). Uden dem tager
  ruteplanlæggeren genvejen udenom — Vuelta 2026 etape 9 sprang Puerto de
  Tudons over (3 km i stedet for 13). Med dem lå passene 0 m fra facit.
- **Tæt køreplan.** Byer for hver ~5 km giver et spor, der ligger på den rigtige
  vej; byer for hver 25 km gør ikke (Giro 2027 etape 2 i Istrien).
- Brug køreplanens **koordinater for km 0**, hvis de står der.
- Mål på en top: en `natural=peak` uden vej flyttes automatisk ud til nærmeste
  vej (op til 900 m). Tjek i rapporten, at målet ligger rigtigt.

## Kør

```bash
python agents/gpx_builder.py --race <slug> --stage N --dry-run   # altid først
python agents/gpx_builder.py --race <slug> --stage N             # skriver data/gpx/ hvis BESTÅET
python agents/gpx_builder.py --race <slug> --all
```

Scriptet: geokoder → fugleflugt-kontrol (fanger navnebrødre) → BRouter
(profil `moped`: veje med biladgang, ingen motorvej, ingen stier) strækning
for strækning, hvor det af op til fire alternativer vælger det, der passer med
den officielle afstand → klipper blindgyder ind til bymidter og den neutrale
start af → højde fra EU-DEM 25 m → kontrol.

## Kontrollen (kan ikke slås fra)

| Kontrol | Grænse |
|---|---|
| Samlet distance mod officiel | ±2 % |
| Byernes km mod en ret linje `rute-km = a + b·officiel` | hældning ±3 %, forskydning ±3 km, hver by ±1 km fra linjen |
| Byernes højde (hvis `ele`) | ±50 m |
| Officiel højdekurve (hvis løbet har ankre i `profile_image_anchors.json`) | median ≤ 30 m, 95 %-fraktil ≤ 90 m |
| Stejleste kilometer | ≤ 25 % |

Hvorfor en linje og ikke "±1 km pr. by": selv cyclingstages GPX afviger op til
2 km fra roadbookens tal (jævn glidning + bymidter ved siden af ruten). En
strækning ad forkert vej giver derimod et spring væk fra linjen. Kontrollen
blev kalibreret på Vuelta 2026 etape 9: **facit (cyclingstage) består.**

**Bestået** → `data/gpx/<slug>/stage-N.gpx` + `.report.json`. Derefter tager
pipelinen den selv: `climb_profile_generator.download_stage_gpx()`,
`gpx_agent.py` (rutekortet) og `veloviewer_agent.py` læser den, når cyclingstage
ikke har etapen. Kør `gpx_agent.py --race <slug>` og de normale profil-jobs.

**Afvist** → kandidaten ligger i `output/gpx_kandidater/` og ses ikke af
pipelinen. **Løsn aldrig tolerancerne for at få en etape igennem.** Tilføj i
stedet flere officielle punkter (passer, byer fra køreplanen) — eller
accepter, at kilden ikke er der endnu, og rapportér det (jf.
`feedback_missing_data_sources`: manglende kilde eskaleres, den opfindes ikke).

## Hvad metode 2 realistisk kan (kalibrering 2026-11-08)

Vuelta 2026 etape 9 bygget fra køreplanen (28 punkter inkl. passer) og målt
mod cyclingstages spor: **82 % af ruten < 100 m fra facit, median 8 m**, alle
passer 0 m. Men den blev **afvist** — med rette: start (km 0–9, sløjfen via
Benidorm), Relleu–Sella og målet på Aitana (militærvej, som `moped`-profilen
ikke må køre) lå 1,5–4 km ved siden af. Giro 2027 etape 2, 7 og 20 blev
afvist af samme grunde. Forvent derfor:

- Midten af en etape med tæt køreplan: rigtig.
- Start-sløjfer i byer, lukkede/private veje (militærveje, autodromer,
  grusveje) og mål på toppe: kræver arrangørens spor (metode 1) eller flere
  officielle punkter. Gæt dem ikke på plads.

## Faldgruber, vi allerede har betalt for

- Nominatim svarer med **kommunens** midtpunkt før byen (Logatec: 4 km ved
  siden af). Scriptet foretrækker `class=place/natural/mountain_pass`.
- Bymidter i **gågader** (Ljubljana) kan profilen ikke nå → punktet flyttes.
- BRouters offentlige server rationerer ("403 Please, retry later") —
  scriptet venter selv. Kør ikke mange løb parallelt.
- Open Topo Data: højst 1.000 kald/dag ≈ 25 lange etaper pr. dag.
