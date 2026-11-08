"""
artikel_links.py
Ét sikkerhedsnet for de interne links i nyhedsartiklerne — brugt alle steder,
en artikel bliver skrevet eller publiceret: ai_news_processor.py (kladden),
api.py (godkend og "Ret med feedback") og artikel_linktjek.py (workerens
løbende tjek af alt det publicerede).

Regler (STRATEGI.md §2a og ai_news_processor.py's prompt):
  - højst MAX_INTERNE interne links pr. artikel,
  - hvert mål linkes kun én gang (resten bliver plain text),
  - kun mål, der findes: forsiden, løbskalenderen, cross-serierne og løb
    (evt. en etape), der står i databasen.

Både markdown-links og HTML-<a> håndteres. Det var HTML, der slap igennem i
oktober 2026: "Ret med feedback" lod modellen skrive <a href="/giro-ditalia">
fire gange i én artikel, og den gamle kontrol kendte kun markdown.

Et link, der ikke må stå, bliver til sin ankertekst — teksten bevares altid.
"""

import re

import requests

import linkstrategi

MAX_INTERNE = 2
SITE = "https://klassementet.dk"

# Faste sider, en artikel må linke til. Cross-serierne skal følge
# cykel-frontend/lib/crossSerier.ts.
FASTE = {"/", "/races", "/races/cykelcross", "/nyheder"}
CROSS_SERIER = {"world-cup", "superprestige", "x2o-trofee", "hg-cross",
                "mesterskaber", "oevrige"}
FASTE |= {f"/races/cykelcross/{s}" for s in CROSS_SERIER}

# Markdown [tekst](url) eller HTML <a ... href="url" ...>tekst</a>
_LINK = re.compile(
    r"\[(?P<mtekst>[^\]]+)\]\((?P<murl>[^)\s]+)\)"
    r"|<a\b(?P<attr>[^>]*?)href=[\"'](?P<hurl>[^\"']+)[\"'][^>]*>(?P<htekst>.*?)</a>",
    re.S | re.I,
)


def hent_race_slugs(supabase_url: str, key: str) -> set[str]:
    """Alle løbs-slugs i databasen (sideinddelt — der er over tusind)."""
    hdr = {"apikey": key, "Authorization": f"Bearer {key}"}
    slugs: set[str] = set()
    fra = 0
    while True:
        r = requests.get(f"{supabase_url}/rest/v1/races?select=slug&order=slug",
                         headers={**hdr, "Range": f"{fra}-{fra + 999}"}, timeout=30)
        r.raise_for_status()
        rows = r.json()
        slugs |= {x["slug"] for x in rows}
        if len(rows) < 1000:
            return slugs
        fra += 1000


def er_intern(url: str) -> bool:
    return url.startswith("/") or bool(re.match(r"^https?://(www\.)?klassementet\.dk", url))


def normaliser(url: str) -> str:
    """Intern url → sti uden domæne, query, anker og afsluttende skråstreg.
    En årstalsadresse med fast adresse (tour-de-france-2027) bliver til den
    faste, så linket ikke går gennem en videresendelse."""
    sti = re.sub(r"^https?://(www\.)?klassementet\.dk", "", url)
    sti = re.split(r"[?#]", sti)[0] or "/"
    if len(sti) > 1:
        sti = sti.rstrip("/") or "/"
    m = re.match(r"^/([^/]+)(/.*)?$", sti)
    if m and m.group(1) in linkstrategi.EVERGREEN:
        sti = linkstrategi.EVERGREEN[m.group(1)] + (m.group(2) or "")
    return sti


def _reparer(sti: str) -> str | None:
    """En stavefejl i en fast adresse (/giro-ditalia, /tourdefrance) rettes til
    den faste adresse — kun når det entydigt er den. Alt andet: None."""
    noegle = re.sub(r"[^a-z]", "", sti.lower())
    for fast in linkstrategi.EVERGREEN.values():
        if noegle == re.sub(r"[^a-z]", "", fast):
            return fast
    return None


def er_gyldig(sti: str, race_slugs: set[str]) -> bool:
    if sti in FASTE or sti in linkstrategi.EVERGREEN.values():
        return True
    m = re.match(r"^/([^/]+)(?:/stage/\d+)?$", sti)
    if not m:
        return False
    return m.group(1) in race_slugs or ("/" + m.group(1)) in linkstrategi.EVERGREEN.values()


def rens(content: str, race_slugs: set[str], doede: set[str] = frozenset(),
         max_interne: int = MAX_INTERNE) -> tuple[str, list[str]]:
    """Returnerer (renset indhold, ændringer i klartekst).

    `doede` er stier, der er set svare 404 live — de fjernes, selv om
    databasen kender løbet."""
    brugte: list[str] = []
    aendringer: list[str] = []

    def erstat(m: re.Match) -> str:
        html = m.group("hurl") is not None
        url = m.group("hurl") if html else m.group("murl")
        tekst = m.group("htekst") if html else m.group("mtekst")
        if not er_intern(url):
            return m.group(0)
        sti = normaliser(url)
        if not er_gyldig(sti, race_slugs):
            rettet = _reparer(sti)
            if not rettet:
                aendringer.append(f"fjernet link til {url} (siden findes ikke)")
                return tekst
            aendringer.append(f"rettet {url} → {rettet}")
            sti = rettet
        if sti in doede:
            aendringer.append(f"fjernet link til {sti} (svarer 404)")
            return tekst
        if sti in brugte:
            aendringer.append(f"fjernet gentaget link til {sti}")
            return tekst
        if len(brugte) >= max_interne:
            aendringer.append(f"fjernet link til {sti} (over {max_interne} interne links)")
            return tekst
        brugte.append(sti)
        if sti == url:
            return m.group(0)
        if html:
            return f'<a{m.group("attr")}href="{sti}">{tekst}</a>'
        return f"[{tekst}]({sti})"

    return _LINK.sub(erstat, content or ""), aendringer


def interne_stier(content: str) -> list[str]:
    """Stierne på alle interne links, i rækkefølge (markdown og HTML)."""
    ud = []
    for m in _LINK.finditer(content or ""):
        url = m.group("hurl") or m.group("murl")
        if er_intern(url):
            ud.append(normaliser(url))
    return ud
