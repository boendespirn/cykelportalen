"""
stage_profile_generator.py
Genererer klassementet.dk's egen FULDE etape-hoejdeprofil direkte fra raa
GPX-hoejdedata, som fallback naar PCS ikke leverer et hel-etape-profilbillede
(se STG-002 i state/issues.md — fx tour-de-france-2026 etape 3).

Genbruger byggeklodserne fra climb_profile_generator.py (samme GPX-kilde,
samme farveskala, samme sektions-/resampling-logik), men for HELE etapens
GPX-spor i stedet for et enkelt klatresegment. Overlejrer kendte kategoriserede
stigninger (fra stage_climbs) som markerede bånd med navn/gradient, ligesom en
rigtig PCS-etapeprofil.

GPX'ens egen kumulative distance matcher sjældent den officielle etapedistance
(bekræftet ~4-5% afvigelse på tour-de-france-2026 etape 3) — terrænet tegnes
derfor i GPX'ens egen km-skala, men akse-labels og klatremarkører regnes om
til officiel km via samme skalerings-tilgang som climb_profile_generator.py's
locate_climb_segment() bruger til enkelt-stigninger.

Skriver KUN til stages.elevation_image_url når feltet er NULL, medmindre
--overwrite angives eksplicit — rører aldrig et eksisterende (fx PCS-hentet)
billede uden det.

Kør (test — uploader kun til test/-sti, ingen DB-skrivning):
    python agents/stage_profile_generator.py --race tour-de-france-2026 --stage 3

Kør (produktion — skriver stages.elevation_image_url hvis NULL):
    python agents/stage_profile_generator.py --race tour-de-france-2026 --stage 3 --write-db
"""

import os
import io
import sys
import argparse
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from climb_profile_generator import (  # noqa: E402
    download_stage_gpx,
    cumulative_distances_km,
    resample_elevation_profile,
    gradient_to_color,
)
# Bemærk: climb_profile_generator.py wrapper allerede sys.stdout til UTF-8 ved
# import (samme mønster som alle andre agent-scripts) — wrapper det ikke igen
# her, da dobbelt-wrapping af samme underliggende buffer lukker strømmen
# (ValueError: I/O operation on closed file).
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SB_AUTH = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
SB_HEADERS = {**SB_AUTH, "Content-Type": "application/json", "Prefer": "return=minimal"}
BUCKET = "stage-profiles"


# ── Sektionsberegning (hele etapen, ikke kun én stigning) ────────────────────

def compute_stage_sections(resampled: list[tuple[float, float]], n_sections: int = 80) -> list[dict]:
    """Deler den resamplede fulde etapeprofil i n_sections lige lange sektioner."""
    from climb_profile_generator import _interp_at  # lille helper, ren funktion

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
            "start_km": start_km, "end_km": end_km,
            "start_elev": start_elev, "end_elev": end_elev,
            "avg_gradient": gradient,
        })
    return sections


# ── Rendering ─────────────────────────────────────────────────────────────────

WIDTH, HEIGHT = 3000, 1000
BG_COLOR = (15, 23, 42)
TEXT_COLOR = (226, 232, 240)
GRID_COLOR = (51, 65, 85)
LINE_COLOR = (241, 245, 249)
BRAND_COLOR = (100, 116, 139)
CLIMB_BAND_COLOR = (56, 189, 248)   # sky-400, halvgennemsigtig markering
CLIMB_LABEL_BG = (30, 41, 59)       # slate-800

PAD_LEFT, PAD_RIGHT, PAD_TOP, PAD_BOTTOM = 110, 60, 175, 90

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


