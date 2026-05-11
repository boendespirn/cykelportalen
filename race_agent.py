import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from slugify import slugify

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

SOURCE_URL = "https://www.velowire.com/UCIcyclingcalendar/calendar/241/uci-worldtour/2026.html"


def clean_date(text):
    text = text.replace("on ", "")
    text = text.replace("from ", "")
    text = text.replace("until ", "")
    text = text.strip()

    day, month, year = text.split("-")
    return f"{year}-{month}-{day}"


def normalize_name(name):
    replacements = {
        "Tour of Italy (Giro d'Italia)": "Giro d'Italia",
        "Tour of Switzerland (Tour de Suisse)": "Tour de Suisse",
    }
    return replacements.get(name, name)


def guess_country(name):
    if "France" in name or "Paris" in name:
        return "FR"
    if "Italy" in name or "Giro" in name or "Milano" in name or "Lombardia" in name:
        return "IT"
    if "Copenhagen" in name:
        return "DK"
    if "Suisse" in name or "Switzerland" in name:
        return "CH"
    if "Vuelta" in name or "Catalunya" in name or "Basque" in name:
        return "ES"
    if "Flanders" in name or "Ronde" in name or "Liège" in name:
        return "BE"
    return None


response = requests.get(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"})
print("Henter kalender:", response.status_code)

soup = BeautifulSoup(response.text, "html.parser")

supabase_url = f"{SUPABASE_URL}/rest/v1/races?on_conflict=slug"

headers = {
    "apikey": SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates"
}

count = 0

for row in soup.find_all("tr"):
    cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]

    if len(cells) < 2:
        continue

    name = normalize_name(cells[0])
    date_text = cells[1]

    if not ("on " in date_text or "from " in date_text or "until " in date_text):
        continue

    start_date = clean_date(date_text)

    race = {
        "name": name,
        "slug": slugify(f"{name}-2026"),
        "category": "UCI WorldTour",
        "country_code": guess_country(name),
        "start_date": start_date,
        "end_date": start_date,
        "source": "velowire",
        "source_url": SOURCE_URL
    }

    result = requests.post(supabase_url, headers=headers, json=race)

    print("Gemmer:", name, "| Status:", result.status_code)

    count += 1

print("Færdig:", count)