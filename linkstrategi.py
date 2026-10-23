"""
linkstrategi.py
Den ejer-godkendte interne linkstrategi (2026-10-23): hvor mange nyheder pr.
uge der må bære interne links, og hvilke landingssider linkene skal gå til.

Bruges af ai_news_processor.py. Ændres strategien, ændres den HER — og i
STRATEGI.md §2a, som er den menneskelæselige udgave.

Begreber:
  spand     — en gruppe linkmål med en andel af ugens links (cross, giro, tour,
              vuelta, forside, naer).
  ankertype — hvordan ankerteksten formuleres; fordelingen holdes pr. linkmål.

En spand uden en eksisterende side tæller ikke: Giro- og Tour-linkene venter,
til 2027-siderne er oprettet, og deres andel går imens til de andre spande.
Vi linker aldrig en 2027-nyhed til en 2026-side.
"""

from datetime import date, timedelta

GRAND_TOURS = {
    "giro":   "giro-d-italia",
    "tour":   "tour-de-france",
    "vuelta": "la-vuelta-ciclista-a-espana",
}

# (fra, til inkl., link-artikler pr. uge, andele). None = dynamisk (maj-sep).
PERIODER = [
    # Ejerens tilføjelse: to måneder med intensiv cykelcross.
    (date(2026, 10, 23), date(2026, 12, 31), 3,
     {"cross": 0.5, "giro": 0.2, "forside": 0.2, "tour": 0.1}),
    (date(2027, 1, 1),   date(2027, 1, 31),  3,
     {"tour": 0.4, "giro": 0.3, "forside": 0.2, "vuelta": 0.1}),
    # Giroen går aggressivt; "naer" er forsiden plus løb tæt på (Paris-Nice,
    # klassikerne, Tour Auvergne-Rhône-Alpes osv.).
    (date(2027, 2, 1),   date(2027, 4, 30),  4,
     {"giro": 0.5, "tour": 0.3, "naer": 0.2}),
    (date(2027, 5, 1),   date(2027, 9, 30),  5, None),
]
STANDARD = (3, {"forside": 0.5, "naer": 0.5})   # uden for perioderne

ANKER_FORDELING = {"navn_aar": 0.4, "delvis": 0.3, "beskrivende": 0.2, "eksakt": 0.1}
ANKER_FORKLARING = {
    "navn_aar":    'løbets navn med årstal, fx "{navn} {aar}"',
    "delvis":      'en naturlig omskrivning med løbets navn, fx "ruten til {navn} {aar}" eller "etaperne i {navn}"',
    "beskrivende": 'beskrivende tekst om det, siden viser, fx "stigningsprofilerne" eller "startlisten"',
    "eksakt":      'det præcise søgeord "{navn} {aar} etaper" (for et endagsløb: "{navn} startliste")',
}
NAER_DAGE  = 42   # "tæt på" = starter inden for 6 uger
CROSS_DAGE = 21   # et crossløb kan linkes fra 3 uger før til 2 dage efter


def periode(d: date) -> tuple[int, dict]:
    """(link-artikler pr. uge, andele pr. spand) for dagen d."""
    for fra, til, pr_uge, andele in PERIODER:
        if fra <= d <= til:
            return pr_uge, andele if andele is not None else _dynamiske_andele(d)
    return STANDARD


def periode_fra(d: date) -> date:
    """Startdatoen for den periode, andelene tælles i. Maj-sep og tiden uden
    for perioderne skifter fokus løbende, så dér tæller de sidste 28 dage."""
    for fra, til, _, andele in PERIODER:
        if fra <= d <= til and andele is not None:
            return fra
    return d - timedelta(days=28)


