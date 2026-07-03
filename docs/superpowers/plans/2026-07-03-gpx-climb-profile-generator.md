# GPX-baseret stigningsprofil-generator — Implementeringsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Byg `agents/climb_profile_generator.py`, som genererer klassementet.dk's egne stigningsprofil-billeder direkte fra rå GPX-højdedata (ClimbFinder-stil: terrænsilhuet delt i 10 farvede sektioner efter hældning), og kør en testkørsel for Tour de France 2026 etape 2.

**Architecture:** Ét selvstændigt script i `agents/`, konsistent med den eksisterende stignings-pipelines mønster (`gpx_climb_agent.py`, `climbfinder_agent.py`, `profile_reader_agent.py` — se `ARKITEKTUR.md`). Henter rå GPX direkte fra cyclingstage.com (ikke `stages.route_points`, som mangler højde og er downsamplet), lokaliserer stigningens segment via proportional position i GPX'ens eget distance-rum, validerer segmentet mod DB'ens kendte klatredata, deler i 10 sektioner, farvelægger efter hældning, og renderer med Pillow. Se `docs/superpowers/specs/2026-07-03-gpx-climb-profile-generator-design.md` for det fulde design.

**Tech Stack:** Python 3.10+, `requests`, `beautifulsoup4`, `Pillow` (allerede i `requirements.txt` — ingen nye dependencies), stdlib `unittest` til de rene logik-funktioner (ingen pytest i dette repo).

**Afvigelse fundet under eksekvering (2026-07-03):** Task 3's oprindelige `locate_climb_segment()` (ren proportional position) blev afprøvet mod rigtige etape-2-data i Task 9 og fejlede for alle 4 stigninger — GPS-støj fra sving koncentreres i klatre-afsnittene selv, ikke jævnt langs hele ruten, så den proportionale gætning overskød systematisk (voksende fra ~3 km ved første stigning til ~14 km ved fjerde). Rettet ved at gøre det proportionale gæt til udgangspunkt for en vinduessøgning, der scorer kandidatsegmenter mod DB'ens kendte højdemeter/hældning (ny parameter `db_climb` på `locate_climb_segment()`). Se commit "fix: erstat proportional segment-gaetning med vinduessoegning". Genkørt Task 9 efter rettelsen: alle 4 etape-2-stigninger validerer nu korrekt.

## Global Constraints

- Alt brugervendt output (print-beskeder, docstrings, kommentarer) skrives på dansk, jf. CLAUDE.md §"Alt arbejde foregår på dansk". Funktions-/variabelnavne er engelske, som i resten af `agents/`.
- Ingen nye pip-dependencies — brug kun det, der allerede står i `requirements.txt` (`requests`, `beautifulsoup4`, `Pillow`, `python-dotenv`).
- Farveskala for gradient → farve er **eksakt** denne tabel (fra design-specen, ikke til forhandling i denne plan):
  `0%→#FFFFFF, 4%→#FDE0A6, 7%→#F5943C, 10%→#D62828, 13%→#7A0C1E, 15%+→#0A0A0A`.
- Billedopløsning: 2400×1200 px (matcher ClimbFinders billeder, så eksisterende `<img>`/lightbox-UI i `ClimbProfile.tsx` fungerer uændret).
- Aldrig skriv uverificeret data til `profile_image_url` — et GPX-segment, der ikke består `within_tolerance()`-tjekket mod DB'ens `elevation_m`/`avg_gradient`, skal springes over med en tydelig fejlbesked, ikke gemmes (jf. CLAUDE.md §7).
- `--write-db` skal aldrig køres med `--style both` (tvetydigt hvilket billede der skal gemmes i `profile_image_url`) — valider og fejl tydeligt i stedet.

---

### Task 1: Scaffold + GPX-parsing med højdedata

**Files:**
- Create: `agents/climb_profile_generator.py`
- Test: `agents/test_climb_profile_generator.py`

**Interfaces:**
- Produces: `parse_gpx_with_elevation(xml_content: str) -> list[tuple[float, float, float]]` — returnerer `[(lat, lon, ele_m), ...]` i fuld GPX-opløsning (ingen downsampling).
- Produces: `CYCLINGSTAGE_GPX_PAGES: dict[str, str]`, `UA: str` (User-Agent-streng til HTTP-kald).

- [ ] **Step 1: Opret scaffold-filen med alle imports scriptet får brug for**

```python
"""
climb_profile_generator.py
Genererer klassementet.dk's egne stigningsprofil-billeder direkte fra raa
GPX-hoejdedata, som fallback naar ClimbFinder ikke har et verificeret match.

Stil: terraensilhuet delt i 10 sektioner, farvet efter haeldning
(hvid 0% -> roed 10% -> moerkeroed ~13% -> sort 15%+), i to varianter
("full" med akser/labels, "minimal" uden).

Kilde til GPX: cyclingstage.com (samme kilde som gpx_agent.py, men parset
med hoejde bevaret og uden downsampling).

Kør (test — genererer begge stilarter, uploader kun til test/-sti, ingen DB-skrivning):
     python agents/climb_profile_generator.py --race tour-de-france-2026 --stage 2

Kør (produktion — skriver profile_image_url for stigninger uden billede):
     python agents/climb_profile_generator.py --race tour-de-france-2026 --stage 2 \
         --style full --write-db
"""

import os
import re
import io
import sys
import math
import bisect
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SB_AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
SB_HEADERS = {**SB_AUTH, "Content-Type": "application/json", "Prefer": "return=minimal"}
BUCKET = "stage-profiles"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

CYCLINGSTAGE_GPX_PAGES: dict[str, str] = {
    "giro-d-italia-2026":         "https://www.cyclingstage.com/giro-2026-gpx",
    "tour-de-france-2026":        "https://www.cyclingstage.com/tour-de-france-2026-gpx",
    "criterium-du-dauphine-2026": "https://www.cyclingstage.com/criterium-du-dauphine-2026-gpx",
    "tour-de-suisse-2026":        "https://www.cyclingstage.com/tour-de-suisse-2026-gpx",
}


# ── GPX henter/parser ──────────────────────────────────────────────────────────

def parse_gpx_with_elevation(xml_content: str) -> list[tuple[float, float, float]]:
    """
    Parser GPX XML og returnerer [(lat, lon, ele_m), ...] i fuld opløsning
    (ingen downsampling — modsat gpx_agent.py, som kun gemmer lat/lon).
    Punkter uden <ele> arver forrige punkts højde (GPS-udfald er sjældne,
    men skal ikke vælte hele parsingen).
    """
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        raise ValueError(f"GPX XML-fejl: {e}")

    points_el = []
    for ns_uri in ("http://www.topografix.com/GPX/1/1", "http://www.topografix.com/GPX/1/0"):
        ns = {"g": ns_uri}
        points_el = root.findall(".//g:trkpt", ns)
        if points_el:
            break

    if not points_el:
        points_el = [el for el in root.iter() if el.tag.endswith("trkpt")]

    if not points_el:
        raise ValueError("Ingen trkpt-punkter fundet i GPX")

    points: list[tuple[float, float, float]] = []
    last_ele = 0.0
    for el in points_el:
        lat = float(el.get("lat"))
        lon = float(el.get("lon"))
        ele_el = next((child for child in el if child.tag.endswith("ele")), None)
        if ele_el is not None and ele_el.text:
            last_ele = float(ele_el.text)
        points.append((lat, lon, last_ele))

    return points


def get_gpx_url_for_stage(race_slug: str, stage_number: int) -> str | None:
    """Finder GPX-download-URL'en for en specifik etape på cyclingstage.com."""
    gpx_page_url = CYCLINGSTAGE_GPX_PAGES.get(race_slug)
    if not gpx_page_url:
        return None
    res = requests.get(gpx_page_url, headers={"User-Agent": UA}, timeout=15)
    if not res.ok:
        return None
    soup = BeautifulSoup(res.text, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = re.fullmatch(r".*stage-(\d+)-route\.gpx", href)
        if not m:
            continue
        if int(m.group(1)) == stage_number:
            return href if href.startswith("http") else "https://cdn.cyclingstage.com" + href
    return None


def download_stage_gpx(race_slug: str, stage_number: int) -> list[tuple[float, float, float]] | None:
    """Henter og parser den rå GPX-fil for en etape. None hvis ikke fundet/fejl."""
    gpx_url = get_gpx_url_for_stage(race_slug, stage_number)
    if not gpx_url:
        return None
    res = requests.get(gpx_url, headers={"User-Agent": UA}, timeout=20)
    if not res.ok:
        return None
    try:
        return parse_gpx_with_elevation(res.text)
    except ValueError as e:
        print(f"    [GPX parse-fejl: {e}]")
        return None
```

