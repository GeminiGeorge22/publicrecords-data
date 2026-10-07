#!/usr/bin/env python3
"""Export a public report cut from the publicrecords Velocity panel (box-side).

Usage:
  HF_READ_TOKEN=... python scripts/export_panel_cut.py [--cut-date YYYY-MM-DD]
  python scripts/export_panel_cut.py --snapshot snap.jsonl.gz --state shops.json --latest latest.json

Reads the Hugging Face dataset Publicrecords/etsy-shop-velocity (latest.json,
the snapshot it points to, STATE/shops.json) and writes data/panel/<cut>/:

  movers.csv      top 50 shops (lifetime sales >= 500) by 7-day sales gain
  categories.csv  every category with >= 1 moving shop: shops moving, total and
                  median 7-day gain, shops in the top 50, leading shop
  rising.csv      top 25 shops with 500-999 lifetime sales... see MIN_RISING
  meta.json       snapshot date, panel size, counts, method

Delta method is the same as fleet ops/etsy_top_movers.py (TM-1): the latest sales
read minus the read 7+ days earlier; if the shop has fewer than 7 days of reads,
the gain over the observed span is scaled to 7 days. Only positive gains count.
Nothing here is estimated beyond that scaling, and the scaling is disclosed.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import html
import io
import json
import os
import statistics
import urllib.request
from zoneinfo import ZoneInfo

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HF_BASE = "https://huggingface.co/datasets/Publicrecords/etsy-shop-velocity/resolve/main"
MIN_SALES = 500          # main movers / categories floor (same as TM-1)
RISING_MAX = 1000        # "rising" = lifetime sales below this
TOP_N = 50
RISING_N = 25


def hf_get(path: str) -> bytes:
    tok = (os.environ.get("HF_READ_TOKEN") or os.environ.get("HF_TOKEN") or "").strip()
    if not tok:
        raise SystemExit("HF_READ_TOKEN missing (or pass --snapshot/--state/--latest)")
    req = urllib.request.Request(f"{HF_BASE}/{path}", headers={"Authorization": f"Bearer {tok}",
                                                               "User-Agent": "etsypulse-export"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def load_snapshot(blob: bytes) -> dict:
    out = {}
    with gzip.GzipFile(fileobj=io.BytesIO(blob)) as f:
        for line in f:
            o = json.loads(line)
            out[o["shop"]] = o
    return out


def movers_from(snap: dict, state: dict, min_sales: int) -> list[dict]:
    movers = []
    for shop, st in state.items():
        s = snap.get(shop)
        if not s:
            continue
        total = s.get("sales_count")
        if total is None or total < min_sales:
            continue
        reads = [r for r in (st.get("reads") or []) if r[1] is not None]
        if len(reads) < 2:
            continue
        last = reads[-1]
        cand = None
        for r in reads[:-1]:
            if r[0] <= last[0] - 7:
                cand = r
        back7 = cand is not None
        if cand is None:
            cand = reads[0]
        span = last[0] - cand[0]
        if span <= 0:
            continue
        raw = last[1] - cand[1]
        if raw <= 0:
            continue
        d7 = raw if (back7 and span >= 7) else int(round(raw * 7.0 / span))
        c = s.get("category")
        movers.append({
            "shop": shop,
            "shop_name": s.get("title") or shop,
            "shop_url": s.get("shop_url") or f"https://www.etsy.com/shop/{shop}",
            "category": html.unescape(c) if c else "unknown",
            "sales_7d_delta": d7,
            "sales_total": total,
            "days_observed": span,
            "scaled": not (back7 and span >= 7),
        })
    movers.sort(key=lambda x: (-x["sales_7d_delta"], -x["sales_total"], x["shop"]))
    return movers


def write_csv(path, fields, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cut-date", default=dt.datetime.now(ZoneInfo("America/Toronto")).date().isoformat())
    ap.add_argument("--out-root", default=os.path.join(ROOT, "data", "panel"),
                    help="where <cut>/ is written (box-only internal exports use a path outside the repo)")
    ap.add_argument("--snapshot"); ap.add_argument("--state"); ap.add_argument("--latest")
    a = ap.parse_args()

    latest = json.loads(open(a.latest).read() if a.latest else hf_get("latest.json"))
    snap_blob = open(a.snapshot, "rb").read() if a.snapshot else hf_get(latest["path"])
    snap = load_snapshot(snap_blob)
    state = json.loads(open(a.state).read() if a.state else hf_get("STATE/shops.json"))

    allm = movers_from(snap, state, 0)
    main_m = [m for m in allm if m["sales_total"] >= MIN_SALES]
    top = [{**m, "rank": i} for i, m in enumerate(main_m[:TOP_N], 1)]
    for m in top:
        m["gain_pct_of_lifetime"] = round(100.0 * m["sales_7d_delta"] / m["sales_total"], 2)
    rising = [m for m in main_m if m["sales_total"] < RISING_MAX][:RISING_N]
    rising = [{**m, "rank": i, "gain_pct_of_lifetime": round(100.0 * m["sales_7d_delta"] / m["sales_total"], 2)}
              for i, m in enumerate(rising, 1)]

    top_names = {m["shop"] for m in top}
    cats: dict[str, list] = {}
    for m in main_m:
        if m["category"] != "unknown":
            cats.setdefault(m["category"], []).append(m)
    crow = []
    for c, ms in cats.items():
        ms.sort(key=lambda x: -x["sales_7d_delta"])
        crow.append({
            "category": c,
            "department": c.split(" > ")[0],
            "shops_moving": len(ms),
            "total_7d_delta": sum(x["sales_7d_delta"] for x in ms),
            "median_7d_delta": int(statistics.median(x["sales_7d_delta"] for x in ms)),
            "shops_in_top50": sum(1 for x in ms if x["shop"] in top_names),
            "top_shop": ms[0]["shop_name"],
            "top_shop_url": ms[0]["shop_url"],
            "top_shop_7d_delta": ms[0]["sales_7d_delta"],
        })
    crow.sort(key=lambda x: (-x["total_7d_delta"], x["category"]))
    for i, r in enumerate(crow, 1):
        r["rank"] = i

    out = os.path.join(a.out_root, a.cut_date)
    os.makedirs(out, exist_ok=True)
    mf = ["rank", "shop_name", "shop_url", "category", "sales_7d_delta", "sales_total",
          "gain_pct_of_lifetime", "days_observed"]
    write_csv(os.path.join(out, "movers.csv"), mf, top)
    write_csv(os.path.join(out, "rising.csv"), mf, rising)
    write_csv(os.path.join(out, "categories.csv"),
              ["rank", "category", "department", "shops_moving", "total_7d_delta", "median_7d_delta",
               "shops_in_top50", "top_shop", "top_shop_url", "top_shop_7d_delta"], crow)
    meta = {
        "cut_date": a.cut_date,
        "snapshot_date": latest.get("snapshot_date"),
        "source": "Hugging Face Publicrecords/etsy-shop-velocity (latest.json + snapshot + STATE/shops.json)",
        "snapshot_sha256": latest.get("sha256"),
        "panel_shops": latest.get("panel"),
        "snapshot_rows": latest.get("rows"),
        "history_days_max": latest.get("history_days_max"),
        "min_lifetime_sales": MIN_SALES,
        "shops_with_gain_any_size": len(allm),
        "shops_with_gain_ge_min": len(main_m),
        "shops_with_gain_ge_min_known_category": sum(len(v) for v in cats.values()),
        "total_7d_delta_ge_min": sum(m["sales_7d_delta"] for m in main_m),
        "categories": len(crow),
        "scaled_share": round(sum(1 for m in main_m if m["scaled"]) / max(len(main_m), 1), 3),
        "rows": {"movers": len(top), "rising": len(rising), "categories": len(crow)},
        "method": ("7-day gain = latest public sales counter minus the read 7+ days earlier; when a shop has "
                   "fewer than 7 days of reads, the gain over the observed days is scaled to 7. Shops with "
                   f"lifetime sales >= {MIN_SALES} only."),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    with open(os.path.join(out, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
        fh.write("\n")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
