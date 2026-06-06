"""
instagram_auth.py
Finder og gemmer META_INSTAGRAM_USER_ID fra den tilknyttede
Instagram Business-konto via Meta Graph API.

Forudsætninger:
  1. Instagram-konto er skiftet til Business/Creator
  2. Instagram er tilknyttet Facebook-siden i Instagram-appen
  3. META_PAGE_ACCESS_TOKEN og META_PAGE_ID er sat i .env
  4. Facebook App har scopes: instagram_basic, instagram_content_publish

Kør: python instagram_auth.py
"""

import os
import re
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN   = os.getenv("META_PAGE_ACCESS_TOKEN")
PAGE_ID = os.getenv("META_PAGE_ID")
GRAPH   = "https://graph.facebook.com/v19.0"


def get_instagram_user_id() -> str | None:
    if not TOKEN or not PAGE_ID:
        print("Fejl: META_PAGE_ACCESS_TOKEN og/eller META_PAGE_ID mangler i .env")
        return None

    res = requests.get(
        f"{GRAPH}/{PAGE_ID}",
        params={"fields": "instagram_business_account", "access_token": TOKEN},
        timeout=10,
    )

    if not res.ok:
        print(f"API-fejl {res.status_code}: {res.text[:300]}")
        return None

    data = res.json()
    ig_id = data.get("instagram_business_account", {}).get("id")

    if not ig_id:
        print("\nIngen Instagram Business Account fundet på Facebook-siden.")
        print("\nTjekliste:")
        print("  1. Gå til Instagram-appen → Indstillinger → Konto → Skift til Business/Professionel")
        print("  2. I Instagram: Indstillinger → Konto → Tilknyttede konti → Facebook-side")
        print("  3. I Meta Developer Console: tilføj Instagram-produkt til din app")
        print("  4. Generer en ny META_PAGE_ACCESS_TOKEN med:")
        print("     scopes: instagram_basic, instagram_content_publish, pages_read_engagement")
        return None

    return ig_id


def save_to_env(ig_id: str) -> None:
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

    with open(env_path, "r", encoding="utf-8") as f:
        content = f.read()

    key = "META_INSTAGRAM_USER_ID"
    new_line = f"{key}={ig_id}"

    if re.search(rf"^{key}=", content, flags=re.MULTILINE):
        content = re.sub(rf"^{key}=.*$", new_line, content, flags=re.MULTILINE)
    else:
        content = content.rstrip("\n") + f"\n{new_line}\n"

    with open(env_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Gemt til .env: {key}={ig_id}")


if __name__ == "__main__":
    print("Henter Instagram Business Account ID...\n")
    ig_id = get_instagram_user_id()

    if not ig_id:
        sys.exit(1)

    print(f"Fandt Instagram User ID: {ig_id}")
    save_to_env(ig_id)
    print("\nKlar! Instagram auto-posting er aktiveret ved næste artikel-godkendelse.")
