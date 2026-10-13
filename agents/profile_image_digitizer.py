"""
profile_image_digitizer.py
Udtraekker hoejdekurven (km -> meter) fra et OFFICIELT etapeprofilbillede, saa
stage_profile_generator.py kan tegne vores eget design for loeb uden GPX-kilde.

Baggrund: baade climb_profile_generator.py og stage_profile_generator.py henter
hoejdedata fra cyclingstage.com's GPX-filer. Ni WorldTour-loeb findes ikke der
(DATA-003), og for Tour de Pologne har PCS heller ingen GPX eller
rutekoordinater — verificeret raat 2026-08-02. Uden en hoejdekilde kan de loeb
slet ikke faa en hel-etape-hoejdeprofil, fordi PCS' egne billeder er skjult i
frontenden siden LEG-001.

Hvad vi udtraekker er FAKTA (terraenets hoejde langs en offentlig vej), ikke
arrangoerens billede — samme skelnen som aso_roadbook_agent.py bygger paa, og
billedet selv bliver aldrig vist. Ejeren godkendte fremgangsmaaden 2026-08-02.

Metode:
  1. Find plotfeltet ud fra det farvede fyld under kurven.
  2. Spor fyldets overkant NEDEFRA og op, saa labellernes lodrette hjaelpelinjer
     og de stiplede gitterlinjer ikke forveksles med terraenet.
  3. Kalibrer pixel -> meter med mindste kvadraters ret linje paa de INDRE
     officielle ankre (km, hoejde) fra profile_image_anchors.json.
  4. Snap toppunkter til lokalt maksimum, saa en lille km-forskydning ikke
     rammer flanken i stedet for toppen.
  5. Saet start-/slutvaerdien til den officielle hoejde — kurven er klippet af
     plotrammen i de yderste pixels og kan ikke aflaeses paalideligt der.
  6. VALIDÉR mod samtlige ankre. Overskrides max_deviation_m, returneres intet,
     saa en gaettet kurve aldrig kan publiceres (CLAUDE.md §6).

Kør:
  python profile_image_digitizer.py --race tour-de-pologne-2026 --all
  python profile_image_digitizer.py --race tour-de-pologne-2026 --stage 6
"""

import argparse
import io
import json
import sys
from pathlib import Path

import requests
from PIL import Image

# Wrap kun hvis stdout ikke ALLEREDE er UTF-8. climb_profile_generator.py
# wrapper selv ved import, og en dobbelt-wrapping lukker den underliggende
# stroem ("I/O operation on closed file") naar dette modul importeres derfra.
if (getattr(sys.stdout, "encoding", "") or "").lower().replace("-", "") != "utf8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ANCHOR_FILE = Path(__file__).with_name("profile_image_anchors.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126 Safari/537.36")

PLOT_BG = (241, 241, 243)     # graat plotfelt i arrangoerens profilbilleder
TOL_BG = 6


# ── pixel-hjaelpere ───────────────────────────────────────────────────────────

def _is_bg(px) -> bool:
    return all(abs(a - b) <= TOL_BG for a, b in zip(px, PLOT_BG))


def _is_fill(px) -> bool:
    """Det gule/gyldne fyld under kurven."""
    r, g, b = px
    return r > 170 and g > 140 and b < 130 and (r - b) > 70


def _find_plot_box(im: Image.Image) -> tuple[int, int, int, int] | None:
    """x-udstraekning og bundlinje fra fyldet, som altid daekker hele kurvens
    bredde. Toppen saettes til 0 — sporingen gaar alligevel nedefra og op."""
    w, h = im.size
    x0, x1, y1 = w, 0, 0
    for y in range(h):
        for x in range(w):
            if _is_fill(im.getpixel((x, y))):
                if x < x0:
                    x0 = x
                if x > x1:
                    x1 = x
                if y > y1:
                    y1 = y
    if x1 <= x0:
        return None
    return x0, 0, x1, y1


