"""
One-time script: convert string-type fun_facts to proper JSON arrays.
"""
import ast
import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

AUTH = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}
HEADERS = {**AUTH, "Content-Type": "application/json", "Prefer": "return=minimal"}


def parse_facts(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(f) for f in raw]
    if not isinstance(raw, str) or not raw.strip():
        return []
    text = raw.strip()
    if text.startswith("["):
        depth, end = 0, -1
        for i, ch in enumerate(text):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end >= 0:
            try:
                facts = ast.literal_eval(text[: end + 1])
                if isinstance(facts, list):
                    result = [str(f) for f in facts]
                    rest = text[end + 1 :].strip()
                    if rest:
                        result.append(rest)
                    return result
            except Exception as e:
                print(f"  ast.literal_eval failed: {e}")
    return [text] if text else []


race_res = requests.get(
    f"{SUPABASE_URL}/rest/v1/races?slug=eq.giro-d-italia-2026&select=id&limit=1",
    headers=AUTH,
)
race_id = race_res.json()[0]["id"]

stages_res = requests.get(
    f"{SUPABASE_URL}/rest/v1/stages?race_id=eq.{race_id}&select=id,stage_number,fun_facts&order=stage_number.asc",
    headers=AUTH,
)
stages = stages_res.json()

fixed = 0
for stage in stages:
    raw = stage.get("fun_facts")
    if raw is None or isinstance(raw, list):
        continue  # already fine

    parsed = parse_facts(raw)
    if not parsed:
        continue

    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/stages?id=eq.{stage['id']}",
        json={"fun_facts": parsed},
        headers=HEADERS,
    )
    if res.ok:
        print(f"E{stage['stage_number']}: fixed ({len(parsed)} facts)")
        fixed += 1
    else:
        print(f"E{stage['stage_number']}: FAILED {res.status_code} {res.text}")

print(f"\nDone: {fixed} stages repaired")
