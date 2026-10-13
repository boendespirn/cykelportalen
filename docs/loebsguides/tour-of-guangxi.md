# Tour of Guangxi — kildeguide

*Etapeløb · UCI WorldTour · kørt 2026-10-13 – 2026-10-18 i 2026.*

Skrevet ud fra 2026-sæsonen 2026-10-12. Brug den som udgangspunkt for 2027 — men **verificér URL'erne igen**, før sæsonen går i gang: PCS skifter slugs uden varsel.

## Identitet

| Felt | Værdi |
|---|---|
| Vores DB-slug | `tour-of-guangxi-2027` |
| PCS-slug | `tour-of-guangxi` |
| PCS-løbsside | https://www.procyclingstats.com/race/tour-of-guangxi/2026 |
| PCS-resultat | https://www.procyclingstats.com/race/tour-of-guangxi/2026/stage-N/result |
| GPX (cyclingstage) | **ikke konfigureret** |
| ASO-roadbook | nej (ikke et ASO-løb) |
| Kendt af startliste-agenten | **nej — tilføj PCS-slug til `startlist_agent.PCS_RACE_SLUGS`** |
| Kendt af TV-agenten | **nej — tilføj nøgleord til `tv_agent.RACE_KEYWORDS`** |

## Hvad vi fik i 2026

| Data | Status |
|---|---|
| Startliste | 158 ryttere |
| Etaper i databasen | 6 |
| Etaper med distance | 6 |
| Etaper med GPX-rute | 0 |
| Egengenereret højdeprofil | 0 |
| Stigninger | 0 (0 med profil) |
| Etaper med resultat | 0 / 6 |
| Klassementsrækker | 0 |
| Etapereferater | 0 |
| TV-sendinger | 0 |

## Noter

- **Sæsonens sidste løb og den første prøve på automatiseringen** — startlisten (151 ryttere) blev hentet af workeren i skyen 2026-10-13, uden at nogen trykkede.
- Syv kinesiske ryttere i startlisten findes ikke i `riders` og står derfor uden profil (HU Haijie, LIU Chenglu, LIU Zhicheng, MA Binyan, SHEN Yutao, WANG Ruidong, ZHAO Chenli).

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