- [ ] **Step 2: Skriv testfilen med syntetisk GPX (ingen netværk)**

```python
"""
test_climb_profile_generator.py
Automatiserede unit-tests for de rene logik-funktioner i
climb_profile_generator.py (GPX-parsing, geometri, farveskala, rendering).
Netværks-/DB-integrationen (Supabase, cyclingstage.com) testes ikke her —
den verificeres manuelt ved en rigtig kørsel, jf. Task 9 i implementerings-
planen.

Kør: python agents/test_climb_profile_generator.py
"""

import unittest

from climb_profile_generator import parse_gpx_with_elevation


SAMPLE_GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.0" creator="test" xmlns="http://www.topografix.com/GPX/1/0">
  <trk><trkseg>
    <trkpt lat="45.000000" lon="6.000000"><ele>100.0</ele></trkpt>
    <trkpt lat="45.001000" lon="6.001000"><ele>110.0</ele></trkpt>
    <trkpt lat="45.002000" lon="6.002000"><ele>120.0</ele></trkpt>
    <trkpt lat="45.003000" lon="6.003000"></trkpt>
  </trkseg></trk>
</gpx>
"""


class TestParseGpxWithElevation(unittest.TestCase):
    def test_parses_lat_lon_ele(self):
        points = parse_gpx_with_elevation(SAMPLE_GPX)
        self.assertEqual(points[0], (45.0, 6.0, 100.0))
        self.assertEqual(points[1], (45.001, 6.001, 110.0))
        self.assertEqual(points[2], (45.002, 6.002, 120.0))

    def test_missing_ele_carries_forward_previous_value(self):
        points = parse_gpx_with_elevation(SAMPLE_GPX)
        self.assertEqual(points[3], (45.003, 6.003, 120.0))

    def test_raises_on_empty_gpx(self):
        with self.assertRaises(ValueError):
            parse_gpx_with_elevation("<gpx></gpx>")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Kør testen og bekræft den passerer**

Run: `python agents/test_climb_profile_generator.py -v`
Expected: `OK` — alle 3 tests i `TestParseGpxWithElevation` passerer.

- [ ] **Step 4: Commit**

```bash
git add agents/climb_profile_generator.py agents/test_climb_profile_generator.py
git commit -m "feat: scaffold climb_profile_generator.py med GPX-hoejdeparsing"
```

---

### Task 2: Geometri — haversine-afstand og kumulativ distance

**Files:**
- Modify: `agents/climb_profile_generator.py` (tilføj sektion "Geometri")
- Test: `agents/test_climb_profile_generator.py`

**Interfaces:**
- Consumes: ingen (rene matematiske funktioner).
- Produces: `haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float`, `cumulative_distances_km(points: list[tuple[float, float, float]]) -> list[float]`.

- [ ] **Step 1: Skriv de fejlende tests**

Tilføj til `agents/test_climb_profile_generator.py`:

```python
from climb_profile_generator import (
    parse_gpx_with_elevation,
    haversine_km,
    cumulative_distances_km,
)


class TestGeometry(unittest.TestCase):
    def test_haversine_one_degree_latitude(self):
        # Ren nord-syd-bevægelse: sfærisk afstand = R * radianer(1°) ≈ 111.194 km
        d = haversine_km(45.0, 6.0, 45.01, 6.0)
        self.assertAlmostEqual(d, 1.11194, delta=0.001)

    def test_haversine_zero_distance(self):
        self.assertAlmostEqual(haversine_km(45.0, 6.0, 45.0, 6.0), 0.0, delta=1e-9)

    def test_cumulative_distances_starts_at_zero_and_increases(self):
        points = [(45.0, 6.0, 100.0), (45.01, 6.0, 110.0), (45.02, 6.0, 120.0)]
        cum = cumulative_distances_km(points)
        self.assertEqual(len(cum), 3)
        self.assertAlmostEqual(cum[0], 0.0, delta=1e-9)
        self.assertAlmostEqual(cum[1], 1.11194, delta=0.001)
        self.assertAlmostEqual(cum[2], 2.22388, delta=0.002)
```

- [ ] **Step 2: Kør testen og bekræft den fejler**

Run: `python agents/test_climb_profile_generator.py -v`
Expected: `ImportError: cannot import name 'haversine_km'` (funktionerne findes ikke endnu).

- [ ] **Step 3: Implementér funktionerne**

Tilføj til `agents/climb_profile_generator.py` (efter GPX-sektionen — `import math` er allerede tilføjet i Task 1's imports-blok):

```python
# ── Geometri ────────────────────────────────────────────────────────────────

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def cumulative_distances_km(points: list[tuple[float, float, float]]) -> list[float]:
    """Kumulativ distance i km langs punktrækken, samme længde som points. cum[0] = 0.0."""
    cum = [0.0]
    for i in range(1, len(points)):
        d = haversine_km(points[i - 1][0], points[i - 1][1], points[i][0], points[i][1])
        cum.append(cum[-1] + d)
    return cum
