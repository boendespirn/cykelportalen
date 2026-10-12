# E3 Saxo Classic — kildeguide

*Endagsløb · UCI WorldTour · kørt 2026-03-27 i 2026.*

Skrevet ud fra 2026-sæsonen 2026-10-12. Brug den som udgangspunkt for 2027 — men **verificér URL'erne igen**, før sæsonen går i gang: PCS skifter slugs uden varsel.

## Identitet

| Felt | Værdi |
|---|---|
| Vores DB-slug | `e3-saxo-classic-2027` |
| PCS-slug | `e3-harelbeke` |
| PCS-løbsside | https://www.procyclingstats.com/race/e3-harelbeke/2026 |
| PCS-resultat | https://www.procyclingstats.com/race/e3-harelbeke/2026/result |
| GPX (cyclingstage) | konfigureret |
| ASO-roadbook | nej (ikke et ASO-løb) |
| Kendt af startliste-agenten | **nej — tilføj PCS-slug til `startlist_agent.PCS_RACE_SLUGS`** |
| Kendt af TV-agenten | **nej — tilføj nøgleord til `tv_agent.RACE_KEYWORDS`** |

## Hvad vi fik i 2026

| Data | Status |
|---|---|
| Startliste | 0 ryttere |
| Etaper i databasen | 1 |
| Etaper med distance | 0 |
| Etaper med GPX-rute | 0 |
| Egengenereret højdeprofil | 0 |
| Stigninger | 0 (0 med profil) |
| Etaper med resultat | 1 / 1 |
| Klassementsrækker | 0 |
| Etapereferater | 0 |
| TV-sendinger | 0 |

## Noter

- PCS-slug er `e3-harelbeke`. Både `e3-saxo-classic` og `e3-saxo-bank-classic` svarer tomt.

## Tjekliste til 2027

| Hvornår | Hvad | Job |
|---|---|---|
| Før sæsonen | Verificér PCS-slug og GPX-kilde (de skifter) | `Datakilde-scan` |
| 1 uge før | Startliste + etapedata + stigninger + profiler | `Fuld forberedelse` |
| 48 t før | Startliste igen (PCS har først hele feltet tæt på) | `Startliste` |
| 24 t før | TV-tider | `TV-tider` |
| 6 t før | Sidste tjek af startliste og rute | `Startliste`, `Ræsinfo` |
| 1 t efter mål | Resultat og klassement | `Resultater` |
| Hver ½ time indtil resultatet står | Resultat igen | `Resultater` |

---

Se [README.md](README.md) for metoden og de generelle fælder.
