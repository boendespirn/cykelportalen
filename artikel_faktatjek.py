"""
artikel_faktatjek.py
Faktatjek af nyhedsartiklerne, før de publiceres — ejer-godkendt 2026-11-08
sammen med fuldautomatisk publicering ("artikler skal køre fuldautomatisk
fremover"). Uden et menneske i køen er det her, der står mellem en kladde og
siden.

Hvorfor: "19-årig træner vildt for at slå Pogačar" (juni 2026) kaldte Paul
Seixas "den portugisiske João Seixas". Kilden var 265 tegn fra RSS-feedet, og
prompten krævede 600-900 ord — resten blev digtet. Derfor tre trin:

  0. hent_kildetekst(): hele kildeartiklen hentes; RSS-feedet giver ofte kun
     en teaser (CyclingNews/CyclingWeekly: median 4 tegn). For lidt kilde =
     ingen artikel.
  1. tjek_mod_data(): fast regel uden AI — rytternavne slås op i vores
     ryttertabel; et forkert fornavn eller en forkert nationalitet ved navnet
     er en fejl.
  2. tjek_mod_kilde(): en separat AI-gennemgang lister hver faktuel påstand
     med grundlag (kilde, vores data, almen viden) og fjerner dem uden. Den
     kan kassere artiklen helt.

Efter trin 2 køres trin 1 igen på den rettede tekst; står der stadig en fejl,
kasseres artiklen. Korrekthed før alt (CLAUDE.md §9.1): hellere ingen artikel
end en forkert.
"""

import json
import re
from collections import defaultdict
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

FAKTATJEK_MODEL = "claude-opus-5-5"
MIN_KILDE_TEGN = 600      # under dette er der ikke stof nok til en artikel
MAX_KILDE_TEGN = 9000
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130 Safari/537.36"}

# Nationalitet (ISO-kode som i riders.nationality) → danske adjektivstammer.
NATIONALITET = {
    "DK": ["dansk"], "FR": ["fransk"], "ES": ["spansk"], "PT": ["portugisisk"],
    "IT": ["italiensk"], "BE": ["belgisk"], "NL": ["hollandsk", "nederlandsk"],
    "SI": ["slovensk"], "GB": ["britisk", "engelsk", "skotsk", "walisisk"],
    "US": ["amerikansk"], "AU": ["australsk"], "CO": ["colombiansk"],
    "EC": ["ecuadoriansk"], "NO": ["norsk"], "DE": ["tysk"], "CH": ["schweizisk"],
    "AT": ["østrigsk"], "PL": ["polsk"], "CZ": ["tjekkisk"], "SK": ["slovakisk"],
    "IE": ["irsk"], "CA": ["canadisk"], "NZ": ["newzealandsk"], "ZA": ["sydafrikansk"],
    "ER": ["eritreansk"], "MX": ["mexicansk"], "LU": ["luxembourgsk"],
    "KZ": ["kasakhisk", "kasakhstansk"], "SE": ["svensk"], "EE": ["estisk"],
    "LV": ["lettisk"], "LT": ["litauisk"], "RU": ["russisk"], "UA": ["ukrainsk"],
    "VE": ["venezuelansk"], "AR": ["argentinsk"], "HU": ["ungarsk"],
    "HR": ["kroatisk"], "FI": ["finsk"], "JP": ["japansk"], "IL": ["israelsk"],
    "BY": ["hviderussisk"], "RO": ["rumænsk"], "RS": ["serbisk"], "GR": ["græsk"],
    "CR": ["costaricansk"], "PA": ["panamansk"], "UY": ["uruguayansk"],
    "CL": ["chilensk"], "TR": ["tyrkisk"], "ET": ["etiopisk"], "RW": ["rwandisk"],
}
_ADJ = {stamme: kode for kode, stammer in NATIONALITET.items() for stamme in stammer}
_NAT_FOER_NAVN = re.compile(
    r"\b((?i:" + "|".join(sorted(_ADJ, key=len, reverse=True)) + r"))e\s+"
    r"(?:[a-zæøå\-]+\s+)?(?:[A-ZÀ-Þ][\wÀ-ÿ'\-]+\s+)?$")
PARTIKLER = {"van", "de", "der", "den", "le", "la", "di", "da", "del", "du", "von", "ten", "ter"}

