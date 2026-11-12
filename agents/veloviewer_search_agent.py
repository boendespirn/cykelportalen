"""
veloviewer_search_agent.py — VeloViewer-segmenter fundet via websøgning.

Stravas segment-API er lukket (2026-10-10), så veloviewer_agent.py kan ikke
længere finde segmenter geografisk. Ejeren bad 2026-11-12 om at søge
"<stigningens navn> veloviewer" og bruge et match, hvis det passer.

Søgningen selv sker uden for scriptet (agentens websøgning); her kommer en
kandidatfil ind, og HVER kandidat kontrolleres mod vores egne tal fra
VeloViewers offentlige segmentside (distance, grade, elevationHigh/Low):

  - længde        ±8 % (min. 0,6 km)
  - hældning      ±0,8 procentpoint
  - tophøjde      ±60 m   (kildens trykte tophøjde)
  - fodhøjde      ±70 m   (tophøjde − højdegevinst) — det er den, der fanger
                            den FORKERTE SIDE af det rigtige bjerg, som fik
                            veloviewer_nogpx_agent.py spærret (4 af 5 forkerte).
  - navnet skal ligne stigningens navn.

Kun en kandidat, der består ALLE kontroller, skrives — og kun til
`stage_climbs.veloviewer_segment_id`, når feltet er tomt (eller --overwrite).

Kandidatfil (JSON): {"<stage_climbs.id>": [segment_id, ...], ...}

Kør:
  python agents/veloviewer_search_agent.py --kandidater fil.json [--write-db] [--overwrite]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

import requests
from dotenv import load_dotenv

if not isinstance(sys.stdout, io.TextIOWrapper) or (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"

LAENGDE_PCT, LAENGDE_MIN_KM = 8.0, 0.6
GRADIENT_PP = 0.8
TOP_M = 60
FOD_M = 70
NAVN_MIN = 0.45

_STOP = {"col", "du", "de", "la", "le", "les", "des", "passo", "del", "della", "di", "monte",
         "cote", "climb", "segment", "from", "via", "the", "salita", "san", "colle", "dei"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s)


def navn_ligner(climb: str, segment: str) -> float:
    """0..1: andelen af stigningsnavnets betydende ord, der står i segmentnavnet."""
    c, s = _norm(climb), _norm(segment)
    ord_c = [w for w in c.split() if w not in _STOP and len(w) > 2]
    if not ord_c:
        return SequenceMatcher(None, c, s).ratio()
    hits = sum(1 for w in ord_c
               if w in s or any(SequenceMatcher(None, w, t).ratio() > 0.85 for t in s.split()))
    return hits / len(ord_c)


def hent_segment(seg_id: int) -> dict | None:
    try:
        r = requests.get(f"https://veloviewer.com/segments/{seg_id}", headers={"User-Agent": UA}, timeout=30)
    except requests.RequestException:
        return None
    if not r.ok:
        return None
    h = r.text

    def num(key):
        m = re.search(rf'"{key}"\s*:\s*(-?[\d.]+)', h)
        return float(m.group(1)) if m else None

    titel = re.search(r"Segment Details for (.*?)</title>", h)
    d = {"id": seg_id, "navn": (titel.group(1).strip() if titel else ""),
         "distance_km": (num("distance") or 0) / 1000, "grade": num("grade"),
         "high": num("elevationHigh"), "low": num("elevationLow")}
    if not d["distance_km"] or d["grade"] is None or d["high"] is None or d["low"] is None:
        return None
    return d


def kontroller(climb: dict, seg: dict) -> tuple[bool, list[str]]:
    fejl = []
    L, G = float(climb["length_km"]), float(climb["avg_gradient"])
    if abs(seg["distance_km"] - L) > max(L * LAENGDE_PCT / 100, LAENGDE_MIN_KM):
        fejl.append(f"længde {seg['distance_km']:.2f}/{L}")
    if abs(seg["grade"] - G) > GRADIENT_PP:
        fejl.append(f"hældning {seg['grade']}/{G}")
    top = climb.get("top_hoejde_m")
    if top is None:
        fejl.append("ingen tophøjde at kontrollere mod")
    else:
        if abs(seg["high"] - top) > TOP_M:
            fejl.append(f"top {seg['high']:.0f}/{top}")
        fod = top - float(climb.get("elevation_m") or L * G * 10)
        if abs(seg["low"] - fod) > FOD_M:
            fejl.append(f"fod {seg['low']:.0f}/{fod:.0f}")
    # Virtuelle ruter (Zwift/RGT/Bkool/Tacx …) er ikke en optagelse af den
    # virkelige vej — de kan matche på tal og stadig være forkerte.
    if re.search(r"\b(rgt|zwift|watopia|bkool|tacx|rouvy|fulgaz|virtual)\b", seg["navn"], re.I):
        fejl.append("virtuelt segment")
    nl = navn_ligner(climb["name"], seg["navn"])
    if nl < NAVN_MIN:
        fejl.append(f"navn '{seg['navn']}' ({nl:.2f})")
    return not fejl, fejl


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kandidater", required=True)
    ap.add_argument("--write-db", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    kand: dict[str, list[int]] = json.loads(Path(a.kandidater).read_text(encoding="utf-8"))

    rapport = {"dato": date.today().isoformat(), "fundet": [], "ikke_fundet": []}
    cache: dict[int, dict | None] = {}
    for climb_id, segs in kand.items():
        rows = requests.get(
            f"{SUPABASE_URL}/rest/v1/stage_climbs?id=eq.{climb_id}"
            "&select=id,name,length_km,avg_gradient,elevation_m,top_hoejde_m,veloviewer_segment_id",
            headers=SB_HEADERS, timeout=30).json()
        if not rows:
            continue
        c = rows[0]
        if c.get("veloviewer_segment_id") and not a.overwrite:
            print(f"= {c['name']}: har allerede {c['veloviewer_segment_id']}")
            continue
        bedst = None
        afvist = []
        for sid in dict.fromkeys(segs):
            if sid not in cache:
                cache[sid] = hent_segment(sid)
                time.sleep(0.8)
            seg = cache[sid]
            if not seg:
                afvist.append(f"{sid}: kunne ikke læses")
                continue
            ok, fejl = kontroller(c, seg)
            if ok:
                score = (abs(seg["distance_km"] - c["length_km"]) / c["length_km"]
                         + abs(seg["grade"] - c["avg_gradient"]) / 5)
                if bedst is None or score < bedst[0]:
                    bedst = (score, seg)
            else:
                afvist.append(f"{sid} '{seg['navn']}': " + ", ".join(fejl))
        if bedst:
            seg = bedst[1]
            print(f"✓ {c['name']} → {seg['id']} '{seg['navn']}' ({seg['distance_km']:.2f} km, "
                  f"{seg['grade']}%, {seg['low']:.0f}→{seg['high']:.0f} m)")
            rapport["fundet"].append({"climb_id": climb_id, "navn": c["name"], "segment": seg})
            if a.write_db:
                requests.patch(f"{SUPABASE_URL}/rest/v1/stage_climbs?id=eq.{climb_id}",
                               json={"veloviewer_segment_id": seg["id"]}, headers=SB_HEADERS,
                               timeout=30).raise_for_status()
        else:
            print(f"✗ {c['name']}: intet segment bestod" + (f" — {afvist[0]}" if afvist else ""))
            rapport["ikke_fundet"].append({"climb_id": climb_id, "navn": c["name"], "afvist": afvist})

    ud = REPO_ROOT / "output" / "veloviewer_search" / f"{Path(a.kandidater).stem}-rapport.json"
    ud.parent.mkdir(parents=True, exist_ok=True)
    ud.write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nFundet: {len(rapport['fundet'])}, ikke fundet: {len(rapport['ikke_fundet'])}. Rapport: {ud}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
