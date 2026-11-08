# Giro d'Italia — kildeguide

*Etapeløb · 2.UWT · 2027: 8.–30. maj, Trieste → Rom.*

Opdateret 2026-11-08, da 2027-ruten blev lagt ind (præsenteret 3/11). Første
Grand Tour, vi forbereder for anden gang.

## Identitet

| Felt | Værdi |
|---|---|
| Vores DB-slug | `giro-d-italia-2027` |
| PCS-slug | `giro-d-italia` (uændret fra 2026) |
| PCS-løbsside | https://www.procyclingstats.com/race/giro-d-italia/2027 |
| Officiel rute | https://www.giroditalia.it/en/the-route/ — etaper, beskrivelser og profilbilleder pr. etape |
| GPX (cyclingstage) | `https://www.cyclingstage.com/giro-2027-gpx` — **findes ikke endnu** (404 2026-11-08). Workeren opdager den selv |
| ASO-roadbook | nej (RCS-løb) |

## Hvad 2027 fik på dag 1 (2026-11-08)

| Data | Kilde | Status |
|---|---|---|
| Løb og 21 etaper (dato, start, mål, distance) | PCS + officiel side | ✓ — PCS's stednavne og etapetyper rettet til arrangørens (7 og 15 er enkeltstarter) |
| Højdemeter | Arrangørens tekster | 8 etaper (1, 2, 3, 5, 10, 14, 16, 19); resten står tomme frem for at blive gættet |
| Hel-etape-højdeprofil | Digitaliseret fra giroditalia.it's profilbilleder, stil `"giro"` | ✓ 21/21, valideret mod officielle højder (max 3-57 m) og mod "ingen kilometer over 25 %" |
| Rutetekst og etapetekster + "Værd at vide" | Skrevet ud fra arrangørens profiler, stigningsbilleder og statistik | ✓ 21/21 |
| Stigninger (`stage_climbs`) | — | **mangler med vilje.** Kræver GPX (verifikation) og PCS' `-climb`-billeder; ingen af dem findes endnu |
| Startliste, lokale favoritter | PCS | kommer, når holdene udtager |

## Fælder fundet i 2027-materialet

- **Etape 1's billede er selvmodsigende:** Hrvatini og Prebeneg står ved km
  134,0 og 142,6, men er tegnet ved km ≈136 og ≈151. De to ankre er udeladt;
  kurven er kalibreret på de etiketter, der stemmer med aksen.
- **Monte Livata (E9):** profilen siger 1.352 m i mål, stigningsbilledet 1.368 m.
  Profilen bruger sit eget tal.
- **Zum Zeri (E12):** profilen siger 8,7 km og max 13 %, stigningsbilledet 8,4 km
  og max 14 %. Teksterne bruger stigningsbilledet (det detaljerede).
- **Etape 8's profil har ingen alt-tekst** på rutesiden, og stigningsbillederne
  til etape 14, 16, 18 og 20 heller ikke — de findes ved tidsstemplet i filnavnet.
- **GPM-prikken skjuler toppen:** den sorte prik på hver GPM-top ligger oven på
  kurven; digitizeren bruger prikkens centrum, men kun når den ligger PÅ kurven
  (den fede tekst "13.1 km / 7.4%" ved målet er også et tæt sort felt).

## Tjekliste til resten af vejen

| Hvornår | Hvad | Hvem |
|---|---|---|
| Hver morgen | Er GPX kommet? → `fuld_forberedelse` med det samme | workeren (`datakilde_research`) |
| 30 / 14 / 7-1 dage før | Fuld forberedelse — rute, stigninger, profiler, startliste, lokale favoritter | workeren |
| 21 og 10 dage før | Startliste | workeren |
| 48 t / 6 t / start | Startliste | workeren |
| 24 t før | TV-tider + ræsinfo | workeren |
| Efter mål | Resultat, klassement, etapereferat | workeren |
| Efter sidste etape | Samlet ræsreferat | workeren |
| Når stigningerne er hentet | Læs etapeteksterne igen: de nævner stigningerne ud fra arrangørens tal, og PCS kan have andre længder | ejeren / en kontrolkørsel |

---

Se [README.md](README.md) for metoden og de generelle fælder.
