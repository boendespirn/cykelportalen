# Tour de France — kildeguide

*Etapeløb · UCI WorldTour · kørt 2026-07-04 – 2026-07-26 i 2026.*

Skrevet ud fra 2026-sæsonen 2026-10-12. Brug den som udgangspunkt for 2027 — men **verificér URL'erne igen**, før sæsonen går i gang: PCS skifter slugs uden varsel.

## Identitet

| Felt | Værdi |
|---|---|
| Vores DB-slug | `tour-de-france-2027` |
| PCS-slug | `tour-de-france` |
| PCS-løbsside | https://www.procyclingstats.com/race/tour-de-france/2026 |
| PCS-resultat | https://www.procyclingstats.com/race/tour-de-france/2026/stage-N/result |
| GPX (cyclingstage) | konfigureret |
| ASO-roadbook | ja |
| Kendt af startliste-agenten | ja |
| Kendt af TV-agenten | ja |

## Hvad vi fik i 2026

| Data | Status |
|---|---|
| Startliste | 184 ryttere |
| Etaper i databasen | 21 |
| Etaper med distance | 21 |
| Etaper med GPX-rute | 21 |
| Egengenereret højdeprofil | 19 |
| Stigninger | 88 (88 med profil) |
| Etaper med resultat | 21 / 21 |
| Klassementsrækker | 1627 |
| Etapereferater | 0 |
| TV-sendinger | 67 |

## Noter

- Sæsonens vigtigste løb (north star i `CLAUDE.md` §4) — forbered det først og mest grundigt.
- Har ASO-roadbook (`letour.fr`), som er en uafhængig kontrol af stigningernes km og længde.
- Bedst dækkede løb i 2026: 21/21 etaper med resultat, 88 stigninger med profil, 67 TV-sendinger.
- Klassementerne hentes fra `…/stage-N-gc` osv. — men den AFSLUTTENDE etape svarer HTTP 500 der, og det endelige klassement ligger kun på løbs-niveau (`…/2026/gc`). Fallbacken må kun gælde sidste etape (RES-005).

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
