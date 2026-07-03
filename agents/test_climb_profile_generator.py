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


if __name__ == "__main__":
    unittest.main()