def _trace_surface(im: Image.Image, box) -> dict[int, int]:
    """Terraenets overkant pr. kolonne. Fyldet er sammenhaengende fra bundlinjen
    op til overfladen; hjaelpelinjer og gitterlinjer er aldrig fyldfarvede."""
    x0, _y0, x1, y1 = box
    surface: dict[int, int] = {}
    for x in range(x0, x1 + 1):
        y = y1
        while y > 0 and not _is_fill(im.getpixel((x, y))):
            y -= 1
        if y <= 0:
            continue
        gap = 0
        while y > 0:
            if _is_fill(im.getpixel((x, y))):
                gap = 0
            else:
                gap += 1
                if gap > 2:          # taal tynde gitterlinjer henover fyldet
                    break
            y -= 1
        surface[x] = y + gap + 1
    return _despike(surface)


# Et vejprofil kan ikke aendre sig hundredvis af meter paa én pixelkolonne
# (~0,1 km). Arrangoerens profilbilleder har markoerer og lodrette
# hjaelpelinjer, der stedvis overlapper fyldet og giver isolerede naale paa
# +/-200-460 m. De fjernes ved at sammenligne hver kolonne med den lokale
# median og interpolere hen over de afvigende. Selv den stejleste stigning i
# feltet flytter under 5 px pr. kolonne, saa 10 px-graensen rammer kun
# artefakter — aldrig aegte terraen.
DESPIKE_WINDOW = 5
DESPIKE_MAX_PX = 10


