import os, requests, json
from dotenv import load_dotenv
load_dotenv()
URL = os.getenv("SUPABASE_URL","").rstrip("/")
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
AUTH = {"apikey": KEY, "Authorization": f"Bearer {KEY}"}

res = requests.get(
    f"{URL}/rest/v1/startlists"
    f"?race_id=eq.a4f527df-17a4-479d-befd-140f99439779"
    f"&gc_position=not.is.null"
    f"&select=gc_position,gc_time_gap_seconds,riders(name)"
    f"&order=gc_position.asc&limit=10",
    headers=AUTH
)
print("Status:", res.status_code)
print(res.text[:500])
