"""
test_gpx_builder.py
Unit-tests for de rene funktioner i gpx_builder.py (geometri og kontrol).
Netværket (Nominatim, BRouter, Open Topo Data) testes ikke her — det
kalibreres mod en rigtig etape med facit, jf. SKILL.md (Vuelta 2026 etape 9).

Kør: python agents/test_gpx_builder.py
"""

import unittest

from gpx_builder import (
    cum_km,
    densify,
    trim_spurs,
    trim_neutral_start,
    _decode_polyline,
    validate,
)

KM_LAT = 1 / 111.195  # grader breddegrad pr. km (samme jordradius som haversine)


def straight(km: float, step_km: float = 0.5, lat0: float = 45.0, lon: float = 10.0):
    """Et lige spor mod nord, ét punkt pr. step_km."""
    n = int(km / step_km)
    return [(lat0 + i * step_km * KM_LAT, lon) for i in range(n + 1)]


class TestDensify(unittest.TestCase):
    def test_keeps_vertices_and_length(self):
        # Et zigzag-spor: en jævn gensampling ville skære hjørnerne af.
        pts = [(45.0, 10.0), (45.01, 10.0), (45.01, 10.01), (45.02, 10.01)]
        ud = densify(pts, 50)
        for p in pts:
            self.assertIn(p, ud)
        self.assertAlmostEqual(cum_km(ud)[-1], cum_km(pts)[-1], places=6)
        self.assertTrue(all(b - a <= 0.0501 for a, b in zip(cum_km(ud), cum_km(ud)[1:])))


class TestTrimSpurs(unittest.TestCase):
    def test_removes_short_out_and_back(self):
        frem = [(45.0, 10.0 + i * 0.001) for i in range(10)]          # mod øst
        blindgyde = [(45.0 + i * 0.001, 10.009) for i in range(1, 6)]  # 0,55 km nordpå
        tilbage = list(reversed(blindgyde[:-1])) + [(45.0, 10.009)]
        videre = [(45.0, 10.010 + i * 0.001) for i in range(10)]
        pts = frem + blindgyde + tilbage + videre
        via = len(frem) + len(blindgyde) - 1  # toppen af blindgyden
        ud, fjernet = trim_spurs(pts, [via])
        self.assertGreater(fjernet, 800)
        self.assertLess(cum_km(ud)[-1], cum_km(pts)[-1] - 0.8)

    def test_keeps_long_out_and_back(self):
        # Et frem-og-tilbage på 2 × 5 km er løbets egen rute, ikke en omvej.
        ud_ = [(45.0 + i * 0.5 * KM_LAT, 10.0) for i in range(11)]
        pts = ud_ + list(reversed(ud_[:-1]))
        _, fjernet = trim_spurs(pts, [10])
        self.assertEqual(fjernet, 0)


class TestNeutralStart(unittest.TestCase):
    def test_trims_offset_found_from_towns(self):
        pts = straight(50)
        # Officielt km 0 ligger 4 km nord for byen; byerne står med officielle km.
        wps = [{"name": "start", "km": 0.0, "lat": pts[0][0], "lon": 10.0}]
        for off in (10, 20, 30):
            wps.append({"name": f"by{off}", "km": off - 4.0, "lat": pts[off * 2][0], "lon": 10.0})
        wps.append({"name": "mål", "km": 46.0, "lat": pts[-1][0], "lon": 10.0})
        ud, neutral = trim_neutral_start(pts, wps)
        self.assertAlmostEqual(neutral, 4.0, places=1)
        self.assertAlmostEqual(cum_km(ud)[-1], 46.0, places=1)

    def test_no_trim_when_towns_fit(self):
        pts = straight(30)
        wps = [{"name": n, "km": k, "lat": pts[int(k * 2)][0], "lon": 10.0}
               for n, k in (("a", 0.0), ("b", 10.0), ("c", 20.0), ("d", 30.0))]
        _, neutral = trim_neutral_start(pts, wps)
        self.assertEqual(neutral, 0.0)


class TestPolyline(unittest.TestCase):
    def test_google_reference_example(self):
        # Googles eget eksempel i formatdokumentationen.
        pts = _decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
        self.assertEqual(pts, [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)])


class TestValidate(unittest.TestCase):
    def _spec(self, wps, official):
        return {"race": "test-uden-ankre", "stage": 1, "official_km": official, "waypoints": wps}

    def _run(self, track_km, town_km_official, town_km_routed, official):
        pts = densify(straight(track_km), 50)
        cum = cum_km(pts)
        eles = [100.0 + c for c in cum]  # 0,1 % — langt under 25 %-grænsen
        wps, idx = [], []
        for off, routed in zip(town_km_official, town_km_routed):
            i = min(range(len(cum)), key=lambda k: abs(cum[k] - routed))
            wps.append({"name": f"km{off}", "km": off, "lat": pts[i][0], "lon": pts[i][1]})
            idx.append(i)
        return validate(self._spec(wps, official), pts, eles, idx)

    def test_even_drift_passes(self):
        # Ruten er jævnt 1 % længere end roadbooken (som cyclingstage mod ASO).
        off = [0, 20, 40, 60, 80, 100]
        r = self._run(101, off, [k * 1.01 for k in off], 100.0)
        self.assertTrue(r["ok"], r["fejl"])

    def test_wrong_road_jump_fails(self):
        # Én strækning 3 km for kort (genvej udenom et pas) — et spring.
        off = [0, 20, 40, 60, 80, 100]
        routed = [0, 20, 40, 57, 77, 97]
        r = self._run(97, off, routed, 100.0)
        self.assertFalse(r["ok"])
        self.assertTrue(any("fra linjen" in f for f in r["fejl"]), r["fejl"])

    def test_total_distance_fails(self):
        off = [0, 50, 100]
        r = self._run(90, off, [0, 45, 90], 100.0)
        self.assertFalse(r["ok"])
        self.assertTrue(any("samlet distance" in f for f in r["fejl"]))


if __name__ == "__main__":
    unittest.main()