```

- [ ] **Step 4: Kør testen og bekræft den passerer**

Run: `python agents/test_climb_profile_generator.py -v`
Expected: `OK` — alle tests inkl. de 3 nye i `TestGeometry` passerer.

- [ ] **Step 5: Commit**

```bash
git add agents/climb_profile_generator.py agents/test_climb_profile_generator.py
git commit -m "feat: tilfoej haversine-afstand og kumulativ distance"
```

---

### Task 3: Lokalisér stigningens segment i GPX-sporet

**Files:**
- Modify: `agents/climb_profile_generator.py` (tilføj sektion "Segment-lokalisering")
- Test: `agents/test_climb_profile_generator.py`

**Interfaces:**
- Consumes: `cumulative_distances_km()` fra Task 2.
- Produces: `locate_climb_segment(points: list[tuple[float, float, float]], cum_dist: list[float], stage_distance_km: float, km_from_start: float, length_km: float) -> list[tuple[float, float, float]]` — kaster `ValueError` hvis intet gyldigt segment kan lokaliseres.

- [ ] **Step 1: Skriv de fejlende tests**

```python
from climb_profile_generator import locate_climb_segment


class TestLocateClimbSegment(unittest.TestCase):
    def setUp(self):
        # 11 punkter jaevnt fordelt langs en meridian, ca. 1 km mellem hver
        self.points = [(45.0 + i * 0.0089932, 6.0, float(i)) for i in range(11)]
        self.cum = [round(i * 1.11194, 5) for i in range(11)]  # ~[0,1,2,...,10] km

    def test_exact_boundaries_when_gpx_matches_official_distance(self):
        segment = locate_climb_segment(self.points, self.cum, stage_distance_km=10.0,
                                        km_from_start=3.0, length_km=4.0)
        self.assertEqual(segment[0], self.points[3])
        self.assertEqual(segment[-1], self.points[7])
        self.assertEqual(len(segment), 5)

    def test_proportional_scaling_when_gpx_distance_differs_from_official(self):
        # Officiel distance 8 km, men GPX'ens egen sum er 10 km (GPS-stoej).
        # Klatring ligger 30%-70% af den officielle distance -> samme 3-7 km
        # vindue i GPX'ens eget distance-rum som ovenstaaende test.
        segment = locate_climb_segment(self.points, self.cum, stage_distance_km=8.0,
                                        km_from_start=2.4, length_km=3.2)
        self.assertEqual(segment[0], self.points[3])
        self.assertEqual(segment[-1], self.points[7])

    def test_raises_on_invalid_stage_distance(self):
        with self.assertRaises(ValueError):
            locate_climb_segment(self.points, self.cum, stage_distance_km=0,
                                  km_from_start=1.0, length_km=2.0)
```

- [ ] **Step 2: Kør testen og bekræft den fejler**

Run: `python agents/test_climb_profile_generator.py -v`
Expected: `ImportError: cannot import name 'locate_climb_segment'`.

- [ ] **Step 3: Implementér funktionen**

Tilføj til `agents/climb_profile_generator.py`:

```python
# ── Segment-lokalisering ────────────────────────────────────────────────────

def locate_climb_segment(
    points: list[tuple[float, float, float]],
    cum_dist: list[float],
    stage_distance_km: float,
    km_from_start: float,
    length_km: float,
) -> list[tuple[float, float, float]]:
    """
    Lokaliserer stigningens segment i GPX-sporet ved proportional position,
    fordi GPX'ens egen kumulative distance sjældent matcher den officielle
    etapedistance præcist (GPS-støj i sving inflaterer GPX-distancen).
    """
    if stage_distance_km <= 0:
        raise ValueError("Ugyldig etapedistance")

    gpx_total = cum_dist[-1]
    start_target = (km_from_start / stage_distance_km) * gpx_total
    end_target = ((km_from_start + length_km) / stage_distance_km) * gpx_total

    start_idx = bisect.bisect_left(cum_dist, start_target)
    end_idx = bisect.bisect_left(cum_dist, end_target)

    start_idx = max(0, min(start_idx, len(points) - 1))
    end_idx = max(0, min(end_idx, len(points) - 1))

    if end_idx <= start_idx:
        raise ValueError("Kunne ikke lokalisere et gyldigt GPX-segment for stigningen")

    segment = points[start_idx:end_idx + 1]
    if len(segment) < 2:
        raise ValueError("For få GPX-punkter i det lokaliserede segment")

    return segment
```

- [ ] **Step 4: Kør testen og bekræft den passerer**

Run: `python agents/test_climb_profile_generator.py -v`
Expected: `OK` — alle tests inkl. de 3 nye i `TestLocateClimbSegment` passerer.

- [ ] **Step 5: Commit**

```bash
git add agents/climb_profile_generator.py agents/test_climb_profile_generator.py
git commit -m "feat: lokaliser stigningssegment via proportional GPX-position"
```

---

### Task 4: Udledte klatrestats + tolerance-validering mod DB-data

**Files:**
- Modify: `agents/climb_profile_generator.py` (tilføj sektion "Validering")
- Test: `agents/test_climb_profile_generator.py`

**Interfaces:**
- Consumes: `haversine_km()` fra Task 2.
- Produces: `derive_climb_stats(segment_points: list[tuple[float, float, float]]) -> dict` (nøgler: `elevation_gain_m: int`, `avg_gradient: float`, `distance_km: float`), `within_tolerance(derived: dict, db_climb: dict) -> tuple[bool, str]`.

- [ ] **Step 1: Skriv de fejlende tests**

```python
from climb_profile_generator import derive_climb_stats, within_tolerance


class TestDeriveClimbStats(unittest.TestCase):
    def test_computes_elevation_gain_and_gradient(self):
        # 3 punkter, ~0.5559 km mellem hver (0.005° breddegrad), total ~1.1119 km
        segment = [(45.0, 6.0, 100.0), (45.005, 6.0, 150.0), (45.01, 6.0, 200.0)]
        stats = derive_climb_stats(segment)
        self.assertEqual(stats["elevation_gain_m"], 100)
        self.assertAlmostEqual(stats["avg_gradient"], 9.0, delta=0.1)