def _despike(surface: dict[int, int]) -> dict[int, int]:
    if not surface:
        return surface
    xs = sorted(surface)
    good: dict[int, int] = {}
    bad: list[int] = []
    for i, x in enumerate(xs):
        lo = max(0, i - DESPIKE_WINDOW)
        hi = min(len(xs), i + DESPIKE_WINDOW + 1)
        window = sorted(surface[xs[j]] for j in range(lo, hi))
        median = window[len(window) // 2]
        if abs(surface[x] - median) > DESPIKE_MAX_PX:
            bad.append(x)
        else:
            good[x] = surface[x]
    if not good:
        return surface
    good_xs = sorted(good)
    for x in bad:
        left = [gx for gx in good_xs if gx < x]
        right = [gx for gx in good_xs if gx > x]
        if left and right:
            a, b = left[-1], right[0]
            t = (x - a) / (b - a)
            surface[x] = round(good[a] + (good[b] - good[a]) * t)
        elif left:
            surface[x] = good[left[-1]]
        elif right:
            surface[x] = good[right[0]]
    return surface


# ── digitalisering ────────────────────────────────────────────────────────────

def _interp(points: list[tuple[float, float]], x: float) -> float:
    """Lineaer interpolation i en stigende (x, y)-liste, fladt uden for enderne."""
    if not points:
        return 0.0
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for i in range(1, len(points)):
        x1, y1 = points[i]
        if x1 >= x:
            x0, y0 = points[i - 1]
            t = 0.0 if x1 == x0 else (x - x0) / (x1 - x0)
            return y0 + (y1 - y0) * t
    return points[-1][1]


def load_config(race_slug: str) -> dict | None:
    data = json.loads(ANCHOR_FILE.read_text(encoding="utf-8"))
    return data.get(race_slug)


def _fetch_image(url: str) -> Image.Image:
    res = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    res.raise_for_status()
    return Image.open(io.BytesIO(res.content)).convert("RGB")


def digitize_stage_profile(
    race_slug: str,
    stage_number: int,
    n_samples: int = 1200,
    verbose: bool = True,
):
    """Returnerer ([(km, hoejde_m)], rapport) eller (None, rapport) hvis
    valideringen ikke holder."""
    cfg = load_config(race_slug)
    report: dict = {"race": race_slug, "stage": stage_number}
    if not cfg:
        report["error"] = "ingen ankerkonfiguration for løbet"
        return None, report

    st = cfg.get("stages", {}).get(str(stage_number))
    if not st:
        report["error"] = f"ingen ankre for etape {stage_number}"
        return None, report

    if cfg.get("style") == "edgecycling":
        return _digitize_edgecycling(cfg, st, report, n_samples, verbose)

    url = cfg["source_url_pattern"].format(stage=stage_number)
    report["source_url"] = url
    im = _fetch_image(url)

    box = _find_plot_box(im)
    if not box:
        report["error"] = "plotfelt ikke fundet i billedet"
        return None, report
    x0, _, x1, _y1 = box
    surface = _trace_surface(im, box)
    span = x1 - x0
    if len(surface) < span * 0.9:
        report["error"] = f"kun {len(surface)} af {span} kolonner kunne spores"
        return None, report

    total_km = float(st["total_km"])
    summits = {round(float(k), 1) for k in st.get("summit_anchors", [])}

    def km_to_px(km: float) -> float:
        return x0 + (km / total_km) * span

    def py_at_km(km: float, snap: bool):
        px = int(round(km_to_px(km)))
        if snap:
            win = max(6, int(0.015 * span))
            cand = [surface[c] for c in range(px - win, px + win + 1) if c in surface]
            return min(cand) if cand else None
        for d in range(8):
            for c in (px - d, px + d):
                if c in surface:
                    return surface[c]
        return None

    # Kalibrér kun paa INDRE ankre: kurven er klippet af plotrammen i de yderste
    # pixels, og et kantanker traekker hele skalaen skaevt.
    inner = [(float(km), float(m)) for km, m in st["anchors"]
             if 0.02 * total_km < float(km) < 0.98 * total_km]
    pts = []
    for km, m in inner:
        py = py_at_km(km, snap=round(km, 1) in summits)
        if py is not None:
            pts.append((py, m))
    if len(pts) < 2:
        report["error"] = "for få brugbare kalibreringsankre"
        return None, report

    n = len(pts)
    sx = sum(p for p, _ in pts)
    sy = sum(m for _, m in pts)
    sxx = sum(p * p for p, _ in pts)
    sxy = sum(p * m for p, m in pts)
    den = n * sxx - sx * sx
    if den == 0:
        report["error"] = "degenereret kalibrering (alle ankre på samme pixelrække)"
        return None, report
    scale = (n * sxy - sx * sy) / den
    offset = (sy - scale * sx) / n
    report["m_per_px"] = abs(scale)
    report["n_calibration_anchors"] = n

    def to_m(py: int) -> float:
        return scale * py + offset

    # Validering mod SAMTLIGE officielle ankre
    deviations = []
    for km, m in ((float(a), float(b)) for a, b in st["anchors"]):
        py = py_at_km(km, snap=round(km, 1) in summits)
        if py is None:
            continue
        deviations.append((km, m, to_m(py), to_m(py) - m))
    report["deviations"] = deviations
    max_dev = max((abs(d) for *_, d in deviations), default=0.0)
    report["max_deviation_m"] = max_dev
    report["mean_deviation_m"] = (
        sum(abs(d) for *_, d in deviations) / len(deviations) if deviations else 0.0
    )

    limit = float(cfg.get("max_deviation_m", 60))
    if max_dev > limit:
        report["error"] = (f"max afvigelse {max_dev:.0f} m overskrider grænsen "
                           f"{limit:.0f} m — kurven kan ikke verificeres")
        if verbose:
            _print_report(report)
        return None, report

    # Saml kurven
    resampled: list[tuple[float, float]] = []
    for i in range(n_samples):
        km = total_km * i / (n_samples - 1)
        py = py_at_km(km, snap=False)
        if py is None:
            continue
        resampled.append((km, to_m(py)))
    if len(resampled) < n_samples * 0.9:
        report["error"] = "for få punkter kunne udtrækkes"
        return None, report

    # Stykvis residual-korrektion mod de officielle hoejder ("rubber sheeting").
    # Den lineaere kalibrering rammer i gennemsnit godt, men afviger stedvis
    # (Slodyczki laa 57 m under officiel tophoejde og blev vist saadan paa
    # etapesiden). Her tvinges kurven til at gaa PRAECIS gennem hvert officielt
    # anker, og residualet interpoleres jaevnt derimellem. Det retter samtidig
    # yderpunkterne, hvor kurven er klippet af plotrammen.
    # Kvalitetsmaalet i rapporten er bevidst residualet FOER korrektionen —
    # ellers ville valideringen maale sig selv.
    fix_pts: list[tuple[float, float]] = [(0.0, float(st["start_m"]) - _interp(resampled, 0.0))]
    for km, m in ((float(a), float(b)) for a, b in st["anchors"]):
        py = py_at_km(km, snap=round(km, 1) in summits)
        if py is not None:
            fix_pts.append((km, m - to_m(py)))
    fix_pts.append((total_km, float(st["finish_m"]) - _interp(resampled, total_km)))
    fix_pts.sort(key=lambda p: p[0])

    resampled = [(km, m + _interp(fix_pts, km)) for km, m in resampled]

    report["points"] = len(resampled)
    report["anchor_corrected"] = len(fix_pts)
    if verbose:
        _print_report(report)
    return resampled, report


def _print_report(r: dict) -> None:
    print(f"\n=== etape {r['stage']} — {r.get('source_url', '')}")
    if "m_per_px" in r:
        print(f"    kalibreret på {r['n_calibration_anchors']} indre ankre "
              f"({r['m_per_px']:.3f} m/px)")
    for km, off, est, dev in r.get("deviations", []):
        print(f"    km {km:>6.1f}: officiel {off:>5.0f} m | aflæst {est:>6.0f} m "
              f"| afvig {dev:+5.0f} m")
    if "max_deviation_m" in r:
        print(f"    -> max {r['max_deviation_m']:.0f} m, "
              f"gennemsnit {r['mean_deviation_m']:.0f} m")
    if r.get("error"):
        print(f"    ✗ {r['error']}")
    elif "points" in r:
        print(f"    ✓ {r['points']} punkter udtrukket")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--race", required=True)
    ap.add_argument("--stage", type=int)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    cfg = load_config(args.race)
    if not cfg:
        print(f"Ingen ankerkonfiguration for {args.race}")
        return
    stages = ([args.stage] if args.stage
              else sorted(int(s) for s in cfg["stages"]) if args.all else [])
    if not stages:
        print("Angiv --stage N eller --all")
        return

    ok = 0
    for n in stages:
        pts, _ = digitize_stage_profile(args.race, n)
        if pts:
            ok += 1
    print(f"\nFærdig: {ok}/{len(stages)} etaper verificeret")


if __name__ == "__main__":
    main()


# ── stil: "edgecycling" (Tour of Guangxi m.fl.) ───────────────────────────────
# Arrangoerens profilbillede er RODT fyld paa HVID bund med en rigtig, lineaer
# y-akse. Det giver en mere direkte kalibrering end Pologne-stilens spredte
# ankre: vi laeser aksen i stedet for at udlede den. Tre ting er ikke-aabenlyse
# og kostede hver en fejlaflaesning, foer de blev haandteret:
#
#  1. Den NEDERSTE y-tick er komprimeret paa alle etaper ("0 M" ligger kun ét
#     interval under naeste vaerdi, selv om der er 100-200 m imellem). Tages den
#     med i kalibreringen, skraenes hele skalaen. Den droppes automatisk.
#  2. km 0 ligger IKKE ved plotfeltets venstrekant. Der tegnes 1,8-7,1 km
#     neutral start foer km 0 — bekraeftet mod 2024-GPX'ens 6,2 km neutralzone
#     paa etape 6. Derfor kalibreres x paa markoerlinjerne, ikke paa fyldet.
#  3. I de yderste kolonner mangler bundslaben, og sporingen vandrer da helt op
#     og rammer maalflagets ikon (806 m i stedet for 574 m). Derfor kraeves det,
#     at fyldet haenger sammen med bundlinjen.


def _edge_is_fill(px) -> bool:
    """Roedt fyld i alle nuancer: hovedfyld, fremhaevede klatrebaand og det
    blege pre-start-felt. Ikonerne er gule/blaa og fanges ikke."""
    r, g, b = px
    return r > 80 and r - g > 45 and r - b > 45 and abs(g - b) < 50


def _edge_is_dark(px) -> bool:
    r, g, b = px
    return r < 110 and g < 95 and b < 95


def _lsq(pts):
    n = len(pts)
    sx = sum(a for a, _ in pts)
    sy = sum(b for _, b in pts)
    sxx = sum(a * a for a, _ in pts)
    sxy = sum(a * b for a, b in pts)
    den = n * sxx - sx * sx
    if den == 0:
        raise ValueError("degenereret kalibrering")
    m = (n * sxy - sx * sy) / den
    return m, (sy - m * sx) / n


def _edge_y_calibration(y_ticks):
    """Mindste kvadrater paa aksens egne ticks, efter at den komprimerede
    bundtick er droppet."""
    t = [(float(y), float(m)) for y, m in y_ticks]
    if len(t) >= 4:
        sp = [(t[i + 1][0] - t[i][0]) / (t[i][1] - t[i + 1][1]) for i in range(len(t) - 1)]
        avg = sum(sp[:-1]) / len(sp[:-1])
        if abs(sp[-1] - avg) > 0.25 * avg:
            t = t[:-1]
    a, b = _lsq(t)
    return a, b, t


def _edge_x_calibration(im, px, base, x_labels, total_km):
    """Genfinder markoerlinjerne og fitter km -> pixel. Maalflaget taelles med
    paa nogle etaper og ikke paa andre, saa flere pakninger proeves, og den med
    mindst residual vinder."""
    w, h = im.size
    axis = min(x for x in range(60, 400)
               if sum(1 for y in range(150, base) if _edge_is_dark(px[x, y])) > (base - 150) * 0.6)
    right = max(x for x in range(axis, w)
                for y in range(150, base) if _edge_is_fill(px[x, y]))
    prof = {x: sum(1 for y in range(150, base) if _edge_is_dark(px[x, y]))
            for x in range(axis + 3, right - 2)}
    if not prof:
        return None
    mx = max(prof.values())
    labsets = [list(x_labels), list(x_labels) + [total_km],
               [0.0] + list(x_labels), [0.0] + list(x_labels) + [total_km]]
    best = None
    for thr in (0.5, 0.45, 0.4, 0.35, 0.3, 0.25, 0.2, 0.15, 0.12, 0.10):
        cols = sorted(x for x, c in prof.items() if c > mx * thr)
        groups, cur = [], []
        for x in cols:
            if cur and x - cur[-1] > 6:
                groups.append(cur)
                cur = []
            cur.append(x)
        if cur:
            groups.append(cur)
        cen = [sum(g) / len(g) for g in groups]
        for labs in labsets:
            if len(cen) != len(labs):
                continue
            try:
                a, b = _lsq(list(zip(labs, cen)))
            except ValueError:
                continue
            if a <= 0:
                continue
            res = max(abs(c - (a * k + b)) for k, c in zip(labs, cen))
            if best is None or res < best[0]:
                best = (res, a, b, len(cen))
    return best


def _edge_despike(d, win=9, max_jump=8.0):
    xs = sorted(d)
    out = dict(d)
    for i, x in enumerate(xs):
        lo = max(0, i - win // 2)
        hi = min(len(xs), i + win // 2 + 1)
        med = sorted(d[xs[j]] for j in range(lo, hi))[(hi - lo) // 2]
        if abs(d[x] - med) > max_jump:
            out[x] = med
    return out


def _digitize_edgecycling(cfg, st, report, n_samples, verbose):
    total_km = float(st["total_km"])
    url = st["source_url"]
    report["source_url"] = url
    im = _fetch_image(url)
    px = im.load()
    w, h = im.size

    base = max(y for y in range(150, h)
               if sum(1 for x in range(200, w - 50) if _edge_is_fill(px[x, y])) > w * 0.5)
    ay, by, used = _edge_y_calibration(st["y_ticks"])
    report["m_per_px"] = abs(ay)
    report["n_calibration_anchors"] = len(used)

    xcal = _edge_x_calibration(im, px, base, st["x_labels"], total_km)
    if not xcal:
        report["error"] = "x-aksens markoerlinjer kunne ikke genfindes"
        if verbose:
            _print_report(report)
        return None, report
    res_px, a, b, n_markers = xcal
    report["x_residual_px"] = res_px
    report["x_residual_km"] = res_px / a
    if res_px / a > 1.5:
        report["error"] = (f"km-kalibreringen afviger {res_px / a:.2f} km — "
                           "markoerlinjer og km-etiketter passer ikke sammen")
        if verbose:
            _print_report(report)
        return None, report

    # Terraenet kan ikke ligge over oeverste tick + ét interval.
    y_top = min(y for y, _ in used) - abs(used[0][0] - used[1][0])
    surface = {}
    x0, x1 = int(round(b)), int(round(a * total_km + b))
    for x in range(max(x0, 0), min(x1, w - 1) + 1):
        if not any(_edge_is_fill(px[x, y]) for y in range(base - 4, base)):
            continue                                  # fyldet skal naa bundlinjen
        y, gap = base - 1, 0
        while y > y_top:
            if _edge_is_fill(px[x, y]):
                gap = 0
            else:
                gap += 1
                if gap > 2:
                    break
            y -= 1
        top = y + gap + 1
        if top >= base - 2 or top <= y_top + 1:
            continue
        surface[x] = top
    span = x1 - x0 + 1
    if len(surface) < span * 0.9:
        report["error"] = f"kun {len(surface)} af {span} kolonner kunne spores"
        if verbose:
            _print_report(report)
        return None, report

    elev = _edge_despike({x: ay * y + by for x, y in surface.items()})
    xs = sorted(elev)
    resampled = []
    for i in range(n_samples):
        km = total_km * i / (n_samples - 1)
        xq = a * km + b
        if xq <= xs[0]:
            resampled.append((km, elev[xs[0]]))
            continue
        if xq >= xs[-1]:
            resampled.append((km, elev[xs[-1]]))
            continue
        j = 0
        while j < len(xs) - 1 and xs[j + 1] < xq:
            j += 1
        p, q = xs[j], xs[j + 1]
        f = 0.0 if q == p else (xq - p) / (q - p)
        resampled.append((km, elev[p] + (elev[q] - elev[p]) * f))

    # Validering 1: samlet hoejdemeter mod arrangoerens eget tal. Et billede paa
    # ~13 px/km kan ikke oploese alle smaaboelger, saa vores sum ligger
    # systematisk UNDER det officielle (maalt -12% til -34%). Baandet fanger
    # derfor grove skalafejl, ikke den forventede underregning.
    gain = sum(max(0.0, resampled[i][1] - resampled[i - 1][1])
               for i in range(1, len(resampled)))
    official = float(st.get("official_gain_m") or 0)
    report["gain_m"] = gain
    report["official_gain_m"] = official
    if official:
        rel = (gain - official) / official
        report["gain_rel"] = rel
        if not (-0.50 <= rel <= 0.30):
            report["error"] = (f"hoejdemeter {gain:.0f} afviger {rel * 100:+.0f}% fra "
                               f"officielle {official:.0f} — kurven kan ikke verificeres")
            if verbose:
                _print_report(report)
            return None, report

    # Validering 2: hver kendt stigning skal kunne genfindes i kurven med
    # nogenlunde den hoejdegevinst, arrangoeren selv angiver.
    devs = []
    for c in st.get("climbs", []):
        summit = float(c["summit_km"])
        length = float(c["length_km"])
        want = length * float(c["avg_gradient"]) * 10.0
        got = _interp(resampled, summit) - _interp(resampled, max(0.0, summit - length))
        devs.append((summit, want, got, got - want))
    report["climb_checks"] = devs
    if devs:
        worst = max(abs(d) for *_, d in devs)
        report["max_climb_deviation_m"] = worst
        if worst > 120:
            report["error"] = (f"stigningsgevinst afviger op til {worst:.0f} m fra "
                               "arrangoerens egne tal")
            if verbose:
                _print_report(report)
            return None, report

    report["points"] = len(resampled)
    report["max_deviation_m"] = report.get("max_climb_deviation_m", 0.0)
    report["mean_deviation_m"] = (sum(abs(d) for *_, d in devs) / len(devs)) if devs else 0.0
    if verbose:
        print(f"\n=== etape {report['stage']} — {url}")
        print(f"    y-akse: {len(used)} ticks ({abs(ay):.3f} m/px); "
              f"x-akse: {n_markers} markoerer, residual {res_px / a:.2f} km")
        if official:
            print(f"    hoejdemeter {gain:.0f} m mod officielle {official:.0f} m "
                  f"({(gain - official) / official * 100:+.0f}%)")
        for summit, want, got, d in devs:
            print(f"    stigning km {summit:>6.1f}: officiel gevinst {want:>4.0f} m | "
                  f"aflaest {got:>4.0f} m | afvig {d:+4.0f} m")
        print(f"    OK {len(resampled)} punkter udtrukket")
    return resampled, report