# Ord med stort begyndelsesbogstav, der kan stå lige før et efternavn uden at
# være et fornavn.
IKKE_FORNAVN = {
    "Den", "Det", "De", "Da", "Når", "Men", "Og", "Hvor", "Som", "Mens", "Efter",
    "Før", "For", "Til", "Med", "Hos", "Om", "Ifølge", "Både", "Også", "Her",
    "Der", "Nu", "Så", "Derfor", "Unge", "Selvom", "Hvis", "Dersom", "Fordi",
    "Kan", "Vil", "Skal", "Mod", "Uden", "Ved", "Fra", "Over", "Under", "Mellem",
    "Allerede", "Endnu", "Kun", "Netop", "Især", "Ikke", "Hverken", "Enten", "Danske", "Holdkaptajn", "Kaptajn",
    "Hollænderen", "Belgieren", "Franskmanden", "Slovenen", "Dansker", "Danskeren",
    "Superstjernen", "Stjernen", "Mester", "Verdensmester", "Kollega", "Holdkammerat",
    "Tour", "Giro", "Vuelta", "Team", "Visma", "UAE", "Red", "Bull", "Lidl",
    "Trek", "Soudal", "Quick", "Step", "Ineos", "Grenadiers", "Bora", "Alpecin",
    "Jayco", "Movistar", "Decathlon", "EF", "Cofidis", "Uno", "X", "Israel",
    "Tudor", "Q36", "Picnic", "Groupama", "FDJ", "Lotto", "Intermarché", "Wanty",
    "Bahrain", "Victorious", "Astana", "XDS", "Arkéa", "Total", "Energies",
}


# ── Trin 0: kilden ────────────────────────────────────────────────────────────

def hent_kildetekst(url: str, rss_tekst: str = "") -> str:
    """Kildeartiklens brødtekst. To metoder — den forælder, der rummer mest
    afsnitstekst, og alle afsnit i <article> — og den længste vinder; RSS-
    teksten, hvis den er længere endnu. Tom streng, hvis siden ikke kan hentes."""
    kandidater = [rss_tekst or ""]
    try:
        r = requests.get(url, headers=UA, timeout=25)
        if r.ok:
            soup = BeautifulSoup(r.text, "html.parser")
            for t in soup(["script", "style", "nav", "footer", "aside", "figure", "form"]):
                t.decompose()
            ps = soup.find_all("p")
            if ps:
                score = defaultdict(int)
                for p in ps:
                    score[id(p.parent)] += len(p.get_text(strip=True))
                bedst = max(ps, key=lambda p: score[id(p.parent)]).parent
                kandidater.append(_afsnit(bedst))
            art = soup.find("article")
            if art:
                kandidater.append(_afsnit(art))
    except requests.RequestException:
        pass
    return max(kandidater, key=len)[:MAX_KILDE_TEGN]


def _afsnit(el) -> str:
    tekster = (p.get_text(" ", strip=True) for p in el.find_all("p"))
    return "\n".join(t for t in tekster if len(t) > 40)


# ── Trin 1: vores egne data ───────────────────────────────────────────────────

def hent_ryttere(supabase_url: str, key: str) -> list[dict]:
    """Ryttertabellen med hold: [{fornavn, efternavn, nationalitet, hold}]."""
    hdr = {"apikey": key, "Authorization": f"Bearer {key}"}
    ud, fra = [], 0
    while True:
        r = requests.get(f"{supabase_url}/rest/v1/riders?select=name,nationality,teams(name)"
                         f"&order=name", headers={**hdr, "Range": f"{fra}-{fra + 999}"}, timeout=30)
        r.raise_for_status()
        rows = r.json()
        for x in rows:
            efternavn, fornavn = _del_navn(x["name"])
            if efternavn and fornavn:
                ud.append({"fornavn": fornavn, "efternavn": efternavn,
                           "nationalitet": x.get("nationality"),
                           "hold": (x.get("teams") or {}).get("name")})
        if len(rows) < 1000:
            return ud
        fra += 1000


def _del_navn(navn: str) -> tuple[str, str]:
    """"VAN DER POEL Mathieu" → ("Van Der Poel", "Mathieu"). PCS skriver
    efternavnet med versaler."""
    ord_ = navn.split()
    efter = [o for o in ord_ if (o.isupper() and len(o) > 1)]
    for_ = [o for o in ord_ if o not in efter]
    return " ".join(o.capitalize() for o in efter), " ".join(for_)


def _efternavn_re(efternavn: str) -> re.Pattern:
    navn = r"\s+".join(re.escape(d) for d in efternavn.split())
    return re.compile(r"(?<![\wÀ-ÿ])" + navn + r"(?![\wÀ-ÿ])",
                      re.I if " " in efternavn else 0)


