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
| GPX (cyclingstage) | **findes ikke** |
| **Arrangoerens API** | `https://cycling.edgecycling.cn` — serie `1802953069501599746` |
| — aargang | `/pro/proRaces/queryBySeriesId?seriesId=...` (giver raceId pr. aar) |
| — etapeliste | `/pro/proStages/queryAll4Web?raceId=...` |
| — etapedetalje | `/pro/proStages/queryById4Web?id=...` |
| — GPX i API'et | **tomt** — `gpxUrl` er null for 2025 og 2026 (kun 2024 har filer) |
| Hentes af | `agents/edgecycling_agent.py --race tour-of-guangxi-YYYY --write-db` |
| ASO-roadbook | nej (ikke et ASO-løb) |
| Kendt af startliste-agenten | **nej — tilføj PCS-slug til `startlist_agent.PCS_RACE_SLUGS`** |
| Kendt af TV-agenten | **nej — tilføj nøgleord til `tv_agent.RACE_KEYWORDS`** |

## Hvad vi fik i 2026

| Data | Status |
|---|---|
| Startliste | 158 ryttere |
| Etaper i databasen | 6 |
| Etaper med distance | 6 |
| Etaper med GPX-rute | 0 — ingen GPX findes for løbet |
| Egengenereret højdeprofil | **6** (digitaliseret fra arrangørens officielle profilbillede) |
| Stigninger | **12** (kategori, km, længde, gradient fra arrangørens slopeMap) |
| Etaper med resultat | 0 / 6 |
| Klassementsrækker | 0 |
| Etapereferater | 0 |
| TV-sendinger | 0 |

## Noter

- **Sæsonens sidste løb og den første prøve på automatiseringen** — startlisten (151 ryttere) blev hentet af workeren i skyen 2026-10-13, uden at nogen trykkede.
- Syv kinesiske ryttere i startlisten findes ikke i `riders` og står derfor uden profil (HU Haijie, LIU Chenglu, LIU Zhicheng, MA Binyan, SHEN Yutao, WANG Ruidong, ZHAO Chenli).


## Datakilder — hvad findes, og hvad gør det ikke (fundet 2026-10-14)

| Data | Kilde | Status |
|---|---|---|
| Etapeinfo (distance, D+, byer, type) | arrangørens API | ✅ komplet, 6/6 |
| Start- og forventet måltid | arrangørens API (`startTime`/`endTime`) | ✅ — vigtigt, fordi `races.country_code` er tom for Guangxi, så schedulerens tidszonegæt ellers rammer ved siden af |
| Hel-etape-højdeprofil | `elevationChart`-billede → digitaliseret | ✅ 6/6 i vores eget design |
| Stigninger | `slopeMap`-billede → aflæst | ✅ 12 stigninger |
| Startliste | PCS | ✅ 158 ryttere |
| Resultater | PCS | ✅ (etape 1 hentet automatisk af workeren) |
| **GPX / rutegeometri** | — | ❌ **findes ingen steder.** Arrangørens felt er tomt, cyclingstage har ikke løbet. Konsekvens: kortpanelet står tomt, og stigninger kan ikke matches mod VeloViewer-segmenter. |
| **Stigningsprofil-billeder** | `slopeMap` | ⚠️ tallene er hentet, men procent-etiketterne dækker kun de markante delstrækninger (på Nongla 609 m af 3.100 m), så `gradient_sections` kan ikke udfyldes uden at aflæse farvebåndene |
| **Bonusspurter** | `elevationChart` | ⚠️ markørerne findes, men spurt og depotzone kan ikke skelnes uden at læse ikonerne |

**Vigtigste fælde ved kilden:** knappen "GPX" på `/route` renderes ubetinget og ser ud til at virke, men `href` bindes til `gpxUrl`, som er `null`. 2025-udgaven kørte helt færdig uden at feltet blev udfyldt — feltet er ikke vedligeholdt efter 2024.

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
