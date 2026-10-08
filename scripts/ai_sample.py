#!/usr/bin/env python3
"""SITE-1: the AI page's sample conversation and free CSV come from ONE existing Etsy Search Scraper run.

  python scripts/ai_sample.py --run-id <id>     # read-only: fetch the run + its dataset, write data/ai-sample/

Never starts a run. Refuses a run that did not SUCCEED, is on a build older than MIN_BUILD, or whose dataset
item count differs from the rows written. Token: APIFY_TOKEN env or APIFY_TOKEN_FILE (never printed).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import urllib.request

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
OUT = os.path.join(ROOT, "data", "ai-sample")
MIN_BUILD = (0, 2, 8)
FIELDS = ["query", "position", "title", "url", "price", "currency", "shop_name", "shop_url", "rating_value",
          "review_count", "review_count_approx", "bestseller", "star_seller", "popular_now", "etsys_pick",
          "free_shipping", "is_ad", "total_results", "run_id"]


def token():
    t = os.environ.get("APIFY_TOKEN")
    if not t and os.environ.get("APIFY_TOKEN_FILE"):
        t = open(os.environ["APIFY_TOKEN_FILE"]).read().strip()
    if not t:
        raise SystemExit("no APIFY_TOKEN / APIFY_TOKEN_FILE")
    return t


def get(path):
    r = urllib.request.Request("https://api.apify.com/v2" + path, headers={"Authorization": "Bearer " + token()})
    return json.load(urllib.request.urlopen(r, timeout=60))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    a = ap.parse_args()
    run = get(f"/actor-runs/{a.run_id}")["data"]
    build = tuple(int(x) for x in (run.get("buildNumber") or "0.0.0").split("."))
    if run["status"] != "SUCCEEDED" or build < MIN_BUILD:
        raise SystemExit(f"refuse: status={run['status']} build={run.get('buildNumber')} (need SUCCEEDED, >= 0.2.8)")
    ds = get(f"/datasets/{run['defaultDatasetId']}")["data"]
    items = get(f"/datasets/{run['defaultDatasetId']}/items?clean=1&format=json")
    if len(items) != ds["itemCount"]:
        raise SystemExit(f"refuse: fetched {len(items)} rows, dataset itemCount {ds['itemCount']}")
    inp = get(f"/key-value-stores/{run['defaultKeyValueStoreId']}/records/INPUT")
    items.sort(key=lambda i: int(i.get("position") or 0))
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "listings.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(FIELDS)
        for i in items:
            w.writerow([a.run_id if f == "run_id" else i.get(f, "") for f in FIELDS])
    meta = {
        "actor": "publicrecords/etsy-search-scraper",
        "run_id": run["id"], "build_number": run.get("buildNumber"), "build_id": run.get("buildId"),
        "status": run["status"], "started_at": run["startedAt"], "finished_at": run.get("finishedAt"),
        "dataset_id": run["defaultDatasetId"], "dataset_item_count": ds["itemCount"], "rows": len(items),
        "queries": inp.get("queries"), "max_items": inp.get("maxItems"), "sort": inp.get("sort"),
        "proxy_country": (inp.get("proxyConfiguration") or {}).get("apifyProxyCountry"),
        "charged_events": run.get("chargedEventCounts"),
        "usage_usd": round(run.get("usageTotalUsd") or 0, 4),
    }
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
        fh.write("\n")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
