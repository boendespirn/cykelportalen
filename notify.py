"""
notify.py
Korte driftsbeskeder til Telegram.

Hvorfor: når pipelinen flyttes væk fra ejerens skærm (OPS-010), forsvinder også
den måde, fejl blev opdaget på — nemlig at han så dem i vinduet. Uden en besked
ville en død kørsel først blive bemærket, når et løb manglede sit resultat.

Beskeder sendes KUN om drift: et job der fejlede, en etape der ikke fik sit
resultat, og det daglige sammendrag. Ikke om hvert normalt job — en kanal, der
bipper hele dagen, holder man op med at læse.

Mangler `TELEGRAM_BOT_TOKEN` eller `TELEGRAM_CHAT_ID`, gør modulet ingenting og
siger det én gang. Det må aldrig vælte en kørsel, at en besked ikke kunne
sendes: beskeden er tilbehør, dataen er opgaven.
"""

from __future__ import annotations

import os

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
_advaret = False


def aktiv() -> bool:
    return bool(TOKEN and CHAT_ID)


def send(tekst: str) -> bool:
    """Sender én besked. Returnerer om den kom af sted."""
    global _advaret
    if not aktiv():
        if not _advaret:
            print("[notify] TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID mangler — sender ingen beskeder")
            _advaret = True
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": tekst[:4000],
                  "disable_web_page_preview": True},
            timeout=20,
        )
        if not r.ok:
            print(f"[notify] Telegram svarede {r.status_code}: {r.text[:160]}")
        return r.ok
    except Exception as e:
        print(f"[notify] kunne ikke sende: {type(e).__name__}: {e}")
        return False
