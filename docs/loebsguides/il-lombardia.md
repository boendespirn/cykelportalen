# Il Lombardia — kildeguide

*Endagsløb · UCI WorldTour · kørt 2026-10-10 i 2026.*

Skrevet ud fra 2026-sæsonen 2026-10-12. Brug den som udgangspunkt for 2027 — men **verificér URL'erne igen**, før sæsonen går i gang: PCS skifter slugs uden varsel.

## Identitet

| Felt | Værdi |
|---|---|
| Vores DB-slug | `il-lombardia-2027` |
| PCS-slug | `il-lombardia` |
| PCS-løbsside | https://www.procyclingstats.com/race/il-lombardia/2026 |
| PCS-resultat | https://www.procyclingstats.com/race/il-lombardia/2026/result |
| GPX (cyclingstage) | konfigureret |
| ASO-roadbook | nej (ikke et ASO-løb) |
| Kendt af startliste-agenten | ja |
| Kendt af TV-agenten | ja |

## Hvad vi fik i 2026

| Data | Status |
|---|---|
| Startliste | 174 ryttere |
| Etaper i databasen | 1 |
| Etaper med distance | 1 |
| Etaper med GPX-rute | 1 |
| Egengenereret højdeprofil | 1 |
| Stigninger | 9 (9 med profil) |
| Etaper med resultat | 1 / 1 |
| Klassementsrækker | 0 |
| Etapereferater | 0 |
| TV-sendinger | 3 |

## Noter

- **Referenceopsætningen for endagsløb** — se afsnittet i `ARKITEKTUR.md`.
- GPX ligger IKKE på cyclingstages fælles index (kun forårsløb). Den står på løbets egen rute-underside, og cyclingstage kalder løbet `tour-of-lombardy` (DATA-003).
- PCS har kun klatredata som BILLEDER (`-climb` på `/info/profiles`) — `climb_vision_agent.py` læser dem (STG-031).
- San Fermo della Battaglia køres TO gange på den afsluttende sløjfe. Søgningen skal returnere alle passager, ellers mangler den afgørende opstigning 5 km fra mål (STG-032).
- Intet referat muligt: PCS har ingen LiveStats-tidslinje for endagsløb (RES-008).

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