class TestWithinTolerance(unittest.TestCase):
    def test_accepts_close_match(self):
        derived = {"elevation_gain_m": 390, "avg_gradient": 5.8}
        db_climb = {"elevation_m": 400, "avg_gradient": 6.0}
        ok, reason = within_tolerance(derived, db_climb)
        self.assertTrue(ok)

    def test_rejects_wildly_different_elevation(self):
        derived = {"elevation_gain_m": 100, "avg_gradient": 5.8}
        db_climb = {"elevation_m": 800, "avg_gradient": 6.0}
        ok, reason = within_tolerance(derived, db_climb)
        self.assertFalse(ok)
        self.assertIn("højdemeter", reason)

    def test_rejects_wildly_different_gradient(self):
        derived = {"elevation_gain_m": 400, "avg_gradient": 2.0}
        db_climb = {"elevation_m": 400, "avg_gradient": 9.0}
        ok, reason = within_tolerance(derived, db_climb)
        self.assertFalse(ok)
        self.assertIn("hældning", reason)

    def test_skips_check_when_db_value_missing(self):
        derived = {"elevation_gain_m": 400, "avg_gradient": 6.0}
        db_climb = {"elevation_m": None, "avg_gradient": None}
        ok, reason = within_tolerance(derived, db_climb)
        self.assertTrue(ok)
```

- [ ] **Step 2: Kør testen og bekræft den fejler**

Run: `python agents/test_climb_profile_generator.py -v`
Expected: `ImportError: cannot import name 'derive_climb_stats'`.

- [ ] **Step 3: Implementér funktionerne**

Tilføj til `agents/climb_profile_generator.py`:

```python
# ── Validering ──────────────────────────────────────────────────────────────

def derive_climb_stats(segment_points: list[tuple[float, float, float]]) -> dict:
    """Beregner nettohøjdemeter og gennemsnitshældning for et GPX-segment."""
    start_elev = segment_points[0][2]
    end_elev = segment_points[-1][2]
    elevation_gain_m = end_elev - start_elev

    dist_km = 0.0
    for i in range(1, len(segment_points)):
        dist_km += haversine_km(
            segment_points[i - 1][0], segment_points[i - 1][1],
            segment_points[i][0], segment_points[i][1],
        )

    avg_gradient = (elevation_gain_m / (dist_km * 1000)) * 100 if dist_km > 0 else 0.0

    return {
        "elevation_gain_m": round(elevation_gain_m),
        "avg_gradient": round(avg_gradient, 1),
        "distance_km": round(dist_km, 2),
    }


def within_tolerance(derived: dict, db_climb: dict) -> tuple[bool, str]:
    """
    Sammenligner GPX-udledte stats med DB'ens kendte klatredata.
    Returnerer (godkendt, forklaring). Springer et tjek over hvis DB ikke har
    den pågældende værdi. Samme ånd som climbfinder_agent.py's metrics_ok().
    """
    reasons = []

    db_elev = db_climb.get("elevation_m")
    if db_elev:
        diff = abs(derived["elevation_gain_m"] - db_elev)
        max_diff = max(100, db_elev * 0.25)
        if diff > max_diff:
            return False, f"højdemeter {derived['elevation_gain_m']}m vs DB {db_elev}m (diff {diff}m)"
        reasons.append(f"elev {derived['elevation_gain_m']}≈{db_elev}m")

    db_grad = db_climb.get("avg_gradient")
    if db_grad:
        diff = abs(derived["avg_gradient"] - db_grad)
        if diff > 2.5:
            return False, f"hældning {derived['avg_gradient']:.1f}% vs DB {db_grad}% (diff {diff:.1f}%)"
        reasons.append(f"grad {derived['avg_gradient']:.1f}≈{db_grad}%")

    return True, " | ".join(reasons) if reasons else "ingen metrics at tjekke"
```

- [ ] **Step 4: Kør testen og bekræft den passerer**

Run: `python agents/test_climb_profile_generator.py -v`
Expected: `OK` — alle tests inkl. de 5 nye passerer.

- [ ] **Step 5: Commit**

```bash
git add agents/climb_profile_generator.py agents/test_climb_profile_generator.py
git commit -m "feat: udled klatrestats fra GPX og valider mod DB-tolerance"
```

---

### Task 5: Resampling og 10-sektions gradientberegning

**Files:**
- Modify: `agents/climb_profile_generator.py` (tilføj sektion "Sektionsberegning")
- Test: `agents/test_climb_profile_generator.py`

**Interfaces:**
- Consumes: `haversine_km()` fra Task 2.
- Produces: `resample_elevation_profile(segment_points: list[tuple[float, float, float]], n: int = 200) -> list[tuple[float, float]]` (par af `(distance_km_fra_segmentstart, elevation_m)`), `compute_gradient_sections(resampled: list[tuple[float, float]], n_sections: int = 10) -> list[dict]` (hver dict: `start_km`, `end_km`, `start_elev`, `end_elev`, `avg_gradient`).

- [ ] **Step 1: Skriv de fejlende tests**

```python
from climb_profile_generator import resample_elevation_profile, compute_gradient_sections


class TestResampleElevationProfile(unittest.TestCase):
    def test_linear_segment_resamples_correctly(self):
        # 3 punkter langs en lineær stigning: 0km/100m, 1km/150m, 2km/200m
        segment = [(45.0, 6.0, 100.0), (45.008993, 6.0, 150.0), (45.017986, 6.0, 200.0)]
        resampled = resample_elevation_profile(segment, n=5)
        self.assertEqual(len(resampled), 5)
        self.assertAlmostEqual(resampled[0][0], 0.0, delta=0.01)
        self.assertAlmostEqual(resampled[0][1], 100.0, delta=1.0)
        self.assertAlmostEqual(resampled[2][1], 150.0, delta=2.0)
        self.assertAlmostEqual(resampled[-1][1], 200.0, delta=1.0)


class TestComputeGradientSections(unittest.TestCase):
    def test_two_sections_on_constant_gradient_line(self):
        # Fuldstændig lineær profil: 0km->0m, 1km->50m, 2km->100m (5% hele vejen)
        resampled = [(0.0, 0.0), (1.0, 50.0), (2.0, 100.0)]
        sections = compute_gradient_sections(resampled, n_sections=2)
        self.assertEqual(len(sections), 2)
        self.assertAlmostEqual(sections[0]["start_km"], 0.0)
        self.assertAlmostEqual(sections[0]["end_km"], 1.0)
        self.assertAlmostEqual(sections[0]["avg_gradient"], 5.0, delta=0.01)
        self.assertAlmostEqual(sections[1]["avg_gradient"], 5.0, delta=0.01)
        self.assertAlmostEqual(sections[1]["end_elev"], 100.0, delta=0.01)
```

- [ ] **Step 2: Kør testen og bekræft den fejler**

Run: `python agents/test_climb_profile_generator.py -v`
Expected: `ImportError: cannot import name 'resample_elevation_profile'`.

- [ ] **Step 3: Implementér funktionerne**

Tilføj til `agents/climb_profile_generator.py`:

```python
# ── Sektionsberegning ───────────────────────────────────────────────────────

