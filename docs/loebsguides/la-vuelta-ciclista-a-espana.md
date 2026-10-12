# La Vuelta Ciclista a España — kildeguide

*Etapeløb · UCI WorldTour · kørt 2026-08-22 – 2026-09-13 i 2026.*

Skrevet ud fra 2026-sæsonen 2026-10-12. Brug den som udgangspunkt for 2027 — men **verificér URL'erne igen**, før sæsonen går i gang: PCS skifter slugs uden varsel.

## Identitet

| Felt | Værdi |
|---|---|
| Vores DB-slug | `la-vuelta-ciclista-a-espana-2027` |
| PCS-slug | `vuelta-a-espana` |
| PCS-løbsside | https://www.procyclingstats.com/race/vuelta-a-espana/2026 |
| PCS-resultat | https://www.procyclingstats.com/race/vuelta-a-espana/2026/stage-N/result |
| GPX (cyclingstage) | konfigureret |
| ASO-roadbook | ja |
| Kendt af startliste-agenten | ja |
| Kendt af TV-agenten | ja |

## Hvad vi fik i 2026

| Data | Status |
|---|---|
| Startliste | 179 ryttere |
| Etaper i databasen | 21 |
| Etaper med distance | 21 |
| Etaper med GPX-rute | 0 |
| Egengenereret højdeprofil | 21 |
| Stigninger | 58 (11 med profil) |
| Etaper med resultat | 20 / 21 |
| Klassementsrækker | 1618 |
| Etapereferater | 17 |
| TV-sendinger | 0 |

## Noter

- Har ASO-roadbook (`lavuelta.es`).
- PCS-slug er `vuelta-a-espana`, ikke vores `la-vuelta-ciclista-a-espana`.
- 2026: de sidste fire etaper (18-21) fik aldrig hentet resultat, fordi ingen kørte jobbet efter løbets slutning. Hentet bagud 2026-10-13 — præcis det hul, automatiseringen skal fjerne.
- Etape 3 blev aflyst i uvejr og står korrekt som `data_status = cancelled`.
- På den AFSLUTTENDE etape svarer `…/stage-21-gc` HTTP 500; det endelige klassement ligger kun på løbs-niveau (`…/2026/gc`). Fallbacken dækker det (RES-005).

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
