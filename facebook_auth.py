"""
facebook_auth.py
Henter ny Facebook Page Access Token til Klassementet-siden.

Interaktiv brug (åbner browser):
  python facebook_auth.py

Med token fra URL (non-interaktiv):
  python facebook_auth.py --token EAAG... --save

Tokens holder ~60 dage. Kør scriptet igen når Railway poster fejler.
"""
import argparse, webbrowser, urllib.parse, requests, os, re, subprocess, sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from dotenv import load_dotenv

load_dotenv()

APP_ID       = "991776093267542"
APP_SECRET   = os.getenv("META_APP_SECRET", "")
REDIRECT_URI = "https://klassementet.dk"

SCOPES = [
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_posts",
    "public_profile",
    "instagram_basic",
    "instagram_content_publish",
]

auth_url = (
    f"https://www.facebook.com/dialog/oauth"
    f"?client_id={APP_ID}"
    f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
    f"&scope={','.join(SCOPES)}"
    f"&response_type=token"
)

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--token", default="", help="User access token fra redirect-URL")
parser.add_argument("--save",  action="store_true", help="Gem .env automatisk uden at spørge")
args, _ = parser.parse_known_args()

print("=" * 60)
print("Facebook token-fornyelse — Klassementet")
print("=" * 60)
print()

if args.token:
    user_token = args.token.strip()
    print("Bruger token fra --token argument")
else:
    print("Trin 1: Chrome åbnes — log ind og godkend permissions")
    print("Trin 2: Du landes på klassementet.dk")
    print("        URL'en ser sådan ud:")
    print("        https://klassementet.dk/#access_token=EAAG...&long_lived_token=EAAG...")
    print("        Kopier værdien af long_lived_token= (eller access_token= hvis ingen long_lived)")
    print()

    # Åbn i Chrome (Windows)
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Users\\" + os.getenv("USERNAME", "") + r"\AppData\Local\Google\Chrome\Application\chrome.exe",
    ]
    opened = False
    for chrome in chrome_paths:
        if os.path.exists(chrome):
            subprocess.Popen([chrome, auth_url])
            opened = True
            break
    if not opened:
        webbrowser.open(auth_url)

    user_token = input("Indsæt din token her: ").strip()

# Forsøg at udveksle til langtids-token hvis APP_SECRET kendes
if APP_SECRET:
    ex = requests.get(
        "https://graph.facebook.com/oauth/access_token",
        params={
            "grant_type":        "fb_exchange_token",
            "client_id":         APP_ID,
            "client_secret":     APP_SECRET,
            "fb_exchange_token": user_token,
        },
        timeout=10,
    )
    if ex.ok and "access_token" in ex.json():
        user_token = ex.json()["access_token"]
        print("✓ Byttet til langtids-token (60 dage)")
    else:
        print(f"[!] Langtids-udveksling fejlede: {ex.json()} — bruger token as-is")
else:
    print("[!] META_APP_SECRET ikke sat — bruger token direkte (kan udløbe hurtigere)")

# Hent Page Access Token
r = requests.get(
    "https://graph.facebook.com/me/accounts",
    params={"access_token": user_token},
    timeout=10,
)
data = r.json()
if "data" not in data:
    print("\nFejl fra Facebook:", data)
    sys.exit(1)

page = next((p for p in data["data"] if p.get("name") == "Klassementet"), None)
if not page:
    print("\nKlassementet-siden ikke fundet. Tilgængelige sider:")
    for p in data["data"]:
        print(f"  {p['name']} — ID: {p['id']}")
    sys.exit(1)

page_token = page["access_token"]
page_id    = page["id"]

print()
print("=" * 60)
print(f"✓ Side fundet: {page['name']} (ID: {page_id})")
print("=" * 60)

if args.save:
    save = True
else:
    svar = input("\nSkal jeg opdatere .env automatisk? (j/n): ").strip().lower()
    save = svar == "j"

if save:
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    with open(env_path, "r", encoding="utf-8") as f:
        env_content = f.read()

    env_content = re.sub(r"META_PAGE_ACCESS_TOKEN=.*", f"META_PAGE_ACCESS_TOKEN={page_token}", env_content)
    env_content = re.sub(r"META_PAGE_ID=.*",          f"META_PAGE_ID={page_id}",          env_content)

    with open(env_path, "w", encoding="utf-8") as f:
        f.write(env_content)

    print("✓ .env opdateret")
else:
    print("\nOpdater .env manuelt med disse to linjer:")
    print(f"  META_PAGE_ACCESS_TOKEN={page_token}")
    print(f"  META_PAGE_ID={page_id}")

print("\nHusk også at opdatere Railway Variables!")
