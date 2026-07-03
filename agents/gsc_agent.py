"""
Henter data fra Google Search Console for klassementet.dk og rapporterer
optimeringsmuligheder til direktøren (jf. STRATEGI.md prioritet 1: indeksering).

Kræver miljøvariabler (sat i Railway):
  GSC_SERVICE_ACCOUNT_JSON_B64  - service account JSON-nøglen, base64-kodet som én streng
                                  (undgår linjeskift-problemer i .env)
  GSC_PROPERTY_URL              - property som registreret i Search Console, fx
                                  "sc-domain:klassementet.dk" (domain-property) eller
                                  "https://klassementet.dk/" (URL-prefix)

Service accountens email skal være tilføjet som bruger under
Search Console → Indstillinger → Brugere og tilladelser.

Brug:
  python agents/gsc_agent.py
  python agents/gsc_agent.py --days 90
  python agents/gsc_agent.py --inspect-urls "https://klassementet.dk/tour-de-france,https://klassementet.dk/riders/tadej-pogacar"
"""

import os
import json
import base64
import argparse
from datetime import date, timedelta

from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
GSC_PROPERTY_URL = os.getenv("GSC_PROPERTY_URL", "sc-domain:klassementet.dk")


def _load_service():
    raw_b64 = os.getenv("GSC_SERVICE_ACCOUNT_JSON_B64")
    if not raw_b64:
        raise RuntimeError("GSC_SERVICE_ACCOUNT_JSON_B64 mangler i miljøvariablerne.")
    info = json.loads(base64.b64decode(raw_b64))
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("searchconsole", "v1", credentials=creds)


def fetch_search_analytics(service, days=28, row_limit=1000, dimensions=("query", "page")):
    end = date.today() - timedelta(days=3)  # GSC-data har typisk 2-3 dages forsinkelse
    start = end - timedelta(days=days)
    body = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": list(dimensions),
        "rowLimit": row_limit,
    }
    resp = service.searchanalytics().query(siteUrl=GSC_PROPERTY_URL, body=body).execute()
    return resp.get("rows", [])


def fetch_sitemaps(service):
    resp = service.sitemaps().list(siteUrl=GSC_PROPERTY_URL).execute()
    return resp.get("sitemap", [])


def inspect_url(service, page_url):
    body = {"inspectionUrl": page_url, "siteUrl": GSC_PROPERTY_URL}
    resp = service.urlInspection().index().inspect(body=body).execute()
    return resp.get("inspectionResult", {})


def analyze_striking_distance(rows, min_impressions=10):
    """Søgeord hvor vi rangerer 4.-20. plads: kandidater til bedre on-page-signaler."""
    hits = [
        r for r in rows
        if r.get("impressions", 0) >= min_impressions and 4 <= r.get("position", 99) <= 20
    ]
    hits.sort(key=lambda r: -r["impressions"])
    return hits


def analyze_low_ctr(rows, min_impressions=50, ctr_threshold=0.02):
    """Sider med mange visninger men lav CTR: SERP-tekst (titel/meta) bør forbedres."""
    hits = [
        r for r in rows
        if r.get("impressions", 0) >= min_impressions and r.get("ctr", 1) < ctr_threshold
    ]
    hits.sort(key=lambda r: -r["impressions"])
    return hits


def main():
    parser = argparse.ArgumentParser(description="GSC-rapport til direktøren")
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument("--inspect-urls", type=str, default="")
    args = parser.parse_args()

    service = _load_service()

    print(f"=== GSC-rapport for {GSC_PROPERTY_URL} (seneste {args.days} dage) ===\n")

    query_rows = fetch_search_analytics(service, days=args.days, dimensions=("query", "page"))
    page_rows = fetch_search_analytics(service, days=args.days, dimensions=("page",))

    print(f"Søgeord/side-kombinationer hentet: {len(query_rows)}")
    print(f"Sider med performance-data: {len(page_rows)}\n")

    striking = analyze_striking_distance(query_rows)
    print("--- Striking distance (plads 4-20), top 15 ---")
    for r in striking[:15]:
        q, page = r["keys"]
        print(f"  '{q}' -> {page} | pos {r['position']:.1f} | {r['impressions']} visninger | CTR {r['ctr']*100:.1f}%")

    low_ctr = analyze_low_ctr(page_rows)
    print("\n--- Lav CTR trods mange visninger, top 15 ---")
    for r in low_ctr[:15]:
        page = r["keys"][0]
        print(f"  {page} | {r['impressions']} visninger | CTR {r['ctr']*100:.1f}% | pos {r['position']:.1f}")

    sitemaps = fetch_sitemaps(service)
    print("\n--- Sitemap-status ---")
    for sm in sitemaps:
        print(f"  {sm.get('path')} | sidst hentet: {sm.get('lastDownloaded', 'aldrig')} | fejl: {sm.get('errors', 0)} | advarsler: {sm.get('warnings', 0)}")

    if args.inspect_urls:
        print("\n--- URL Inspection ---")
        for u in args.inspect_urls.split(","):
            u = u.strip()
            if not u:
                continue
            result = inspect_url(service, u)
            idx = result.get("indexStatusResult", {})
            print(f"  {u}")
            print(f"    Verdict: {idx.get('verdict')}")
            print(f"    Coverage: {idx.get('coverageState')}")
            print(f"    Sidst crawlet: {idx.get('lastCrawlTime', 'aldrig')}")


if __name__ == "__main__":
    main()