def tjek_mod_data(tekst: str, ryttere: list[dict], kilde: str = "") -> tuple[list[dict], list[str]]:
    """(nævnte ryttere med vores fakta, fejl).

    Kun entydige efternavne tjekkes for fornavn. Et andet fornavn er ikke en
    fejl, hvis netop det fulde navn står i kilden — så er det en anden person
    (Dan Martin er ikke Guillaume Martin)."""
    pr_efternavn = defaultdict(list)
    for r in ryttere:
        if len(r["efternavn"]) >= 4:
            pr_efternavn[r["efternavn"].lower()].append(r)

    # To rytternavne efter hinanden ("Ayuso Seixas" i en opremsning) er ikke
    # et forkert fornavn.
    alle_efternavne = {d.lower() for r in ryttere for d in r["efternavn"].split()}

    naevnte, fejl = [], []
    for kandidater in pr_efternavn.values():
        forekomster = list(_efternavn_re(kandidater[0]["efternavn"]).finditer(tekst))
        if not forekomster:
            continue
        fornavne = {k["fornavn"].split()[0].lower() for k in kandidater}
        for m in forekomster:
            foer = tekst[max(0, m.start() - 80):m.start()]
            ord_foer = re.findall(r"[\wÀ-ÿ'\-]+", foer)
            # Ordet lige før navnet, kun adskilt af mellemrum. Står det først i
            # en sætning, er det stort uanset hvad ("Hvis Seixas ..."), og en
            # partikel hører til efternavnet ("Van Aerts").
            mf = re.search(r"(^|.)\s*([\wÀ-ÿ'\-]+)\s+$", foer, re.S)
            forrige = mf.group(2) if mf else ""
            saetningsstart = not mf or mf.group(1) in ("", ".", "!", "?", ":", "\n", '"', "“", "”", "»", "«")
            if forrige and forrige[0].isupper() and forrige not in IKKE_FORNAVN \
                    and not saetningsstart and len(forrige) >= 3 \
                    and forrige.lower() not in PARTIKLER \
                    and forrige.lower() not in alle_efternavne \
                    and not re.search(r"[-\d][a-zæøå]|\d", forrige) \
                    and forrige.lower() not in fornavne:
                fuldt = f"{forrige} {m.group(0)}"
                if len(kandidater) == 1 and fuldt.lower() not in kilde.lower():
                    r = kandidater[0]
                    fejl.append(f"'{fuldt}': vores rytter hedder {r['fornavn']} {r['efternavn']}")
                continue
            if forrige.lower() in fornavne:
                rytter = next(k for k in kandidater if k["fornavn"].split()[0].lower() == forrige.lower())
            elif len(kandidater) == 1:
                rytter = kandidater[0]
            else:
                continue
            if rytter not in naevnte:
                naevnte.append(rytter)
            # Nationalitet direkte ved navnet: "den portugisiske (cykeltalent)
            # (João) Seixas". Et adjektiv længere væk hører typisk til noget
            # andet ("schweizisk bjergfinale").
            adj = _NAT_FOER_NAVN.search(foer)
            if adj:
                kode = _ADJ[adj.group(1).lower()]
                if rytter["nationalitet"] and kode != rytter["nationalitet"]:
                    fejl.append(f"'{adj.group(0)} … {m.group(0)}': {rytter['fornavn']} "
                                f"{rytter['efternavn']} er {rytter['nationalitet']} i vores data")
    return naevnte, sorted(set(fejl))


# ── Trin 2: kilden ────────────────────────────────────────────────────────────

FAKTATJEK_SYSTEM = """Du er faktatjekker på klassementet.dk. En artikel publiceres automatisk, hvis du godkender den — der er intet menneske efter dig. Korrekthed går forud for alt; hellere en kortere artikel end en forkert.

Du får kildeartiklen, vores data om de nævnte ryttere og vores danske artikel. Gør tre ting:

1. List hver faktuel påstand i artiklen og titlen: navne, nationaliteter, hold, resultater, placeringer, tider, tal, datoer, citater, hvem der sagde hvad. Giv hver et grundlag:
   - "kilde": står i kildeartiklen (også i oversat form)
   - "data": står i vores data nedenfor
   - "almen": sikker, almindeligt kendt viden, der ikke kan være forældet (fx at Tour de France er et tre ugers etapeløb). ALDRIG for konkrete tal, resultater, holdtilknytninger, nationaliteter, alder eller citater — de skal have kilde eller data.
   - "uden_grundlag": hverken i kilde eller data
   - "modsagt": kilden eller vores data siger noget andet
2. Ret artiklen: fjern eller omskriv hver påstand med "uden_grundlag" eller "modsagt", med så små indgreb som muligt. Tilføj intet nyt. Bevar markdown, afsnit og links præcis som de er (et link må kun forsvinde sammen med den sætning, det står i).
3. Afgør: "publicer" eller "kasser". Kasser, hvis artiklens hovedpåstand (titel eller første afsnit) er uden grundlag eller modsagt, eller hvis der efter rettelserne ikke længere står en sammenhængende nyhed tilbage. Der er intet længdekrav: en kort, korrekt nyhed publiceres.

Svar KUN med JSON:
{"paastande": [{"paastand": "...", "grundlag": "kilde|data|almen|uden_grundlag|modsagt"}],
 "titel": "rettet titel (uændret, hvis den er korrekt)",
 "content": "den rettede artikel",
 "dom": "publicer|kasser",
 "begrundelse": "én sætning"}"""


