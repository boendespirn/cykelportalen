"""
facebook_auth.py
Åbner browser til Facebook OAuth med pages_manage_posts permission.
Brug dette til at få en bruger-token, som derefter byttes til Page Access Token.

Kør: python facebook_auth.py
"""
import webbrowser, urllib.parse

APP_ID = "991776093267542"
REDIRECT_URI = "https://klassementet.dk"

SCOPES = [
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_posts",
    "public_profile",
]

url = (
    f"https://www.facebook.com/dialog/oauth"
    f"?client_id={APP_ID}"
    f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
    f"&scope={','.join(SCOPES)}"
    f"&response_type=token"
)

print("Åbner Facebook i browseren...")
print()
print("1. Log ind og godkend permissions")
print("2. Du bliver sendt til klassementet.dk — URL'en vil indeholde #access_token=...")
print("3. Kopier ALT det efter #access_token= og frem til &token_type")
print("4. Det er din USER token — vi bytter den til en PAGE token herunder")
print()
webbrowser.open(url)

user_token = input("Indsæt din USER token her: ").strip()

import requests
# Byt user token til page access token
r = requests.get(
    f"https://graph.facebook.com/me/accounts",
    params={"access_token": user_token},
)
data = r.json()
if "data" not in data:
    print("Fejl:", data)
    exit(1)

for page in data["data"]:
    if page.get("name") == "Klassementet":
        print()
        print(f"Fundet side: {page['name']} (ID: {page['id']})")
        print()
        print("Tilfoej dette til .env:")
        print(f"META_PAGE_ACCESS_TOKEN={page['access_token']}")
        print(f"META_PAGE_ID={page['id']}")
        break
else:
    print("Klassementet-siden ikke fundet. Tilgaengelige sider:")
    for p in data["data"]:
        print(f"  {p['name']} — ID: {p['id']}")