def render_stage_profile(
    stage_label: str,
    sections: list[dict],
    climbs_gpx_km: list[dict],
    distance_km_official: float,
    km_scale: float,
) -> Image.Image:
    """
    sections: output fra compute_stage_sections() (rå GPX-km-skala).
    climbs_gpx_km: [{"name","start_km","end_km","avg_gradient"}] i GPX-km-skala.
    km_scale: gpx_total / distance_km_official (bruges til at vise officielle km-labels).
    """
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    inner_w = WIDTH - PAD_LEFT - PAD_RIGHT
    inner_h = HEIGHT - PAD_TOP - PAD_BOTTOM

    all_elevs = [s["start_elev"] for s in sections] + [sections[-1]["end_elev"]]
    min_elev, max_elev = min(all_elevs), max(all_elevs)
    elev_range = max(max_elev - min_elev, 1.0)
    min_elev_padded = max(0.0, min_elev - elev_range * 0.05)
    max_elev_padded = max_elev + elev_range * 0.12

    total_km = sections[-1]["end_km"]
    baseline_y = PAD_TOP + inner_h

    def to_xy(km: float, elev: float) -> tuple[float, float]:
        x = PAD_LEFT + (km / total_km) * inner_w
        y = PAD_TOP + inner_h - ((elev - min_elev_padded) / (max_elev_padded - min_elev_padded)) * inner_h
        return x, y

    # Terrænsektioner farvet efter hældning
    for s in sections:
        x0, y0 = to_xy(s["start_km"], s["start_elev"])
        x1, y1 = to_xy(s["end_km"], s["end_elev"])
        color = gradient_to_color(s["avg_gradient"])
        draw.polygon([(x0, baseline_y), (x0, y0), (x1, y1), (x1, baseline_y)], fill=color)

    outline_pts = [to_xy(s["start_km"], s["start_elev"]) for s in sections]
    outline_pts.append(to_xy(sections[-1]["end_km"], sections[-1]["end_elev"]))
    draw.line(outline_pts, fill=LINE_COLOR, width=3)

    # Højde-gitter + labels
    for i in range(5):
        elev = min_elev_padded + (max_elev_padded - min_elev_padded) * i / 4
        _, y = to_xy(0, elev)
        draw.line([(PAD_LEFT, y), (WIDTH - PAD_RIGHT, y)], fill=GRID_COLOR, width=1)
        draw.text((PAD_LEFT - 15, y), f"{int(round(elev))}m", font=_font(22),
                   fill=TEXT_COLOR, anchor="rm")

    # Km-akse (vist i officiel distance, ikke GPX-rå distance)
    step_official = max(5, round(distance_km_official / 12 / 5) * 5)
    km_marker_official = 0
    while km_marker_official <= distance_km_official + 1:
        gpx_km = km_marker_official * km_scale
        if gpx_km <= total_km:
            x, _ = to_xy(gpx_km, min_elev_padded)
            draw.line([(x, baseline_y), (x, baseline_y + 8)], fill=GRID_COLOR, width=1)
            draw.text((x, baseline_y + 15), f"{km_marker_official}", font=_font(20),
                       fill=TEXT_COLOR, anchor="ma")
        km_marker_official += step_official
    draw.text((WIDTH / 2, HEIGHT - 20), "km", font=_font(20), fill=BRAND_COLOR, anchor="ma")

    # Stigningsbånd + labels
    for c in climbs_gpx_km:
        x0, _ = to_xy(c["start_km"], min_elev_padded)
        x1, _ = to_xy(c["end_km"], min_elev_padded)
        x1 = max(x1, x0 + 2)
        # Halvgennemsigtig markering hen over selve klatren
        overlay = Image.new("RGBA", (int(x1 - x0), inner_h), (*CLIMB_BAND_COLOR, 55))
        img.paste(overlay, (int(x0), PAD_TOP), overlay)

        mid_x = (x0 + x1) / 2
        label = c["name"]
        sub = f"{c['length_km']:.1f} km @ {c['avg_gradient']:.1f}%"

        # Undgå at labels klippes af kanten eller overlapper titlen: klem
        # ankerpunktet ind fra begge sider og skift til venstre/højre-anker
        # tæt på kanterne i stedet for centreret.
        edge_margin = 220
        if mid_x < PAD_LEFT + edge_margin:
            label_x, anchor = PAD_LEFT + 4, "lb"
        elif mid_x > WIDTH - PAD_RIGHT - edge_margin:
            label_x, anchor = WIDTH - PAD_RIGHT - 4, "rb"
        else:
            label_x, anchor = mid_x, "mb"

        draw.text((label_x, PAD_TOP - 65), label, font=_font(24), fill=(255, 255, 255),
                   anchor=anchor, stroke_width=2, stroke_fill=(0, 0, 0))
        draw.text((label_x, PAD_TOP - 36), sub, font=_font(20), fill=(186, 230, 253),
                   anchor=anchor, stroke_width=2, stroke_fill=(0, 0, 0))
        draw.line([(mid_x, PAD_TOP - 20), (mid_x, PAD_TOP)], fill=(255, 255, 255), width=2)

    start_elev = sections[0]["start_elev"]
    finish_elev = sections[-1]["end_elev"]
    x0, y0 = to_xy(0, start_elev)
    draw.text((x0 + 10, y0 + 12), f"{int(round(start_elev))}m", font=_font(26),
               fill=TEXT_COLOR, anchor="la")
    x1, y1 = to_xy(total_km, finish_elev)
    draw.text((x1, y1 - 15), f"{int(round(finish_elev))}m", font=_font(26),
               fill=TEXT_COLOR, anchor="mb")

    draw.text((PAD_LEFT, 25), stage_label, font=_font(38), fill=TEXT_COLOR, anchor="lm")
    draw.text((PAD_LEFT, 60), f"{distance_km_official:.1f} km — klassementet.dk (genereret af GPX)",
               font=_font(24), fill=BRAND_COLOR, anchor="lm")
    draw.text((WIDTH - PAD_RIGHT, HEIGHT - 20), "klassementet.dk",
               font=_font(22), fill=BRAND_COLOR, anchor="rb")

    return img.convert("RGB")