def tjek_mod_kilde(client, kilde: str, titel: str, content: str,
                   naevnte: list[dict], data_fejl: list[str]) -> dict | None:
    data = "\n".join(f"- {r['fornavn']} {r['efternavn']}: nationalitet {r['nationalitet'] or '?'}, "
                     f"hold {r['hold'] or '?'}" for r in naevnte) or "(ingen kendte ryttere nævnt)"
    advarsler = ("\n\nVores faste kontrol har fundet disse uoverensstemmelser med vores data. "
                 "Ret dem, medmindre kilden klart viser, at det er en anden person:\n"
                 + "\n".join(f"- {f}" for f in data_fejl)) if data_fejl else ""
    prompt = (f"KILDEARTIKEL:\n{kilde}\n\nVORES DATA OM NÆVNTE RYTTERE:\n{data}{advarsler}\n\n"
              f"VORES ARTIKEL\nTitel: {titel}\n\n{content}")
    try:
        resp = client.messages.create(model=FAKTATJEK_MODEL, max_tokens=8000,
                                      system=FAKTATJEK_SYSTEM,
                                      messages=[{"role": "user", "content": prompt}])
        if resp.stop_reason == "max_tokens":
            return None
        tekst = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "")
        svar = json.loads(tekst[tekst.find("{"):tekst.rfind("}") + 1])
        return svar if svar.get("content") and svar.get("dom") in ("publicer", "kasser") else None
    except Exception as e:
        print(f"  [FAKTATJEK FEJL] {e}")
        return None


# ── Samlet ────────────────────────────────────────────────────────────────────

def faktatjek(client, kilde: str, titel: str, content: str, ryttere: list[dict]) -> dict:
    """Hele tjekket. Returnerer {godkendt, titel, content, rapport}. Rapporten
    gemmes i news_articles.faktatjek, så hvert afslag kan forklares."""
    rapport = {"tidspunkt": datetime.now(timezone.utc).isoformat(),
               "kilde_tegn": len(kilde), "model": FAKTATJEK_MODEL}

    def afvis(grund: str) -> dict:
        rapport["dom"] = "kasser"
        rapport["begrundelse"] = grund
        return {"godkendt": False, "titel": titel, "content": content, "rapport": rapport}

    if len(kilde) < MIN_KILDE_TEGN:
        return afvis(f"for lidt kildetekst ({len(kilde)} tegn)")

    naevnte, data_fejl = tjek_mod_data(f"{titel}\n\n{content}", ryttere, kilde)
    rapport["data_fejl_foer"] = data_fejl
    svar = tjek_mod_kilde(client, kilde, titel, content, naevnte, data_fejl)
    if not svar:
        return afvis("faktatjekket gav intet brugbart svar")
    rapport["paastande"] = svar.get("paastande", [])
    rapport["begrundelse"] = svar.get("begrundelse", "")
    if svar["dom"] == "kasser":
        return afvis(svar.get("begrundelse") or "kasseret af faktatjekket")

    ny_titel, nyt = svar.get("titel") or titel, svar["content"]
    # Efter rettelsen er kun nationalitet en hård regel. Et "forkert fornavn"
    # har faktatjekket fået forelagt og afgjort mod kilden — "Strava King" er
    # ikke rytteren Carden King, og reglen kan ikke se forskel.
    _, rest = tjek_mod_data(f"{ny_titel}\n\n{nyt}", ryttere, kilde)
    rest = [f for f in rest if "i vores data" in f]
    if rest:
        rapport["data_fejl_efter"] = rest
        return afvis("fejl mod vores data stod tilbage efter rettelsen: " + "; ".join(rest))
    # Intet længdekrav (ejeren 2026-11-08: "er en nyhed god, så er den god") —
    # kun et værn mod en rest, der ikke er en nyhed længere.
    if len(nyt.split()) < 50:
        return afvis(f"der er ingen nyhed tilbage efter rettelserne ({len(nyt.split())} ord)")

    rapport["dom"] = "publicer"
    rapport["rettet"] = nyt != content or ny_titel != titel
    rapport["fjernede_paastande"] = [p["paastand"] for p in rapport["paastande"]
                                     if p.get("grundlag") in ("uden_grundlag", "modsagt")]
    return {"godkendt": True, "titel": ny_titel, "content": nyt, "rapport": rapport}