def _interp_at(xy_pairs: list[tuple[float, float]], x: float) -> float:
    """Lineær interpolation af y ved et givet x i en sorteret (x, y)-liste."""
    xs = [p[0] for p in xy_pairs]
    idx = bisect.bisect_left(xs, x)
    if idx == 0:
        return xy_pairs[0][1]
    if idx >= len(xy_pairs):
        return xy_pairs[-1][1]
    x0, y0 = xy_pairs[idx - 1]
    x1, y1 = xy_pairs[idx]
    frac = (x - x0) / (x1 - x0) if x1 > x0 else 0.0
    return y0 + frac * (y1 - y0)


def resample_elevation_profile(
    segment_points: list[tuple[float, float, float]], n: int = 200
) -> list[tuple[float, float]]:
    """
    Resampler et GPX-segment til n jævnt fordelte punkter langs distancen
    (lineær interpolation). Udjævner korte stigninger med få rå GPX-punkter,
    så sektionsgrænser ikke bliver støjede.
    """
    local_cum = [0.0]
    for i in range(1, len(segment_points)):
        d = haversine_km(
            segment_points[i - 1][0], segment_points[i - 1][1],
            segment_points[i][0], segment_points[i][1],
        )
        local_cum.append(local_cum[-1] + d)

    total = local_cum[-1]
    if total <= 0:
        raise ValueError("Segment har nul distance")

    xy_pairs = list(zip(local_cum, [p[2] for p in segment_points]))

    resampled = []
    for i in range(n):
        target = total * i / (n - 1)
        resampled.append((target, _interp_at(xy_pairs, target)))
    return resampled


def compute_gradient_sections(
    resampled: list[tuple[float, float]], n_sections: int = 10
) -> list[dict]:
    """Deler et resamplet højdeprofil i n_sections lige lange (efter distance) sektioner."""
    total = resampled[-1][0]
    section_len = total / n_sections

    sections = []
    for i in range(n_sections):
        start_km = i * section_len
        end_km = (i + 1) * section_len
        start_elev = _interp_at(resampled, start_km)
        end_elev = _interp_at(resampled, end_km)
        gradient = (end_elev - start_elev) / (section_len * 1000) * 100 if section_len > 0 else 0.0
        sections.append({
            "start_km":     round(start_km, 3),
            "end_km":       round(end_km, 3),
            "start_elev":   round(start_elev, 1),
            "end_elev":     round(end_elev, 1),
            "avg_gradient": round(gradient, 1),
        })
    return sections
```

- [ ] **Step 4: Kør testen og bekræft den passerer**

Run: `python agents/test_climb_profile_generator.py -v`
Expected: `OK` — alle tests inkl. de nye i `TestResampleElevationProfile` og `TestComputeGradientSections` passerer.

- [ ] **Step 5: Commit**

```bash
git add agents/climb_profile_generator.py agents/test_climb_profile_generator.py
git commit -m "feat: resample hoejdeprofil og beregn 10 gradient-sektioner"
```

---

### Task 6: Farveskala (gradient → RGB)

**Files:**
- Modify: `agents/climb_profile_generator.py` (tilføj sektion "Farve")
- Test: `agents/test_climb_profile_generator.py`

**Interfaces:**
- Consumes: ingen.
- Produces: `COLOR_STOPS: list[tuple[float, tuple[int, int, int]]]`, `gradient_to_color(gradient_pct: float) -> tuple[int, int, int]`.

- [ ] **Step 1: Skriv de fejlende tests**

```python
from climb_profile_generator import gradient_to_color


class TestGradientToColor(unittest.TestCase):
    def test_exact_control_points(self):
        self.assertEqual(gradient_to_color(0.0), (255, 255, 255))
        self.assertEqual(gradient_to_color(4.0), (253, 224, 166))
        self.assertEqual(gradient_to_color(7.0), (245, 148, 60))
        self.assertEqual(gradient_to_color(10.0), (214, 40, 40))
        self.assertEqual(gradient_to_color(13.0), (122, 12, 30))
        self.assertEqual(gradient_to_color(15.0), (10, 10, 10))

    def test_beyond_15_percent_clamps_to_black(self):
        self.assertEqual(gradient_to_color(22.0), (10, 10, 10))

    def test_negative_gradient_clamps_to_white(self):
        self.assertEqual(gradient_to_color(-5.0), (255, 255, 255))

    def test_midpoint_interpolates_between_stops(self):
        c = gradient_to_color(2.0)  # halvvejs mellem 0% (hvid) og 4% (lys rav)
        self.assertTrue(253 <= c[0] <= 255)
        self.assertTrue(224 <= c[1] <= 255)
        self.assertTrue(166 <= c[2] <= 255)
```

- [ ] **Step 2: Kør testen og bekræft den fejler**

Run: `python agents/test_climb_profile_generator.py -v`
Expected: `ImportError: cannot import name 'gradient_to_color'`.

- [ ] **Step 3: Implementér farveskalaen**

Tilføj til `agents/climb_profile_generator.py`:

```python
# ── Farve ───────────────────────────────────────────────────────────────────

COLOR_STOPS: list[tuple[float, tuple[int, int, int]]] = [
    (0.0,  (255, 255, 255)),  # hvid
    (4.0,  (253, 224, 166)),  # lys rav
    (7.0,  (245, 148, 60)),   # orange
    (10.0, (214, 40, 40)),    # rød
    (13.0, (122, 12, 30)),    # mørkerød
    (15.0, (10, 10, 10)),     # sort
]


def gradient_to_color(gradient_pct: float) -> tuple[int, int, int]:
    """Kontinuerlig, stykkevis-lineær farveskala fra hvid (0%) til sort (15%+)."""
    g = max(0.0, gradient_pct)
    if g >= COLOR_STOPS[-1][0]:
        return COLOR_STOPS[-1][1]
    for (g0, c0), (g1, c1) in zip(COLOR_STOPS, COLOR_STOPS[1:]):
        if g0 <= g <= g1:
            frac = (g - g0) / (g1 - g0)
            return tuple(int(round(c0[k] + frac * (c1[k] - c0[k]))) for k in range(3))
    return COLOR_STOPS[-1][1]