# ── Supabase ──────────────────────────────────────────────────────────────────

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
        f"&select=id,stage_number,distance_km,elevation_image_url,start_location,finish_location&limit=1",
        headers=SB_AUTH,
    )
    data = res.json()
    return data[0] if res.ok and data else None


def get_climbs_for_stage(stage_id: str) -> list[dict]:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/stage_climbs"
        f"?stage_id=eq.{stage_id}"
        f"&select=name,km_from_start,length_km,avg_gradient"
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
        print(f"Upload fejl {res.status_code}: {res.text[:150]}")
        return None
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{path}"


def update_stage_image(stage_id: str, url: str) -> bool:
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/stages?id=eq.{stage_id}",
        json={"elevation_image_url": url},
        headers=SB_HEADERS,
    )
    return res.ok


# ── Hovedpipeline ─────────────────────────────────────────────────────────────

def process_stage(race_slug: str, stage_number: int, write_db: bool, overwrite: bool) -> None:
    race_id = get_race_id(race_slug)
    if not race_id:
        print(f"Løb ikke fundet: {race_slug}")
        return

    stage = get_stage(race_id, stage_number)
    if not stage or not stage.get("distance_km"):
        print(f"Etape {stage_number} ikke fundet eller mangler distance_km")
        return

    if write_db and stage.get("elevation_image_url") and not overwrite:
        print(f"Etape {stage_number} har allerede elevation_image_url — springer over (brug --overwrite)")
        return

    print(f"stage_profile_generator.py — {race_slug} etape {stage_number}")
    print("Henter GPX...")
    points = download_stage_gpx(race_slug, stage_number)
    if not points:
        print("Kunne ikke hente/parse GPX-fil for denne etape — ingen kilde tilgængelig")
        return

    cum_dist = cumulative_distances_km(points)
    gpx_total = cum_dist[-1]
    distance_km_official = float(stage["distance_km"])
    km_scale = gpx_total / distance_km_official
    print(f"GPX: {len(points)} punkter, {gpx_total:.1f} km (officiel distance: {distance_km_official} km, "
          f"skalafaktor {km_scale:.3f})")

    resampled = resample_elevation_profile(points, n=400)
    sections = compute_stage_sections(resampled, n_sections=90)

    climbs = get_climbs_for_stage(stage["id"])
    climbs_gpx_km = []
    for c in climbs:
        if c.get("km_from_start") is None or not c.get("length_km"):
            continue
        start_km = float(c["km_from_start"]) * km_scale
        end_km = start_km + float(c["length_km"]) * km_scale
        climbs_gpx_km.append({
            "name": c["name"],
            "start_km": start_km,
            "end_km": end_km,
            "length_km": float(c["length_km"]),
            "avg_gradient": float(c.get("avg_gradient") or 0.0),
        })

    start_loc = stage.get("start_location") or ""
    finish_loc = stage.get("finish_location") or ""
    stage_label = f"Etape {stage_number}" + (f" — {start_loc} → {finish_loc}" if start_loc and finish_loc else "")

    img = render_stage_profile(stage_label, sections, climbs_gpx_km, distance_km_official, km_scale)
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    path = f"stage-full/{stage['id']}.png" if write_db else f"test/stage-{stage['id']}.png"
    url = upload_image(path, buf.getvalue())
    if not url:
        print("Upload fejlede")
        return

    if write_db:
        if update_stage_image(stage["id"], url):
            print(f"✓ Opdateret i DB: {url}")
        else:
            print("✗ DB-opdatering fejlede")
    else:
        print(f"✓ Genereret (test, ingen DB-skrivning): {url}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--race", required=True, help="Løb-slug, fx tour-de-france-2026")
    parser.add_argument("--stage", type=int, required=True, help="Etapenummer")
    parser.add_argument("--write-db", action="store_true",
                         help="Upload til stage-full/ og patch stages.elevation_image_url (default: kun test/-upload)")
    parser.add_argument("--overwrite", action="store_true",
                         help="Ved --write-db: overskriv etaper der allerede har et elevation_image_url")
    args = parser.parse_args()

    process_stage(args.race, args.stage, args.write_db, args.overwrite)
