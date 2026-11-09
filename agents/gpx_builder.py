"""
gpx_builder.py
Bygger en GPX-rute til et løb, der ikke har en GPX-kilde (cyclingstage.com),
ud fra arrangørens egne oplysninger — og udgiver den KUN, hvis den består
kontrollen mod de officielle tal. Ejer-godkendt 2026-11-08.

Arbejdsgangen og reglerne står i .claude/skills/gpx-fra-rute/SKILL.md. Kort:

  Metode "itinerary": byerne langs ruten med officielle km (fra køreplanen,
      profilbilledets byetiketter eller roadbooken) slås op og bindes sammen
      af en ruteplanlægger på OpenStreetMap (BRouter, profil "moped": almindelige
      veje med biladgang, ingen motorvej, ingen stier — det, et feltløb kører på).
  Metode "track": arrangørens eget spor (GeoJSON/KML/GPX/kodet polyline, fx
      opfanget fra det interaktive kort) bruges direkte.

I begge tilfælde lægges højden på fra EU-DEM 25 m (SRTM 30 m uden for Europa)
via Open Topo Data, og ruten kontrolleres mod:

  1. officiel samlet distance                       (højst 2 % afvigelse)
  2. hver bys officielle km                         (højst max(1 km, 1,2 %))
  3. hver bys officielle højde, hvis den kendes     (højst 50 m)
  4. den officielle højdekurve, hvis løbet har ankre i profile_image_anchors.json
                                                    (median ≤ 30 m, 95 %-fraktil ≤ 90 m)
  5. ingen kilometer stejlere end 25 %

Kun en rute, der består ALLE kontroller, skrives til data/gpx/<løb>/stage-N.gpx,
hvor climb_profile_generator.download_stage_gpx() finder den, når cyclingstage
ikke har etapen. Ellers lægges kandidaten i output/gpx_kandidater/ til review,
og intet i pipelinen ser den (CLAUDE.md §6).

Kør:
    python agents/gpx_builder.py --spec data/gpx/giro-d-italia-2027/stage-2.json
    python agents/gpx_builder.py --race giro-d-italia-2027 --all
    python agents/gpx_builder.py --race giro-d-italia-2027 --stage 2 --dry-run
"""

import os
import sys
import json
import math
import time
import argparse
import datetime as dt
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import climb_profile_generator as cpg  # noqa: E402  (pakker selv stdout ind)

ROOT = Path(__file__).resolve().parent.parent
GPX_DIR = cpg.LOCAL_GPX_DIR
KANDIDAT_DIR = ROOT / "output" / "gpx_kandidater"

# Ingen mailadresse i User-Agent (ejeren skal forblive anonym).
UA = "klassementet-gpx-builder/1.0"

BROUTER_URL = "https://brouter.de/brouter"
BROUTER_PROFILE = "moped"
BROUTER_PAUSE_S = 1.0     # mellem kald til den offentlige server
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
TOPO_URL = "https://api.opentopodata.org/v1/eudem25m,srtm30m"
TOPO_BATCH = 100          # Open Topo Datas grænse pr. kald
TOPO_PAUSE_S = 1.1        # 1 kald pr. sekund på den offentlige instans

DENSIFY_M = 50            # største afstand mellem to punkter i den færdige GPX

# Tolerancer — se modulets docstring.
TOL_TOTAL_REL = 0.02
TOL_KM_SLOPE = 0.03       # rute-km pr. officiel km, højst ±3 %
TOL_KM_OFFSET = 3.0       # linjens forskydning ved km 0
TOL_WP_RESID_KM = 1.0     # en bys afstand fra linjen
TOL_WP_ELE_M = 50
TOL_PROFILE_MEDIAN_M = 30
TOL_PROFILE_P95_M = 90
MAX_KM_GRADIENT = 25.0
SPUR_MAX_GAP_M = 25       # to punkter så tæt er "samme sted" ved spor-trimning
SPUR_MAX_KM = 3.0         # længste blindgyde (frem + tilbage), der klippes
NEUTRAL_MAX_KM = 15.0     # længste neutrale start, vi klipper af


# ── Geometri ─────────────────────────────────────────────────────────────────

