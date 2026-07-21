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
    resample_elevation_profile,
    compute_gradient_sections,
    gradient_to_color,
    render_climb_profile,
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
        # Rute: 201 punkter, 0.5 km imellem hver (cum_dist = 0.5*i), 100 km total.
        # Fladt 0-50km (50m) -> lineaer klatring 50-74km (50m -> 450m) -> fladt 74-100km (450m).
        self.cum = [round(0.5 * i, 3) for i in range(201)]
        elevations = []
        for i in range(201):
            if i < 100:
                elevations.append(50.0)
            elif i <= 148:
                elevations.append(50.0 + (i - 100) * (400.0 / 48))
            else:
                elevations.append(450.0)
        self.points = [(0.0, 0.0, e) for e in elevations]
        self.db_climb = {"elevation_m": 400, "avg_gradient": round(400 / 24000 * 100, 2)}

    def test_finds_climb_when_naive_estimate_is_accurate(self):
        # Officiel distance = GPX-total (100 km), saa det proportionale gaet
        # rammer klatringens rigtige start (50 km) praecist.
        segment = locate_climb_segment(self.points, self.cum, stage_distance_km=100.0,
                                        km_from_start=50.0, length_km=24.0, db_climb=self.db_climb)
        derived = derive_climb_stats(segment)
        self.assertAlmostEqual(derived["elevation_gain_m"], 400, delta=15)

    def test_recovers_when_naive_estimate_overshoots(self):
        # Officiel distance (90 km) != GPX-total (100 km) -> det proportionale
        # gaet rammer 70 km (inde i klatringen/paa vej ud i den flade
        # efterfoelgende straekning), 20 km fra klatringens rigtige start (50 km) —
        # samme slags overskud som blev fundet paa tour-de-france-2026 etape 2.
        # Soegningen skal stadig finde den rigtige klatring inden for radius.
        segment = locate_climb_segment(self.points, self.cum, stage_distance_km=90.0,
                                        km_from_start=63.0, length_km=21.6, db_climb=self.db_climb)
        derived = derive_climb_stats(segment)
        self.assertAlmostEqual(derived["elevation_gain_m"], 400, delta=30)
        self.assertGreater(derived["elevation_gain_m"], 300)  # ikke den flade decoy-straekning (~0-90m)

    def test_raises_on_invalid_stage_distance(self):
        with self.assertRaises(ValueError):
            locate_climb_segment(self.points, self.cum, stage_distance_km=0,
                                  km_from_start=1.0, length_km=2.0, db_climb=self.db_climb)

    def test_raises_when_km_from_start_exceeds_stage_distance(self):
        # Set fejlaflaest kildedata (fx vision-laesning der har blandet
        # kumulativ etapeafstand ind) skal afvises frem for at crashe
        # array-indekseringen laengere nede (STG-024).
        with self.assertRaises(ValueError):
            locate_climb_segment(self.points, self.cum, stage_distance_km=100.0,
                                  km_from_start=469.0, length_km=8.3, db_climb=self.db_climb)

    def test_raises_when_km_from_start_negative(self):
        with self.assertRaises(ValueError):
            locate_climb_segment(self.points, self.cum, stage_distance_km=100.0,
                                  km_from_start=-5.0, length_km=8.3, db_climb=self.db_climb)


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


if __name__ == "__main__":
    unittest.main()
