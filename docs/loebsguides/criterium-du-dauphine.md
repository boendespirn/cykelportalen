# Tour Auvergne Rhône-Alpes (Critérium du Dauphiné) — kildeguide

*Etapeløb · UCI WorldTour · kørt 2026-06-07 – 2026-06-14 i 2026.*

Skrevet ud fra 2026-sæsonen 2026-10-12. Brug den som udgangspunkt for 2027 — men **verificér URL'erne igen**, før sæsonen går i gang: PCS skifter slugs uden varsel.

## Identitet

| Felt | Værdi |
|---|---|
| Vores DB-slug | `criterium-du-dauphine-2027` |
| PCS-slug | `tour-auvergne-rhone-alpes` |
| PCS-løbsside | https://www.procyclingstats.com/race/tour-auvergne-rhone-alpes/2026 |
| PCS-resultat | https://www.procyclingstats.com/race/tour-auvergne-rhone-alpes/2026/stage-N/result |
| GPX (cyclingstage) | konfigureret |
| ASO-roadbook | nej (ikke et ASO-løb) |
| Kendt af startliste-agenten | **nej — tilføj PCS-slug til `startlist_agent.PCS_RACE_SLUGS`** |
| Kendt af TV-agenten | ja |

## Hvad vi fik i 2026

| Data | Status |
|---|---|
| Startliste | 170 ryttere |
| Etaper i databasen | 8 |
| Etaper med distance | 8 |
| Etaper med GPX-rute | 0 |
| Egengenereret højdeprofil | 0 |
| Stigninger | 28 (12 med profil) |
| Etaper med resultat | 7 / 8 |
| Klassementsrækker | 392 |
| Etapereferater | 0 |
| TV-sendinger | 26 |

## Noter

- **PCS har omdøbt løbet til `tour-auvergne-rhone-alpes`.** Det gamle `criterium-du-dauphine` svarer tomt. Etape-URL'erne stod med det gamle slug og er rettet 2026-10-13; `races.pcs_url` var allerede rigtig.
- Etape 3 var en **holdenkeltstart**: PCS' aktive fane viser en HOLD-rangliste uden rytterkolonne, så der findes intet rytter-resultat at gemme. Klassementerne efter etapen hentes alligevel.

## Tjekliste til 2027

| Hvornår | Hvad | Job |
|---|---|---|
| Før sæsonen | Verificér PCS-slug og GPX-kilde (de skifter) | `Datakilde-scan` |
| 1 uge før | Startliste + etapedata + stigninger + profiler | `Fuld forberedelse` |
| 48 t før | Startliste igen (PCS har først hele feltet tæt på) | `Startliste` |
| 24 t før | TV-tider | `TV-tider` |
| 6 t før | Sidste tjek af startliste og rute | `Startliste`, `Ræsinfo` |
| 1 t efter mål (pr. etape) | Resultat og klassement | `Resultater` |
| Hver ½ time indtil resultatet står | Resultat igen | `Resultater` |
| Efter sidste etape | Samlet ræsreferat | `Ræsreferat` |

---

Se [README.md](README.md) for metoden og de generelle fælder.
