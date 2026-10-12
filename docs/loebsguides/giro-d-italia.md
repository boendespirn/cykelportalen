# Giro d'Italia — kildeguide

*Etapeløb · 2.UWT · kørt 2026-05-08 – 2026-05-31 i 2026.*

Skrevet ud fra 2026-sæsonen 2026-10-12. Brug den som udgangspunkt for 2027 — men **verificér URL'erne igen**, før sæsonen går i gang: PCS skifter slugs uden varsel.

## Identitet

| Felt | Værdi |
|---|---|
| Vores DB-slug | `giro-d-italia-2027` |
| PCS-slug | `giro-d-italia` |
| PCS-løbsside | https://www.procyclingstats.com/race/giro-d-italia/2026 |
| PCS-resultat | https://www.procyclingstats.com/race/giro-d-italia/2026/stage-N/result |
| GPX (cyclingstage) | konfigureret |
| ASO-roadbook | nej (ikke et ASO-løb) |
| Kendt af startliste-agenten | ja |
| Kendt af TV-agenten | ja |

## Hvad vi fik i 2026

| Data | Status |
|---|---|
| Startliste | 184 ryttere |
| Etaper i databasen | 21 |
| Etaper med distance | 21 |
| Etaper med GPX-rute | 21 |
| Egengenereret højdeprofil | 0 |
| Stigninger | 40 (31 med profil) |
| Etaper med resultat | 21 / 21 |
| Klassementsrækker | 2108 |
| Etapereferater | 0 |
| TV-sendinger | 33 |

## Noter

- Egen GPX-side hos cyclingstage (`giro-2026-gpx`).
- Ingen egengenererede hel-etape-profiler i 2026 — 0 af 21. Kør `stage_profile_generator` med `--overwrite`, efter stigningerne er hentet.

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