haversine_km = cpg.haversine_km


def cum_km(pts) -> list[float]:
    out = [0.0]
    for a, b in zip(pts, pts[1:]):
        out.append(out[-1] + haversine_km(a[0], a[1], b[0], b[1]))
    return out


def densify(pts: list[tuple[float, float]], step_m: float) -> list[tuple[float, float]]:
    """Indsætter punkter, hvor to knuder ligger mere end step_m fra hinanden.
    BRouters knuder kan ligge flere hundrede meter fra hinanden på en lige vej,
    og så ville højdemodellen kun blive spurgt dér — en stigning midt på
    strækningen ville forsvinde.

    Alle oprindelige knuder bevares. En jævn gensampling skar hjørnerne af på
    snoede veje: cyclingstages spor for Vuelta 2026 etape 9 blev 4 km kortere
    (188,7 → 184,7 km)."""
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        d_m = haversine_km(a[0], a[1], b[0], b[1]) * 1000
        n = int(d_m // step_m)
        for k in range(1, n + 1):
            t = k / (n + 1)
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
        if d_m > 0:
            out.append(b)
    return out


def nearest_index(pts, lat, lon, start=0) -> int:
    best, best_d = start, float("inf")
    for i in range(start, len(pts)):
        d = haversine_km(lat, lon, pts[i][0], pts[i][1])
        if d < best_d:
            best, best_d = i, d
    return best


def trim_spurs(pts: list[tuple[float, float]], via_idx: list[int]) -> tuple[list, int]:
    """Fjerner blindgyder omkring via-punkterne.

    Et bynavn geokodes til byens midte. Ligger midten 300 m fra løbets vej,
    kører ruteplanlæggeren derind og samme vej ud igen — en blindgyde, der
    lægger km til og flytter alle senere byer. Vi går baglæns og forlæns fra
    via-punktet, så længe de to retninger ligger oven i hinanden, og klipper
    stykket ud."""
    keep = [True] * len(pts)
    removed_m = 0.0
    for k in via_idx:
        a, b = k, k
        while a > 0:
            lo, hi = b, min(len(pts), b + 60)
            cand = min(range(lo, hi), key=lambda i: haversine_km(*pts[a - 1], *pts[i]), default=None)
            if cand is None or haversine_km(*pts[a - 1], *pts[cand]) * 1000 > SPUR_MAX_GAP_M:
                break
            a, b = a - 1, cand
        if b - a > 1:
            seg = cum_km(pts[a:b + 1])[-1]
            # Kun korte omveje ind til en bymidte. Et længere frem-og-tilbage
            # er løbets egen rute (Giro 2027 etape 2 mistede 10 km uden loftet),
            # og den tæller med i de officielle km.
            if 0.05 < seg <= SPUR_MAX_KM:
                removed_m += seg * 1000
                for i in range(a + 1, b):
                    keep[i] = False
    return [p for p, k in zip(pts, keep) if k], round(removed_m)


def trim_neutral_start(pts, wps) -> tuple[list, float]:
    """Klipper den neutrale start af.

    Officielt km 0 ligger ikke i startbyen: feltet kører først en neutraliseret
    strækning ud af byen (Giro 2027 etape 2: Ljubljanas centrum ligger 26 km
    fra Logatec i fugleflugt, men løbet angiver 24,5 km). Ruten planlægges fra
    byen, og km 0 findes som den forskydning, der får de mellemliggende byer
    til at passe — medianen, så én dårligt geokodet by ikke flytter alt.
    Kontrollen af hver by bagefter afgør, om forskydningen var rigtig."""
    cum = cum_km(pts)
    diffs, start = [], 0
    for w in wps[1:-1]:
        start = nearest_index(pts, w["lat"], w["lon"], start)
        if w.get("km") is not None:
            diffs.append(cum[start] - w["km"])
    if not diffs:
        return pts, 0.0
    offset = sorted(diffs)[len(diffs) // 2]
    if offset < 0.3 or offset > NEUTRAL_MAX_KM:
        return pts, 0.0
    j = next(i for i, c in enumerate(cum) if c >= offset)
    t = (offset - cum[j - 1]) / (cum[j] - cum[j - 1])
    km0 = (pts[j - 1][0] + (pts[j][0] - pts[j - 1][0]) * t,
           pts[j - 1][1] + (pts[j][1] - pts[j - 1][1]) * t)
    return [km0] + pts[j:], offset


# ── Eksterne tjenester ───────────────────────────────────────────────────────

def geocode(q: str) -> tuple[float, float] | None:
    # featureType=settlement: uden den svarer Nominatim gerne med KOMMUNENS
    # midtpunkt (en grænserelation) — for Logatec 4 km fra byen, og så lagde
    # ruteplanlæggeren en omvej ud i skoven (fanget af fugleflugt-kontrollen).
    # Selv med filteret kommer kommunen først (Logatec: boundary foran
    # place=town), så vi tager det første egentlige sted blandt de fem bedste.
    # Uden filter som anden udvej: GPM-etiketter er ofte en TOP (Markovec ved
    # Koper er "natural=peak"), ikke en bebyggelse.
    for extra in ({"featureType": "settlement"}, {}):
        res = requests.get(NOMINATIM_URL, params={"q": q, "format": "json", "limit": 5, **extra},
                           headers={"User-Agent": UA}, timeout=30)
        time.sleep(1.1)  # Nominatims brugsregler: højst ét opslag pr. sekund
        hits = res.json() if res.ok else []
        if hits:
            hit = next((h for h in hits if h.get("class") in ("place", "natural", "mountain_pass")),
                       hits[0])
            return float(hit["lat"]), float(hit["lon"])
    return None


def route_brouter(waypoints: list[tuple[float, float]], alt: int = 0) -> list[tuple[float, float]]:
    lonlats = "|".join(f"{lon:.6f},{lat:.6f}" for lat, lon in waypoints)
    # Den offentlige server rationerer: "403 Please, retry later!" betyder
    # vent, ikke "ingen vej" — ellers ville punkt-flytningen i route_leg()
    # hamre løs og gøre det værre.
    for forsoeg in range(5):
        time.sleep(BROUTER_PAUSE_S)
        res = requests.get(BROUTER_URL, params={
            "lonlats": lonlats, "profile": BROUTER_PROFILE,
            "alternativeidx": alt, "format": "geojson",
        }, headers={"User-Agent": UA}, timeout=120)
        if res.status_code in (403, 429) and "retry" in res.text.lower():
            vent = 30 * (forsoeg + 1)
            print(f"    (BRouter beder om pause — venter {vent} s)")
            time.sleep(vent)
            continue
        break
    if not res.ok:
        # BRouter forklarer i klartekst, fx hvilket punkt der ikke ligger ved en vej.
        raise RuntimeError(f"BRouter {res.status_code}: {res.text.strip()[:300]}")
    coords = res.json()["features"][0]["geometry"]["coordinates"]
    return [(c[1], c[0]) for c in coords]


def _nudged(lat: float, lon: float):
    """Punkter i ringe om (lat, lon) — 300, 600 og 900 m i otte retninger."""
    for r_m in (300, 600, 900):
        for k in range(8):
            v = math.radians(45 * k)
            yield (lat + r_m * math.cos(v) / 111_320,
                   lon + r_m * math.sin(v) / (111_320 * math.cos(math.radians(lat))))


def route_leg(a: dict, b: dict, target_km: float | None):
    """Én strækning mellem to waypoints. Returnerer (spor, a', b', alt) eller
    kaster RuntimeError.

    * Ligger et punkt et sted, profilen ikke må køre (Ljubljanas gågader, en
      bjergtop uden vej), flyttes det ud i en ring, til der findes en vej.
    * Feltet kører sjældent den hurtigste vej: Galantiči → Srgaši er 18,5 km
      ad BRouters første forslag, men 24,4 km officielt. Kendes strækningens
      officielle længde, prøves alle fire alternativer, og det, der passer
      bedst, vælges. Højdekurve-kontrollen afgør bagefter, om valget holdt."""
    pa, pb = (a["lat"], a["lon"]), (b["lat"], b["lon"])
    sidste = None
    for qa in [pa, *_nudged(*pa)]:
        for qb in [pb, *(_nudged(*pb) if qa == pa else [])]:
            try:
                first = route_brouter([qa, qb], 0)
            except RuntimeError as e:
                sidste = e
                continue
            if target_km is None:
                return first, qa, qb, 0
            best, best_alt = first, 0
            for alt in (1, 2, 3):
                if abs(cum_km(best)[-1] - target_km) <= 0.02 * target_km:
                    break
                try:
                    cand = route_brouter([qa, qb], alt)
                except RuntimeError:
                    break  # BRouter har ikke flere alternativer
                if abs(cum_km(cand)[-1] - target_km) < abs(cum_km(best)[-1] - target_km):
                    best, best_alt = cand, alt
            return best, qa, qb, best_alt
    raise RuntimeError(f"{a['name']} → {b['name']}: {sidste}")


def elevations(pts: list[tuple[float, float]]) -> list[float]:
    out: list[float] = []
    for i in range(0, len(pts), TOPO_BATCH):
        chunk = pts[i:i + TOPO_BATCH]
        locs = "|".join(f"{lat:.6f},{lon:.6f}" for lat, lon in chunk)
        for forsoeg in range(3):
            res = requests.post(TOPO_URL, data={"locations": locs},
                                headers={"User-Agent": UA}, timeout=60)
            if res.status_code == 429:
                time.sleep(5 * (forsoeg + 1))
                continue
            res.raise_for_status()
            break
        else:
            raise RuntimeError("Open Topo Data blev ved med at svare 429")
        for r in res.json()["results"]:
            if r["elevation"] is None:
                raise RuntimeError(f"ingen højde ved {r['location']}")
            out.append(float(r["elevation"]))
        time.sleep(TOPO_PAUSE_S)
    return out


# ── Arrangørens spor (metode "track") ────────────────────────────────────────

def load_track(src: str) -> list[tuple[float, float]]:
    """GeoJSON, KML, GPX eller en kodet polyline (Google-format, præcision 5)."""
    if src.startswith("http"):
        res = requests.get(src, headers={"User-Agent": UA}, timeout=60)
        res.raise_for_status()
        text = res.text
    else:
        path = Path(src) if Path(src).is_absolute() else ROOT / src
        text = path.read_text(encoding="utf-8")
    t = text.lstrip()
    if t.startswith("{"):
        return _geojson_coords(json.loads(t))
    if t.startswith("<"):
        root = ET.fromstring(t)
        pts = [(float(e.get("lat")), float(e.get("lon"))) for e in root.iter()
               if e.tag.endswith(("trkpt", "rtept"))]
        if pts:
            return pts
        out = []
        for e in root.iter():
            if e.tag.endswith("coordinates") and e.text:
                for tok in e.text.split():
                    lon, lat, *_ = tok.split(",")
                    out.append((float(lat), float(lon)))
        return out
    return _decode_polyline(t.strip())


def _geojson_coords(gj) -> list[tuple[float, float]]:
    feats = gj.get("features") or [gj]
    out = []
    for f in feats:
        geom = f.get("geometry", f)
        cs = geom.get("coordinates", [])
        if geom.get("type") == "MultiLineString":
            cs = [c for line in cs for c in line]
        if geom.get("type") in ("LineString", "MultiLineString"):
            out.extend((c[1], c[0]) for c in cs)
    return out


def _decode_polyline(s: str, precision: int = 5) -> list[tuple[float, float]]:
    out, idx, lat, lon, f = [], 0, 0, 0, 10 ** precision
    while idx < len(s):
        for which in (0, 1):
            shift = result = 0
            while True:
                b = ord(s[idx]) - 63
                idx += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            d = ~(result >> 1) if result & 1 else result >> 1
            if which == 0:
                lat += d
            else:
                lon += d
        out.append((lat / f, lon / f))
    return out


# ── Kontrol ──────────────────────────────────────────────────────────────────

def validate(spec, pts, eles, wp_idx) -> dict:
    cum = cum_km(pts)
    total = cum[-1]
    official = float(spec["official_km"])
    profil = list(zip(cum, eles))
    checks, fejl = {}, []

    rel = (total - official) / official
    checks["distance"] = {"routed_km": round(total, 2), "official_km": official,
                          "afvigelse_pct": round(rel * 100, 2)}
    if abs(rel) > TOL_TOTAL_REL:
        fejl.append(f"samlet distance {total:.1f} km mod officielle {official:.1f} km "
                    f"({rel * 100:+.1f} %, grænse ±{TOL_TOTAL_REL * 100:.0f} %)")

    # Byernes km måles mod en ret linje (rute-km = a + b · officielle km), ikke
    # direkte. Kalibreret mod cyclingstages GPX for Vuelta 2026 etape 9: selv
    # den afviger op til 2 km fra roadbookens tal (Pego 68,6 mod 66,7), fordi et
    # opmålt spor og roadbooken glider jævnt fra hinanden, og en bys midte ikke
    # ligger på ruten. En jævn glidning er ufarlig; en strækning ad den forkerte
    # vej giver derimod et SPRING, som linjen ikke kan forklare.
    par = [(wp["km"], cum[i]) for wp, i in zip(spec["waypoints"], wp_idx) if wp.get("km") is not None]
    n = len(par)
    mx = sum(x for x, _ in par) / n
    my = sum(y for _, y in par) / n
    sxx = sum((x - mx) ** 2 for x, _ in par)
    b = sum((x - mx) * (y - my) for x, y in par) / sxx if sxx else 1.0
    a = my - b * mx
    checks["km_linje"] = {"a_km": round(a, 2), "b": round(b, 4)}
    if abs(b - 1) > TOL_KM_SLOPE or abs(a) > TOL_KM_OFFSET:
        fejl.append(f"byernes km passer ikke (rute-km = {a:.1f} + {b:.3f} · officielle km)")

    wps = []
    for wp, i in zip(spec["waypoints"], wp_idx):
        if wp.get("km") is None:
            continue
        rest = cum[i] - (a + b * wp["km"])
        row = {"name": wp.get("name"), "official_km": wp["km"], "routed_km": round(cum[i], 2),
               "afvigelse_km": round(cum[i] - wp["km"], 2), "rest_km": round(rest, 2)}
        if abs(rest) > TOL_WP_RESID_KM:
            fejl.append(f"{wp.get('name')}: km {cum[i]:.1f} mod officielle {wp['km']:.1f} "
                        f"({rest:+.1f} km fra linjen)")
        if wp.get("ele") is not None:
            row["official_ele"] = wp["ele"]
            row["dem_ele"] = round(eles[i])
            if abs(eles[i] - wp["ele"]) > TOL_WP_ELE_M:
                fejl.append(f"{wp.get('name')}: højde {eles[i]:.0f} m mod officielle {wp['ele']} m")
        wps.append(row)
    checks["byer"] = wps

    # Officiel højdekurve (fra profile_image_digitizer, hvis løbet har ankre).
    # Ruten skaleres til den officielle længde, så små km-forskydninger ikke
    # forveksles med højdefejl; et forkert dalforløb giver stadig hundredvis af meter.
    try:
        from profile_image_digitizer import digitize_stage_profile
        kurve, dig = digitize_stage_profile(spec["race"], int(spec["stage"]), verbose=False)
    except Exception as e:  # noqa: BLE001
        kurve, dig = None, {"error": str(e)}
    if kurve:
        skaleret = [(c * official / total, e) for c, e in profil]
        devs = sorted(abs(cpg._interp_at(skaleret, k) - cpg._interp_at(kurve, k))
                      for k in [x * 0.5 for x in range(int(official * 2) + 1)])
        med = devs[len(devs) // 2]
        p95 = devs[int(len(devs) * 0.95)]
        checks["hoejdekurve"] = {"median_m": round(med), "p95_m": round(p95),
                                 "max_m": round(devs[-1])}
        if med > TOL_PROFILE_MEDIAN_M or p95 > TOL_PROFILE_P95_M:
            fejl.append(f"højdekurven afviger fra den officielle (median {med:.0f} m, "
                        f"95 % {p95:.0f} m; grænse {TOL_PROFILE_MEDIAN_M}/{TOL_PROFILE_P95_M} m)")
    else:
        checks["hoejdekurve"] = {"sprunget_over": dig.get("error", "ingen kurve")}

    stejlest, k = 0.0, 1.0
    while k <= total:
        stejlest = max(stejlest, abs(cpg._interp_at(profil, k) - cpg._interp_at(profil, k - 1.0)) / 10.0)
        k += 0.25
    checks["stejleste_km_pct"] = round(stejlest, 1)
    if stejlest > MAX_KM_GRADIENT:
        fejl.append(f"en kilometer på {stejlest:.0f} % — umuligt, ruten er gået galt et sted")

    checks["hoejdemeter_dem"] = round(sum(max(0.0, b - a) for a, b in zip(eles, eles[1:])))
    return {"ok": not fejl, "fejl": fejl, "checks": checks}


# ── GPX ud ───────────────────────────────────────────────────────────────────

def write_gpx(path: Path, spec, pts, eles, metode: str) -> None:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    desc = (f"Genereret af klassementet.dk gpx_builder ({metode}). "
            f"Kilde: {spec.get('source', 'ukendt')}, aflæst {spec.get('read_at', '?')}. "
            f"Rute: © OpenStreetMap-bidragydere (ODbL) via BRouter. "
            f"Højde: EU-DEM/SRTM via Open Topo Data.")
    name = f"{spec['race']} etape {spec['stage']}"
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="klassementet.dk gpx_builder" '
        'xmlns="http://www.topografix.com/GPX/1/1">',
        f"  <metadata><name>{escape(name)}</name><desc>{escape(desc)}</desc>"
        f"<time>{now}</time></metadata>",
        f"  <trk><name>{escape(name)}</name><trkseg>",
    ]
    lines += [f'    <trkpt lat="{la:.6f}" lon="{lo:.6f}"><ele>{e:.1f}</ele></trkpt>'
              for (la, lo), e in zip(pts, eles)]
    lines += ["  </trkseg></trk>", "</gpx>", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


# ── Hovedløb ─────────────────────────────────────────────────────────────────

def build(spec_path: Path, dry_run: bool = False) -> bool:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    race, stage = spec["race"], int(spec["stage"])
    print(f"\n=== {race} etape {stage} ({spec['official_km']} km)")
    wps = spec["waypoints"]

    if spec.get("method", "itinerary") == "itinerary":
        # 1. Geokodning — resultatet skrives tilbage i specen, så næste kørsel
        #    er deterministisk, og en forkert by kan rettes i hånden.
        aendret = False
        for wp in wps:
            if wp.get("lat") is None:
                hit = geocode(wp.get("q") or wp["name"])
                if not hit:
                    print(f"  ✗ kunne ikke geokode {wp.get('q') or wp['name']}")
                    return False
                wp["lat"], wp["lon"], wp["geo"] = hit[0], hit[1], "nominatim"
                aendret = True
        if aendret:
            spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")

        # Fugleflugt kan aldrig være længere end vejen. Er den det, er en by
        # geokodet til en navnebror et andet sted — stop, før ruteplanlæggeren
        # lægger en omvej, der ser plausibel ud.
        # Første strækning får slæk for den neutrale start (se trim_neutral_start).
        med_km = [w for w in wps if w.get("km") is not None]
        for n, (a, b) in enumerate(zip(med_km, med_km[1:])):
            luft = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
            slaek = NEUTRAL_MAX_KM if n == 0 else 3.0
            if luft > (b["km"] - a["km"]) + slaek:
                print(f"  ✗ {a['name']} → {b['name']}: {luft:.1f} km i fugleflugt, men kun "
                      f"{b['km'] - a['km']:.1f} km ad vejen — en af dem er geokodet forkert")
                return False

        # Strækning for strækning, så hver kan få sit eget alternativ. Den
        # første har ukendt længde (neutral start), så dér tages BRouters første.
        raw, idx, valg = [], [0], []
        for n, (a, b) in enumerate(zip(wps, wps[1:])):
            target = (b["km"] - a["km"]) if n > 0 and a.get("km") is not None \
                and b.get("km") is not None else None
            try:
                leg, _, _, alt = route_leg(a, b, target)
            except RuntimeError as e:
                print(f"  ✗ ingen rute: {e} — sæt lat/lon på vejen i specen")
                return False
            raw.extend(leg if not raw else leg[1:])
            idx.append(len(raw) - 1)
            valg.append(alt)
        if any(valg):
            print(f"  alternativer valgt pr. strækning: {valg}")
        raw, fjernet = trim_spurs(raw, idx[1:-1])
        if fjernet:
            print(f"  blindgyder fjernet: {fjernet} m")
        # Enkeltstarter har ingen neutral start: km 0 er startrampen.
        raw, neutral = trim_neutral_start(raw, wps) if spec.get("neutral_start", True) \
            else (raw, 0.0)
        if neutral:
            print(f"  neutral start klippet af: {neutral:.1f} km")
        metode = f"køreplan + BRouter/{BROUTER_PROFILE}"
    else:
        raw = load_track(spec["track"])
        fjernet, neutral = 0, 0.0
        metode = "arrangørens spor"

    pts = densify(raw, DENSIFY_M)
    print(f"  {len(pts)} punkter, henter højde …")
    eles = elevations(pts)

    wp_idx, start = [], 0
    for w in wps:
        if w.get("lat") is None:
            wp_idx.append(start)
            continue
        start = nearest_index(pts, w["lat"], w["lon"], start)
        wp_idx.append(start)

    rapport = validate(spec, pts, eles, wp_idx)
    rapport.update({"race": race, "stage": stage, "metode": metode,
                    "blindgyder_fjernet_m": fjernet, "neutral_start_km": round(neutral, 2),
                    "source": spec.get("source"),
                    "genereret": dt.datetime.now().isoformat(timespec="seconds")})

    c = rapport["checks"]
    print(f"  distance: {c['distance']['routed_km']} km ({c['distance']['afvigelse_pct']:+} %)")
    for r in c["byer"]:
        ele = f", højde {r['dem_ele']}/{r['official_ele']} m" if "dem_ele" in r else ""
        print(f"    {r['name']:<28} km {r['routed_km']:>6} / {r['official_km']:<6} "
              f"({r['afvigelse_km']:+.2f}, fra linjen {r['rest_km']:+.2f}){ele}")
    print(f"  højdekurve: {c['hoejdekurve']}")
    print(f"  stejleste km: {c['stejleste_km_pct']} %   højdemeter (DEM): {c['hoejdemeter_dem']}")

    if rapport["ok"] and not dry_run:
        ud = GPX_DIR / race / f"stage-{stage}.gpx"
        print(f"  ✓ BESTÅET → {ud}")
    elif rapport["ok"]:
        ud = KANDIDAT_DIR / race / f"stage-{stage}.gpx"
        print(f"  ✓ BESTÅET (dry-run) → {ud}")
    else:
        ud = KANDIDAT_DIR / race / f"stage-{stage}.gpx"
        print("  ✗ AFVIST — skrevet til review, ikke til pipelinen:")
        for f in rapport["fejl"]:
            print(f"    - {f}")
    write_gpx(ud, spec, pts, eles, metode)
    ud.with_suffix(".report.json").write_text(
        json.dumps(rapport, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rapport["ok"]


def main() -> None:
    p = argparse.ArgumentParser(description="Byg og kontrollér en GPX-rute fra officielle oplysninger")
    p.add_argument("--spec", help="sti til en stage-N.json")
    p.add_argument("--race")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--stage", type=int)
    g.add_argument("--all", action="store_true")
    p.add_argument("--dry-run", action="store_true",
                   help="skriv også en bestået rute til output/, ikke data/gpx/")
    a = p.parse_args()

    if a.spec:
        specs = [Path(a.spec)]
    elif a.race and a.stage:
        specs = [GPX_DIR / a.race / f"stage-{a.stage}.json"]
    elif a.race and a.all:
        specs = sorted((GPX_DIR / a.race).glob("stage-*.json"),
                       key=lambda s: int(s.stem.split("-")[1]))
    else:
        p.error("angiv --spec eller --race med --stage/--all")

    ok = sum(build(s, a.dry_run) for s in specs)
    print(f"\n{ok}/{len(specs)} etaper bestod")
    sys.exit(0 if ok == len(specs) else 1)


if __name__ == "__main__":
    main()
