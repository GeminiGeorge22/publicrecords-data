#!/usr/bin/env python3
"""Niche snapshot: Etsy search results for keywords taken from the hottest categories (box-side).

  APIFY_TOKEN=... python scripts/niche_snapshot.py run [--cut-date D] [--per-keyword 60]
      starts publicrecords/etsy-search-scraper on the first 5 distinct categories in
      data/panel/<cut>/movers.csv (keyword = leaf category name), 1 page per keyword, waits, then writes data/niche/<cut>/.
  APIFY_TOKEN=... python scripts/niche_snapshot.py fetch --run-id RUN [--cut-date D]
      writes data/niche/<cut>/ from an existing run.

Output: listings.csv (public listing fields, one row per search result),
summary.csv (one row per keyword: price quartiles, price bands, reviews, badge shares),
meta.json (run id, dataset id, Apify usage USD, keywords and where they came from).
Budget guard: maxItems = keywords x per-keyword, maxPages = 1.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import json
import os
import statistics
import time
import urllib.request
from zoneinfo import ZoneInfo

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ACTOR = "JbNpPvG1Z7YtM9onP"  # publicrecords/etsy-search-scraper
API = "https://api.apify.com/v2"
BANDS = [(0, 15, "under $15"), (15, 30, "$15–30"), (30, 60, "$30–60"), (60, 10**9, "$60+")]
LIST_COLS = ["query", "position", "title", "url", "price", "currency", "shop_name", "shop_url", "rating_value",
             "review_count", "bestseller", "star_seller", "popular_now", "etsys_pick", "free_shipping", "total_results"]


def token():
    t = (os.environ.get("APIFY_TOKEN") or "").strip()
    if not t:
        raise SystemExit("APIFY_TOKEN missing")
    return t


def api(path, data=None):
    sep = "&" if "?" in path else "?"
    req = urllib.request.Request(f"{API}{path}{sep}token={token()}",
                                 data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def latest_cut():
    ds = sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "data", "panel", "*")))
    if not ds:
        raise SystemExit("no data/panel cut")
    return ds[-1]


def keywords_for(cut, n=5):
    """Leaf names of the first n distinct categories in Top Movers order (e.g. 'faux plants & greenery' -> 'faux plants')."""
    rows = list(csv.DictReader(open(os.path.join(ROOT, "data", "panel", cut, "movers.csv"), encoding="utf-8")))
    out, seen = [], set()
    for r in rows:
        c = r["category"]
        if c == "unknown" or c in seen:
            continue
        seen.add(c)
        out.append((c.split(" > ")[-1].split(" & ")[0].strip(), c))
        if len(out) >= n:
            break
    return out


def pct(vals, q):
    vals = sorted(vals)
    if not vals:
        return None
    k = (len(vals) - 1) * q
    f = int(k)
    c = min(f + 1, len(vals) - 1)
    return round(vals[f] + (vals[c] - vals[f]) * (k - f), 2)


def write(cut, run, items, kw_map):
    out = os.path.join(ROOT, "data", "niche", cut)
    os.makedirs(out, exist_ok=True)
    items = [i for i in items if i.get("query")]
    with open(os.path.join(out, "listings.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=LIST_COLS, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for i in sorted(items, key=lambda x: (x["query"], x.get("position") or 0)):
            w.writerow(i)
    summ = []
    for q in dict.fromkeys(i["query"] for i in items):
        rows = [i for i in items if i["query"] == q]
        prices = [float(i["price"]) for i in rows if isinstance(i.get("price"), (int, float))]
        revs = [int(i["review_count"]) for i in rows if isinstance(i.get("review_count"), (int, float))]
        n = len(rows)
        r = {
            "keyword": q,
            "from_category": kw_map.get(q, ""),
            "listings": n,
            "etsy_total_results": max((i.get("total_results") or 0) for i in rows) or "",
            "price_p25": pct(prices, .25), "price_median": pct(prices, .5), "price_p75": pct(prices, .75),
            "median_shop_reviews": int(statistics.median(revs)) if revs else "",
            "bestseller_share": round(sum(1 for i in rows if i.get("bestseller")) / n, 3),
            "free_shipping_share": round(sum(1 for i in rows if i.get("free_shipping")) / n, 3),
        }
        for lo, hi, label in BANDS:
            r[f"band {label}"] = sum(1 for p in prices if lo <= p < hi)
        summ.append(r)
    fields = list(summ[0].keys()) if summ else ["keyword"]
    with open(os.path.join(out, "summary.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(summ)
    meta = {
        "cut_date": cut,
        "captured_at": run.get("finishedAt") or run.get("startedAt"),
        "actor": "publicrecords/etsy-search-scraper",
        "run_id": run["id"], "dataset_id": run["defaultDatasetId"], "status": run["status"],
        "usage_usd": round(run.get("usageTotalUsd") or 0, 4),
        "charged_events": run.get("chargedEventCounts"),
        "extra_run_ids": run.get("extra_run_ids", []),
        "keywords": [{"keyword": k, "from_category": v} for k, v in kw_map.items()],
        "rows": {"listings": len(items), "keywords": len(summ)},
        "region": "US (Apify residential proxy), sort=relevance, page 1",
    }
    with open(os.path.join(out, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
        fh.write("\n")
    print(json.dumps(meta, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["run", "fetch"])
    ap.add_argument("--cut-date")
    ap.add_argument("--run-id", nargs="+", help="one or more runs; per keyword the run with the most rows wins")
    ap.add_argument("--per-keyword", type=int, default=60)
    a = ap.parse_args()
    cut = a.cut_date or latest_cut()
    kws = keywords_for(cut)
    kw_map = {k: c for k, c in kws}
    if a.mode == "run":
        inp = {"queries": [k for k, _ in kws], "maxPages": 1, "maxItems": a.per_keyword * len(kws),
               "fillLazyCards": True, "sort": "relevance", "source": "etsypulse-site",
               "proxyConfiguration": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"],
                                      "apifyProxyCountry": "US"}}
        run = api(f"/acts/{ACTOR}/runs?timeout=900&memory=2048", inp)["data"]
        print("started", run["id"])
        while run["status"] in ("READY", "RUNNING"):
            time.sleep(15)
            run = api(f"/actor-runs/{run['id']}")["data"]
        items = api(f"/datasets/{run['defaultDatasetId']}/items?clean=1&limit=5000")
        runs = [run]
    else:
        cats = [r["category"] for r in csv.DictReader(
            open(os.path.join(ROOT, "data", "panel", cut, "categories.csv"), encoding="utf-8"))]
        kw_map, best, runs = {}, {}, []
        for rid in a.run_id:
            r = api(f"/actor-runs/{rid}")["data"]
            runs.append(r)
            inp = api(f"/key-value-stores/{r['defaultKeyValueStoreId']}/records/INPUT")
            for q in inp.get("queries") or []:
                kw_map.setdefault(q, next((c for c in cats if c.split(" > ")[-1].startswith(q)), ""))
            got = api(f"/datasets/{r['defaultDatasetId']}/items?clean=1&limit=5000")
            byq = {}
            for i in got:
                byq.setdefault(i.get("query"), []).append(i)
            for q, rows in byq.items():
                if len(rows) > len(best.get(q, [])):
                    best[q] = rows
        items = [i for q in kw_map for i in best.get(q, [])]
        run = dict(runs[0])
        run["usageTotalUsd"] = sum(x.get("usageTotalUsd") or 0 for x in runs)
        run["extra_run_ids"] = [x["id"] for x in runs[1:]]
        ce = {}
        for x in runs:
            for k, v in (x.get("chargedEventCounts") or {}).items():
                ce[k] = ce.get(k, 0) + v
        run["chargedEventCounts"] = ce
        run["finishedAt"] = max(x.get("finishedAt") or "" for x in runs)
    write(cut, run, items, kw_map)


if __name__ == "__main__":
    main()