def _dynamiske_andele(d: date) -> dict:
    """Maj-sep: den Grand Tour, der kører eller er i sine sidste 6 uger, får
    halvdelen; den næste efter den 30 %; forsiden og nære løb 20 %."""
    # Omtrentlige vinduer — bruges kun til at fordele andele, aldrig som data.
    vinduer = [("giro", date(d.year, 5, 1), date(d.year, 6, 1)),
               ("tour", date(d.year, 7, 1), date(d.year, 7, 27)),
               ("vuelta", date(d.year, 8, 20), date(d.year, 9, 14))]
    kommende = [(n, s) for n, s, e in vinduer if e >= d]
    if not kommende:
        return {"naer": 1.0}
    if kommende[0][1] - timedelta(days=NAER_DAGE) > d:
        return {kommende[0][0]: 0.5, "naer": 0.5}
    andele = {kommende[0][0]: 0.5, "naer": 0.2}
    if len(kommende) > 1:
        andele[kommende[1][0]] = 0.3
    else:
        andele["naer"] = 0.5
    return andele


def spand_for(sti: str, races_by_slug: dict) -> str | None:
    """Hvilken spand et internt link tilhører. Etapesider tæller som løbet."""
    if sti == "/":
        return "forside"
    slug = sti.strip("/").split("/")[0]
    for spand, base in GRAND_TOURS.items():
        if slug.startswith(base + "-"):
            return spand
    race = races_by_slug.get(slug)
    if race and race.get("race_type") == "cyclocross":
        return "cross"
    return "naer" if race else None


def linkmaal(d: date, races: list[dict]) -> dict[str, list[dict]]:
    """Mulige linkmål pr. spand i dag. races skal have slug, name, race_type,
    start_date og end_date. En Grand Tour er kun et mål, når en KOMMENDE
    udgave findes som side."""
    forside = {"sti": "/", "navn": "Klassementet", "aar": None}
    maal: dict[str, list[dict]] = {"forside": [forside]}
    for spand, base in GRAND_TOURS.items():
        udgaver = sorted((r for r in races if r["slug"].startswith(base + "-")
                          and r.get("start_date") and date.fromisoformat(r["start_date"]) > d),
                         key=lambda r: r["start_date"])
        if udgaver:
            r = udgaver[0]
            maal[spand] = [{"sti": f"/{r['slug']}", "navn": r["name"], "aar": r["start_date"][:4]}]
    cross, naer = [], []
    for r in races:
        if not r.get("start_date") or any(r["slug"].startswith(b + "-") for b in GRAND_TOURS.values()):
            continue
        start = date.fromisoformat(r["start_date"])
        slut = date.fromisoformat(r.get("end_date") or r["start_date"])
        m = {"sti": f"/{r['slug']}", "navn": r["name"], "aar": r["start_date"][:4]}
        if r.get("race_type") == "cyclocross":
            if slut >= d - timedelta(days=2) and start <= d + timedelta(days=CROSS_DAGE):
                cross.append(m)
        elif slut >= d and start <= d + timedelta(days=NAER_DAGE):
            naer.append(m)
    if cross:
        maal["cross"] = cross
    maal["naer"] = [forside] + naer
    return maal


def prioriteret(andele: dict, brugt: dict[str, int], tilgaengelige: set[str]) -> list[str]:
    """Spandene i den rækkefølge, de mangler links i forhold til deres andel.
    Spande uden en side falder ud; deres andel fordeles på resten. Forsiden
    står altid sidst som reserve, så en artikel uden et relevant mål stadig
    kan linke et sted hen."""
    aktive = {s: a for s, a in andele.items() if s in tilgaengelige}
    if not aktive:
        return ["forside"]
    total_andel = sum(aktive.values())
    n = sum(brugt.get(s, 0) for s in aktive) + 1
    underskud = {s: a / total_andel * n - brugt.get(s, 0) for s, a in aktive.items()}
    raekke = sorted(aktive, key=lambda s: underskud[s], reverse=True)
    if "forside" not in raekke:
        raekke.append("forside")
    return raekke


def naeste_ankertype(brugte_typer: list[str]) -> str:
    """Den ankertype, linkmålet mangler mest i forhold til ANKER_FORDELING."""
    n = len(brugte_typer) + 1
    return max(ANKER_FORDELING,
               key=lambda t: ANKER_FORDELING[t] * n - brugte_typer.count(t))
