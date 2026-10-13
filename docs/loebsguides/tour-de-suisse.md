# Tour de Suisse — kildeguide

*Etapeløb · 2.UWT · kørt 2026-06-17 – 2026-06-21 i 2026.*

Skrevet ud fra 2026-sæsonen 2026-10-12. Brug den som udgangspunkt for 2027 — men **verificér URL'erne igen**, før sæsonen går i gang: PCS skifter slugs uden varsel.

## Identitet

| Felt | Værdi |
|---|---|
| Vores DB-slug | `tour-de-suisse-2027` |
| PCS-slug | `tour-de-suisse` |
| PCS-løbsside | https://www.procyclingstats.com/race/tour-de-suisse/2026 |
| PCS-resultat | https://www.procyclingstats.com/race/tour-de-suisse/2026/stage-N/result |
| GPX (cyclingstage) | konfigureret |
| ASO-roadbook | nej (ikke et ASO-løb) |
| Kendt af startliste-agenten | ja |
| Kendt af TV-agenten | ja |

## Hvad vi fik i 2026

| Data | Status |
|---|---|
| Startliste | 140 ryttere |
| Etaper i databasen | 5 |
| Etaper med distance | 5 |
| Etaper med GPX-rute | 0 |
| Egengenereret højdeprofil | 0 |
| Stigninger | 9 (3 med profil) |
| Etaper med resultat | 5 / 5 |
| Klassementsrækker | 487 |
| Etapereferater | 0 |
| TV-sendinger | 14 |

## Noter

- Løbet havde **fem** etaper i 2026 — ikke otte. Verificeret 2026-10-13: PCS har ingen etape 6. En tidligere note om tre manglende etaper var forkert.

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
