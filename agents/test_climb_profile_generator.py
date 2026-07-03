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

from climb_profile_generator import (
    parse_gpx_with_elevation,
    haversine_km,
    cumulative_distances_km,
    locate_climb_segment,
    derive_climb_stats,
    within_tolerance,
)


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


if __name__ == "__main__":
    unittest.main()