```

- [ ] **Step 4: Kør testen og bekræft den passerer**

Run: `python agents/test_climb_profile_generator.py -v`
Expected: `OK` — alle tests inkl. de 4 nye i `TestGradientToColor` passerer.

- [ ] **Step 5: Commit**

```bash
git add agents/climb_profile_generator.py agents/test_climb_profile_generator.py
git commit -m "feat: kontinuerlig hvid-til-sort farveskala for haeldning"
```

---

### Task 7: Rendering — to stilvarianter (full/minimal)

**Files:**
- Modify: `agents/climb_profile_generator.py` (tilføj sektion "Rendering")
- Test: `agents/test_climb_profile_generator.py`

**Interfaces:**
- Consumes: `gradient_to_color()` fra Task 6; sektions-dicts med nøglerne `start_km`, `end_km`, `start_elev`, `end_elev`, `avg_gradient` (samme form som `compute_gradient_sections()` producerer i Task 5).
- Produces: `render_climb_profile(climb_name: str, sections: list[dict], style: str, length_km: float, avg_gradient: float) -> PIL.Image.Image`. `style` skal være `"full"` eller `"minimal"`, ellers `ValueError`.

- [ ] **Step 1: Skriv de fejlende tests**

```python
from climb_profile_generator import render_climb_profile


class TestRenderClimbProfile(unittest.TestCase):
    def setUp(self):
        # To sektioner med tydeligt forskellig, eksplicit valgt avg_gradient,
        # saa udfyldningsfarven er entydig at forudsige. Elevation stiger jaevnt
        # saa toppolygonens kant ligger godt over baseline overalt undtagen i x=0.
        self.sections = [
            {"start_km": 0.0, "end_km": 1.0, "start_elev": 100.0, "end_elev": 300.0, "avg_gradient": 0.0},
            {"start_km": 1.0, "end_km": 2.0, "start_elev": 300.0, "end_elev": 500.0, "avg_gradient": 10.0},
        ]

    def test_image_has_expected_size(self):
        img = render_climb_profile("Test Climb", self.sections, "minimal",
                                    length_km=2.0, avg_gradient=5.0)
        self.assertEqual(img.size, (2400, 1200))
        self.assertEqual(img.mode, "RGB")

    def test_section_fill_colors_match_gradient_to_color(self):
        img = render_climb_profile("Test Climb", self.sections, "minimal",
                                    length_km=2.0, avg_gradient=5.0)

        pad_left, pad_right, pad_top, pad_bottom = 110, 40, 90, 90
        inner_w = 2400 - pad_left - pad_right
        baseline_y = pad_top + (1200 - pad_top - pad_bottom)
        sample_y = baseline_y - 5

        x_section1 = int(pad_left + (0.5 / 2.0) * inner_w)  # midt i sektion 1 (0-1km)
        x_section2 = int(pad_left + (1.5 / 2.0) * inner_w)  # midt i sektion 2 (1-2km)

        self.assertEqual(img.getpixel((x_section1, sample_y)), (255, 255, 255))
        self.assertEqual(img.getpixel((x_section2, sample_y)), (214, 40, 40))

    def test_rejects_unknown_style(self):
        with self.assertRaises(ValueError):
            render_climb_profile("Test Climb", self.sections, "ugyldig",
                                  length_km=2.0, avg_gradient=5.0)
```

- [ ] **Step 2: Kør testen og bekræft den fejler**

Run: `python agents/test_climb_profile_generator.py -v`
Expected: `ImportError: cannot import name 'render_climb_profile'`.

- [ ] **Step 3: Implementér rendering**

Tilføj til `agents/climb_profile_generator.py`:

```python
# ── Rendering ───────────────────────────────────────────────────────────────

WIDTH, HEIGHT = 2400, 1200
BG_COLOR = (15, 23, 42)        # slate-900
TEXT_COLOR = (226, 232, 240)   # slate-200
GRID_COLOR = (51, 65, 85)      # slate-700
LINE_COLOR = (241, 245, 249)   # slate-100 (terrænkant)
BRAND_COLOR = (100, 116, 139)  # slate-500

PAD_LEFT, PAD_RIGHT, PAD_TOP, PAD_BOTTOM = 110, 40, 90, 90

_FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def _font(size: int):
    for p in _FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def render_climb_profile(
    climb_name: str,
    sections: list[dict],
    style: str,
    length_km: float,
    avg_gradient: float,
) -> Image.Image:
    """
    Renderer et ClimbFinder-inspireret stigningsprofil-billede.
    sections: output fra compute_gradient_sections().
    style: "full" (akser, %-labels, titel) eller "minimal" (kun kurve + højder).
    """
    if style not in ("full", "minimal"):
        raise ValueError(f"Ukendt stil: {style}")

    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    inner_w = WIDTH - PAD_LEFT - PAD_RIGHT
    inner_h = HEIGHT - PAD_TOP - PAD_BOTTOM

    all_elevs = [s["start_elev"] for s in sections] + [sections[-1]["end_elev"]]
    min_elev, max_elev = min(all_elevs), max(all_elevs)
    elev_range = max(max_elev - min_elev, 1.0)
    max_elev_padded = max_elev + elev_range * 0.08

    total_km = sections[-1]["end_km"]
    baseline_y = PAD_TOP + inner_h

    def to_xy(km: float, elev: float) -> tuple[float, float]:
        x = PAD_LEFT + (km / total_km) * inner_w
        y = PAD_TOP + inner_h - ((elev - min_elev) / (max_elev_padded - min_elev)) * inner_h
        return x, y

    # Terrænsektioner — hver farvet efter sin egen gennemsnitshældning
    for s in sections:
        x0, y0 = to_xy(s["start_km"], s["start_elev"])
        x1, y1 = to_xy(s["end_km"], s["end_elev"])
        color = gradient_to_color(s["avg_gradient"])
        draw.polygon([(x0, baseline_y), (x0, y0), (x1, y1), (x1, baseline_y)], fill=color)

    # Terrænkant
    outline_pts = [to_xy(s["start_km"], s["start_elev"]) for s in sections]
    outline_pts.append(to_xy(sections[-1]["end_km"], sections[-1]["end_elev"]))
    draw.line(outline_pts, fill=LINE_COLOR, width=4)

    start_elev = sections[0]["start_elev"]
    summit_elev = sections[-1]["end_elev"]

    if style == "full":
        for i in range(5):
            elev = min_elev + (max_elev_padded - min_elev) * i / 4
            _, y = to_xy(0, elev)
            draw.line([(PAD_LEFT, y), (WIDTH - PAD_RIGHT, y)], fill=GRID_COLOR, width=1)
            draw.text((PAD_LEFT - 15, y), f"{int(round(elev))}m", font=_font(24),
                       fill=TEXT_COLOR, anchor="rm")

        step = max(1, round(total_km / 8))
        km_marker = 0
        while km_marker <= total_km:
            x, _ = to_xy(km_marker, min_elev)
            draw.line([(x, baseline_y), (x, baseline_y + 8)], fill=GRID_COLOR, width=1)
            draw.text((x, baseline_y + 15), f"{km_marker}km", font=_font(22),
                       fill=TEXT_COLOR, anchor="ma")
            km_marker += step

        for s in sections:
            mid_km = (s["start_km"] + s["end_km"]) / 2
            mid_elev = (s["start_elev"] + s["end_elev"]) / 2
            x, y = to_xy(mid_km, mid_elev)
            draw.text((x, y - 20), f"{s['avg_gradient']:.0f}%", font=_font(26),
                       fill=(255, 255, 255), anchor="mb", stroke_width=2, stroke_fill=(0, 0, 0))

        draw.text((PAD_LEFT, 30), climb_name, font=_font(40), fill=TEXT_COLOR, anchor="lm")
        draw.text((PAD_LEFT, 65), f"{length_km:.1f} km @ {avg_gradient:.1f}%",
                   font=_font(26), fill=BRAND_COLOR, anchor="lm")
        draw.text((WIDTH - PAD_RIGHT, HEIGHT - 20), "klassementet.dk",
                   font=_font(22), fill=BRAND_COLOR, anchor="rb")

    x0, y0 = to_xy(0, start_elev)
    draw.text((x0, y0 + 15), f"{int(round(start_elev))}m", font=_font(30),
               fill=TEXT_COLOR, anchor="ma")
    x1, y1 = to_xy(total_km, summit_elev)
    draw.text((x1, y1 - 15), f"{int(round(summit_elev))}m", font=_font(30),
               fill=TEXT_COLOR, anchor="mb")

    return img
