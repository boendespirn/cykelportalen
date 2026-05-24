"""Test PCS scraping for stage 15 og vis hvad regex finder."""
import re, time
from playwright.sync_api import sync_playwright

URL = "https://www.procyclingstats.com/race/giro-d-italia/2026/stage-15/result"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    page.goto(URL, wait_until="networkidle", timeout=30000)
    time.sleep(2)
    html = page.content()
    browser.close()

print(f"HTML-længde: {len(html)}")

# Prøv den eksisterende regex
result_rows = re.findall(
    r'<tr[^>]*>.*?<td[^>]*>(\d+)</td>'
    r'.*?rider/([a-z0-9\-]+)"[^>]*>([^<]+)</a>'
    r'.*?<td[^>]*>([\d:+]+)</td>',
    html, re.DOTALL
)
print(f"Eksisterende regex fandt: {len(result_rows)} rækker")
if result_rows:
    for r in result_rows[:3]:
        print(f"  {r}")

# Kig på de første 3000 tegn af result-tabellen
idx = html.find("result")
if idx > 0:
    snippet = html[max(0,idx-200):idx+2000]
    print("\nHTML ved 'result':")
    print(snippet[:1500])

# Find ryttere på siden
riders = re.findall(r'rider/([a-z0-9\-]+)"[^>]*>([^<]+)</a>', html)
print(f"\nRyttere fundet på siden: {len(riders)}")
for r in riders[:5]:
    print(f"  {r}")
