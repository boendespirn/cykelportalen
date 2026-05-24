"""Test hvilke GC-ryttere der kan slås op i DB."""
from dotenv import load_dotenv
load_dotenv()
from results_agent import get_rider_id

gc_riders = [
    ("jonas-vingegaard",    "VINGEGAARD JONAS"),
    ("afonso-eulalio",      "EULALIO AFONSO"),
    ("felix-gall",          "GALL FELIX"),
    ("thymen-arensman",     "ARENSMAN THYMEN"),
    ("jai-hindley",         "HINDLEY JAI"),
    ("giulio-pellizzari",   "PELLIZZARI GIULIO"),
    ("michael-storer",      "STORER MICHAEL"),
    ("ben-oconnor",         "OCONNOR BEN"),
    ("derek-gee-west",      "GEE WEST DEREK"),
    ("davide-piganzoli",    "PIGANZOLI DAVIDE"),
    ("mathys-rondel",       "RONDEL MATHYS"),
    ("egan-bernal",         "BERNAL EGAN"),
    ("chris-harper",        "HARPER CHRIS"),
    ("damiano-caruso",      "CARUSO DAMIANO"),
    ("david-de-la-cruz",    "DE LA CRUZ DAVID"),
    ("jan-hirt",            "HIRT JAN"),
    ("sepp-kuss",           "KUSS SEPP"),
    ("markel-beloki",       "BELOKI MARKEL"),
    ("gregor-muehlberger",  "MUEHLBERGER GREGOR"),
    ("igor-arrieta",        "ARRIETA IGOR"),
]
found = 0
for slug, name in gc_riders:
    rid = get_rider_id(slug, name)
    status = "OK" if rid else "MANGLER"
    print(f"  {status}  {slug}")
    if rid:
        found += 1

print(f"\nFundet: {found}/{len(gc_riders)}")