```

- [ ] **Step 4: Kør testen og bekræft den passerer**

Run: `python agents/test_climb_profile_generator.py -v`
Expected: `OK` — alle tests inkl. de 3 nye i `TestRenderClimbProfile` passerer.

- [ ] **Step 5: Commit**

```bash
git add agents/climb_profile_generator.py agents/test_climb_profile_generator.py
git commit -m "feat: render stigningsprofil-billeder i full/minimal stilarter"
```

---

### Task 8: Supabase-integration og CLI

**Files:**
- Modify: `agents/climb_profile_generator.py` (tilføj sektioner "Supabase" og "Hovedpipeline", samt `if __name__ == "__main__"`)

**Interfaces:**
- Consumes: alle funktioner fra Task 1-7 (`download_stage_gpx`, `cumulative_distances_km`, `locate_climb_segment`, `derive_climb_stats`, `within_tolerance`, `resample_elevation_profile`, `compute_gradient_sections`, `render_climb_profile`).
- Produces: `get_race_id`, `get_stage`, `get_climbs_for_stage`, `upload_image`, `update_climb_profile`, `process_climb`, `process_stage`. Ingen automatiseret test (netværk/DB-afhængigt) — verificeres manuelt i Task 9, som er house-konventionen for alle andre scripts i `agents/`.

- [ ] **Step 1: Tilføj Supabase-hjælpefunktioner**

Tilføj til `agents/climb_profile_generator.py`:

```python
# ── Supabase ────────────────────────────────────────────────────────────────

def get_race_id(race_slug: str) -> str | None:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/races?slug=eq.{race_slug}&select=id&limit=1",
        headers=SB_AUTH,
    )
    data = res.json()
    return data[0]["id"] if res.ok and data else None


def get_stage(race_id: str, stage_number: int) -> dict | None:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stages"
        f"?race_id=eq.{race_id}&stage_number=eq.{stage_number}"
        f"&select=id,stage_number,distance_km&limit=1",
        headers=SB_AUTH,
    )
    data = res.json()
    return data[0] if res.ok and data else None


def get_climbs_for_stage(stage_id: str) -> list[dict]:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stage_climbs"
        f"?stage_id=eq.{stage_id}"
        f"&select=id,name,km_from_start,length_km,elevation_m,avg_gradient,profile_image_url"
        f"&order=km_from_start.asc",
        headers=SB_AUTH,
    )
    return res.json() if res.ok else []


def upload_image(path: str, data: bytes) -> str | None:
    res = requests.post(
        f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{path}",
        data=data,
        headers={**SB_AUTH, "Content-Type": "image/png", "x-upsert": "true"},
    )
    if not res.ok:
        print(f"    Upload fejl {res.status_code}: {res.text[:120]}")
        return None
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{path}"


def update_climb_profile(climb_id: str, profile_url: str) -> bool:
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/stage_climbs?id=eq.{climb_id}",
        json={"profile_image_url": profile_url, "source": "generated"},
        headers=SB_HEADERS,
    )
    return res.ok
```

- [ ] **Step 2: Tilføj hovedpipeline og CLI**

Tilføj til `agents/climb_profile_generator.py`:

```python
# ── Hovedpipeline ─────────────────────────────────────────────────────────────

def process_climb(
    stage: dict,
    climb: dict,
    gpx_points: list[tuple[float, float, float]],
    cum_dist: list[float],
    style: str,
    write_db: bool,
    overwrite: bool,
) -> str:
    """Genererer og gemmer profilbillede(r) for én stigning. Returnerer en statusbesked."""
    km_from_start = climb.get("km_from_start")
    length_km = climb.get("length_km")
    if km_from_start is None or not length_km:
        return f"  ✗ {climb['name']}: mangler km_from_start/length_km i DB"

    if write_db and climb.get("profile_image_url") and not overwrite:
        return f"  → {climb['name']}: har allerede et profilbillede, springer over (brug --overwrite)"

    try:
        segment = locate_climb_segment(
            gpx_points, cum_dist, stage["distance_km"],
            float(km_from_start), float(length_km),
        )
    except ValueError as e:
        return f"  ✗ {climb['name']}: {e}"

    derived = derive_climb_stats(segment)
    ok, reason = within_tolerance(derived, climb)
    if not ok:
        return f"  ✗ {climb['name']}: GPX-segment matcher ikke DB-data — {reason}"

    resampled = resample_elevation_profile(segment)
    sections = compute_gradient_sections(resampled)

    styles = ["full", "minimal"] if style == "both" else [style]
    urls = []
    for s in styles:
        img = render_climb_profile(
            climb["name"], sections, s,
            length_km=float(length_km),
            avg_gradient=float(climb.get("avg_gradient") or derived["avg_gradient"]),
        )
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        path = f"generated/{climb['id']}.png" if write_db else f"test/{climb['id']}-{s}.png"
        url = upload_image(path, buf.getvalue())
        if not url:
            return f"  ✗ {climb['name']} ({s}): upload fejlede"
        urls.append(url)

        if write_db and not update_climb_profile(climb["id"], url):
            return f"  ✗ {climb['name']}: DB-opdatering fejlede"

    status = "opdateret i DB" if write_db else "genereret (test)"
    return f"  ✓ {climb['name']} — {reason} — {status}: " + " | ".join(urls)


