import requests
from bs4 import BeautifulSoup

url = "https://www.velowire.com/UCIcyclingcalendar/calendar/241/uci-worldtour/2026.html"

headers = {
    "User-Agent": "Mozilla/5.0"
}

response = requests.get(url, headers=headers)
print("Status code:", response.status_code)

soup = BeautifulSoup(response.text, "html.parser")

for row in soup.find_all("tr"):
    cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]

    if len(cells) > 0:
        print(cells)