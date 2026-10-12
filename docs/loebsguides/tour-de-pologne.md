# Tour de Pologne — kildeguide

*Etapeløb · UCI WorldTour · kørt 2026-08-03 – 2026-08-09 i 2026.*

Skrevet ud fra 2026-sæsonen 2026-10-12. Brug den som udgangspunkt for 2027 — men **verificér URL'erne igen**, før sæsonen går i gang: PCS skifter slugs uden varsel.

## Identitet

| Felt | Værdi |
|---|---|
| Vores DB-slug | `tour-de-pologne-2027` |
| PCS-slug | `tour-de-pologne` |
| PCS-løbsside | https://www.procyclingstats.com/race/tour-de-pologne/2026 |
| PCS-resultat | https://www.procyclingstats.com/race/tour-de-pologne/2026/stage-N/result |
| GPX (cyclingstage) | **ikke konfigureret** |
| ASO-roadbook | nej (ikke et ASO-løb) |
| Kendt af startliste-agenten | ja |
| Kendt af TV-agenten | **nej — tilføj nøgleord til `tv_agent.RACE_KEYWORDS`** |

## Hvad vi fik i 2026

| Data | Status |
|---|---|
| Startliste | 116 ryttere |
| Etaper i databasen | 7 |
| Etaper med distance | 7 |
| Etaper med GPX-rute | 0 |
| Egengenereret højdeprofil | 7 |
| Stigninger | 13 (0 med profil) |
| Etaper med resultat | 7 / 7 |
| Klassementsrækker | 344 |
| Etapereferater | 0 |
| TV-sendinger | 0 |

## Noter

- Stigningerne kom fra PCS' per-stigning-billeder (`source = pcs_climb_profile`), men ingen af dem har en profiltegning endnu.

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