def process_stage(race_slug: str, stage_number: int, style: str, write_db: bool, overwrite: bool) -> None:
    if write_db and style == "both":
        print("Fejl: --write-db kræver ét enkelt --style (full eller minimal), ikke 'both'")
        return

    race_id = get_race_id(race_slug)
    if not race_id:
        print(f"Løb ikke fundet: {race_slug}")
        return

    stage = get_stage(race_id, stage_number)
    if not stage or not stage.get("distance_km"):
        print(f"Etape {stage_number} ikke fundet eller mangler distance_km")
        return

    climbs = get_climbs_for_stage(stage["id"])
    if not climbs:
        print("Ingen stigninger fundet for denne etape")
        return

    print(f"climb_profile_generator.py — {race_slug} etape {stage_number}")
    print("Henter GPX...")
    gpx_points = download_stage_gpx(race_slug, stage_number)
    if not gpx_points:
        print("Kunne ikke hente/parse GPX-fil for denne etape")
        return

    cum_dist = cumulative_distances_km(gpx_points)
    print(f"GPX: {len(gpx_points)} punkter, {cum_dist[-1]:.1f} km "
          f"(officiel distance: {stage['distance_km']} km)\n")

    for climb in climbs:
        print(process_climb(stage, climb, gpx_points, cum_dist, style, write_db, overwrite))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--race", required=True, help="Løb-slug, fx tour-de-france-2026")
    parser.add_argument("--stage", type=int, required=True, help="Etapenummer")
    parser.add_argument("--style", choices=["full", "minimal", "both"], default="both",
                         help="Hvilken stilart der skal genereres (default: begge, kun ved test)")
    parser.add_argument("--write-db", action="store_true",
                         help="Upload til generated/ og patch profile_image_url (default: kun test/-upload)")
    parser.add_argument("--overwrite", action="store_true",
                         help="Ved --write-db: overskriv stigninger der allerede har et profilbillede")
    args = parser.parse_args()

    process_stage(args.race, args.stage, args.style, args.write_db, args.overwrite)
```

- [ ] **Step 3: Verificér at scriptet stadig importerer uden fejl og at unit-testsuiten fortsat er grøn**

Run: `python agents/test_climb_profile_generator.py -v`
Expected: `OK` — samtlige tidligere tests passerer fortsat uændret (denne task tilføjer ingen nye automatiserede tests, kun netværks-/DB-kode der verificeres i Task 9).

- [ ] **Step 4: Commit**

```bash
git add agents/climb_profile_generator.py
git commit -m "feat: supabase-integration og CLI for climb_profile_generator.py"
```

---

### Task 9: Testkørsel — Tour de France 2026 etape 2

**Files:** ingen kodeændringer — dette er den aftalte testkørsel fra design-specens etape 2-testplan.

**Interfaces:**
- Consumes: `process_stage()` fra Task 8 via CLI.

- [ ] **Step 1: Kør scriptet for etape 2 i test-tilstand (begge stilarter, ingen DB-skrivning)**

Run: `python agents/climb_profile_generator.py --race tour-de-france-2026 --stage 2`

Expected: Output i stil med:

```
climb_profile_generator.py — tour-de-france-2026 etape 2
Henter GPX...
GPX: 5043 punkter, 178.8 km (officiel distance: 168.5 km)

  ✓ Côte de Begues — elev …≈407m | grad …≈5.9% — genereret (test): https://.../test/<id>-full.png | https://.../test/<id>-minimal.png
  ✓ Côte de Santa Creu d'Olorda — … — genereret (test): …
  ✓ Côte du Castell de Montjuïc — … — genereret (test): …
  ✓ Côte de l'Estadi Olímpic — … — genereret (test): …
```

- [ ] **Step 2: Verificér resultatet**

For hver af de 4 stigninger skal der være **2** URL'er i output (full + minimal), i alt 8 billeder uploadet til `test/`-stien i `stage-profiles`-bucketen. Hvis en stigning fejler valideringen (✗), noter årsagen — det betyder enten at GPX-segmentets udledte stats afviger for meget fra DB'ens data (tegn på forkert lokaliseret segment, bør undersøges før videre brug for netop den stigning) eller manglende `km_from_start`/`length_km`.

- [ ] **Step 3: Rapportér til ejeren**

Saml de 8 URL'er (grupperet pr. stigning: full vs. minimal) i et overskueligt format, og bed ejeren om at åbne dem og vælge en stilart. Skriv resultatet af testkørslen (antal succesfulde/afviste stigninger, evt. afvisningsårsager) til `state/issues.md` som et nyt issue (fx `STG-005`, status `AFVENTER_EJER`), jf. `PROTOKOL.md`'s krav om at logge fund på tværs af kørsler.

- [ ] **Step 4: Commit issues.md-opdateringen**

```bash
git add state/issues.md
git commit -m "docs(STG-005): log etape 2-testkoersel af GPX-stigningsprofil-generator"
```

**Ikke en del af denne plan (afventer ejerens stilvalg fra Step 3):** genkørsel med `--write-db` for de stigninger, der mangler et verificeret ClimbFinder-billede (Côte de Begues, Côte de l'Estadi Olímpic), med den valgte stilart. Kommando, når stilarten er valgt:

```bash
python agents/climb_profile_generator.py --race tour-de-france-2026 --stage 2 --style <full|minimal> --write-db
```

---

## Self-Review

**Spec-dækning:** Alle sektioner fra design-specen er dækket — GPX-parsing m. højde (Task 1), geometri/proportional lokalisering (Task 2-3), tolerance-validering (Task 4), 10-sektions gradientberegning (Task 5), farveskala (Task 6), to render-stilarter (Task 7), Supabase-integration + `source="generated"`-tagging (Task 8), og etape 2-testplanens 3 trin (Task 9). Produktions-DB-skrivning for de to stigninger uden ClimbFinder-match er bevidst efterladt som en opfølgende, bruger-gated kommando (jf. specens Fase 3-4), ikke en plan-task, da den afhænger af et valg ejeren først kan træffe efter at have set testbillederne.

**Placeholder-scan:** Ingen TBD/TODO — alle steps indeholder komplet, kørbar kode eller eksakte kommandoer.

**Typekonsistens:** `sections`-dict-nøglerne (`start_km`, `end_km`, `start_elev`, `end_elev`, `avg_gradient`) er identiske mellem `compute_gradient_sections()` (Task 5) og `render_climb_profile()` (Task 7). GPX-punktformatet `(lat, lon, ele)` er konsistent fra `parse_gpx_with_elevation()` (Task 1) gennem `locate_climb_segment()`, `derive_climb_stats()` og `resample_elevation_profile()`. `within_tolerance()`s `derived`-dict-nøgler matcher præcis det `derive_climb_stats()` returnerer.
