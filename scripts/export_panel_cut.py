#!/usr/bin/env python3
"""Export a public report cut from the publicrecords Velocity panel (box-side).

Usage:
  HF_READ_TOKEN=... python scripts/export_panel_cut.py [--cut-date YYYY-MM-DD]
  python scripts/export_panel_cut.py --snapshot snap.jsonl.gz --state shops.json --latest latest.json

Reads the Hugging Face dataset Publicrecords/etsy-shop-velocity (latest.json,
the snapshot it points to, STATE/shops.json) and writes <out-root>/<cut>/:

  movers.csv      top shops (lifetime sales >= 500) by 7-day sales gain
  categories.csv  categories with >= 1 moving shop: shops moving, total and
                  median 7-day gain, shops in the top list, leading shop
  rising.csv      top shops with 500-999 lifetime sales
  meta.json       snapshot date, panel size, counts, method, custom-report readiness

PUBLIC = the repo's data/panel (default out-root): every CSV is cut to PUBLIC_N (10) rows. Free reports show the
top 10 only; the top 50 is what a visitor gets by running the custom report. The full cut (top 50 / 25 / every
category) is written only to a box-only folder (--full-root, default /workspace/x-etsypulse/internal/panel-full)
and is never pushed. Any other --out-root (box-only internal exports) gets the full cut.

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
import hashlib
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
PUBLIC_N = 10            # rows per report in the public repo (t518u: free = top 10, top 50 = custom report)
CUSTOM_N = 50            # what the "run your own report" button asks the builder for
PUBLIC_ROOT = os.path.join(ROOT, "data", "panel")
FULL_ROOT = os.environ.get("INTERNAL_PANEL_FULL", "/workspace/x-etsypulse/internal/panel-full")


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


def coverage_from(state: dict, latest: dict) -> dict:
    """Honest coverage counts, all read from STATE/shops.json at export time.

    A read is [day, sales, ...] where day = days since Jan 1 of the snapshot year (0-based) and sales is the
    public sales counter (None = not readable). A shop has a measured sales figure once it has sales reads on
    two different days; until then it is listed in the panel but has no gain to report.
    """
    year = int(str(latest.get("snapshot_date") or dt.date.today().isoformat())[:4])
    day0 = dt.date(year, 1, 1)
    first_read, second_read = {}, {}
    read_once = measured = measured_7d = 0
    span_max = 0
    for st in state.values():
        days = sorted({r[0] for r in (st.get("reads") or []) if r[1] is not None})
        if not days:
            continue
        read_once += 1
        d1 = int(days[0]); first_read[d1] = first_read.get(d1, 0) + 1
        if len(days) >= 2:
            measured += 1
            d2 = int(days[1]); second_read[d2] = second_read.get(d2, 0) + 1
            span = days[-1] - days[0]
            span_max = max(span_max, span)
            if span >= 7:
                measured_7d += 1
    series, a, b = [], 0, 0
    snap_day = (dt.date.fromisoformat(latest["snapshot_date"]) - day0).days if latest.get("snapshot_date") else None
    lo = min(first_read) if first_read else None
    hi = max([snap_day or 0] + list(first_read) + list(second_read)) if first_read else None
    if lo is not None:
        for d in range(lo, hi + 1):
            a += first_read.get(d, 0); b += second_read.get(d, 0)
            series.append({"date": (day0 + dt.timedelta(days=d)).isoformat(), "read_once": a, "measured": b})
    return {
        "panel_shops": latest.get("panel"),
        "shops_read_once": read_once,
        "shops_measured": measured,
        "shops_measured_7d_span": measured_7d,
        "shops_one_read_only": read_once - measured,
        "measured_span_days_max": span_max,
        "series": series,
        "definition": ("measured = public sales counter read on at least two different days, so a sales gain can "
                       "be computed; read_once = at least one readable sales counter; panel_shops = shops listed "
                       "in the panel (read or not)."),
    }


def tracker_order(rows):
    """Same order the Etsy Shop Sales Tracker returns when no shop names are given (src/filter.js select())."""
    return sorted(rows, key=lambda r: (0 if r.get("breakout") else 1, -(r.get("sales_per_day") if r.get("sales_per_day") is not None else -1),
                                       -(r.get("sales_count") or 0), r.get("shop") or ""))


def custom_readiness(snap: dict, categories: list[str], min_sales: int) -> dict:
    """Can the custom report (Shop Sales Tracker, run by the visitor) rebuild the top 50 of each public report?

    Read from the same snapshot the tracker serves. A report is 'ready' only when the tracker returns the field we
    rank by (delta_7d, else sales_per_day) for enough shops; max_shops is how many rows the tracker must return so
    that the top CUSTOM_N by that field are all inside them (tracker order is breakouts first, then sales_per_day),
    plus a 20% margin for the daily snapshot moving. Nothing here is shown to visitors as a number."""
    base = [r for r in snap.values() if (r.get("sales_count") or -1) >= min_sales]
    n7 = sum(1 for r in base if r.get("delta_7d") is not None)
    field = "delta_7d" if n7 >= CUSTOM_N else "sales_per_day"

    def plan(rows, keep=lambda r: True, need=CUSTOM_N):
        order = tracker_order(rows)
        pos = {r["shop"]: i for i, r in enumerate(order, 1)}
        cand = sorted([r for r in rows if keep(r) and r.get(field) is not None], key=lambda r: -r[field])[:CUSTOM_N]
        deepest = max((pos[r["shop"]] for r in cand), default=0)
        return {"ready": len(cand) >= need, "rows_with_field": len(cand),
                "max_shops": max(CUSTOM_N, int(-(-deepest * 1.2 // 1))) if cand else None}

    out = {"rank_field": field, "n": CUSTOM_N, "min_sales": min_sales,
           "snapshot_rows_with_field": sum(1 for r in base if r.get(field) is not None),
           "movers": plan(base),
           "rising": dict(plan(base, keep=lambda r: (r.get("sales_count") or 0) < RISING_MAX, need=20), max_sales=RISING_MAX - 1),
           "categories": {}}
    for c in categories:
        rows = [r for r in base if r.get("category") and html.unescape(r["category"]) == c]
        if not rows:
            continue
        raw = rows[0]["category"]
        p = plan(rows, need=min(CUSTOM_N, max(10, len(rows))))
        p["tracker_value"] = raw
        out["categories"][c] = p
    return out


def write_csv(path, fields, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cut-date", default=dt.datetime.now(ZoneInfo("America/Toronto")).date().isoformat())
    ap.add_argument("--out-root", default=PUBLIC_ROOT,
                    help="where <cut>/ is written (box-only internal exports use a path outside the repo)")
    ap.add_argument("--full-root", default=FULL_ROOT,
                    help="box-only folder that keeps the full (untrimmed) cut when --out-root is the public repo")
    ap.add_argument("--snapshot"); ap.add_argument("--state"); ap.add_argument("--latest")
    a = ap.parse_args()

    latest = json.loads(open(a.latest).read() if a.latest else hf_get("latest.json"))
    snap_blob = open(a.snapshot, "rb").read() if a.snapshot else hf_get(latest["path"])
    # DAILY-1 completeness: the downloaded file must be the exact snapshot latest.json describes (sha256 of the .gz)
    # and hold every row it claims; a partial or swapped file fails the export instead of publishing wrong data.
    got_sha = hashlib.sha256(snap_blob).hexdigest()
    if latest.get("sha256") and got_sha != latest["sha256"]:
        raise SystemExit(f"snapshot sha256 mismatch: got {got_sha}, latest.json says {latest['sha256']}")
    snap = load_snapshot(snap_blob)
    if latest.get("rows") is not None and len(snap) != int(latest["rows"]):
        raise SystemExit(f"snapshot rows mismatch: file has {len(snap)} shops, latest.json says {latest['rows']}")
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
    top10_names = {m["shop"] for m in top[:PUBLIC_N]}
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
            "shops_in_top10": sum(1 for x in ms if x["shop"] in top10_names),
            "shops_in_top50": sum(1 for x in ms if x["shop"] in top_names),
            "top_shop": ms[0]["shop_name"],
            "top_shop_url": ms[0]["shop_url"],
            "top_shop_7d_delta": ms[0]["sales_7d_delta"],
        })
    crow.sort(key=lambda x: (-x["total_7d_delta"], x["category"]))
    for i, r in enumerate(crow, 1):
        r["rank"] = i

    public = os.path.realpath(a.out_root).startswith(os.path.realpath(ROOT) + os.sep)
    cap = PUBLIC_N if public else None
    mf = ["rank", "shop_name", "shop_url", "category", "sales_7d_delta", "sales_total",
          "gain_pct_of_lifetime", "days_observed"]
    cf_full = ["rank", "category", "department", "shops_moving", "total_7d_delta", "median_7d_delta",
               "shops_in_top10", "shops_in_top50", "top_shop", "top_shop_url", "top_shop_7d_delta"]

    def write_cut(root, n):
        cf = [f for f in cf_full if f != "shops_in_top50"] if n else cf_full
        d = os.path.join(root, a.cut_date)
        os.makedirs(d, exist_ok=True)
        write_csv(os.path.join(d, "movers.csv"), mf, top[:n] if n else top)
        write_csv(os.path.join(d, "rising.csv"), mf, rising[:n] if n else rising)
        write_csv(os.path.join(d, "categories.csv"), cf, crow[:n] if n else crow)
        return d

    out = write_cut(a.out_root, cap)
    full_dir = write_cut(a.full_root, None) if public else out
    meta = {
        "cut_date": a.cut_date,
        "snapshot_date": latest.get("snapshot_date"),
        "source": "Hugging Face Publicrecords/etsy-shop-velocity (latest.json + snapshot + STATE/shops.json)",
        "snapshot_sha256": latest.get("sha256"),
        "panel_shops": latest.get("panel"),
        "snapshot_rows": latest.get("rows"),
        "snapshot_rows_in_file": len(snap),
        "snapshot_built_at": latest.get("built_at"),
        "history_days_max": latest.get("history_days_max"),
        "min_lifetime_sales": MIN_SALES,
        "shops_with_gain_any_size": len(allm),
        "shops_with_gain_ge_min": len(main_m),
        "shops_with_gain_ge_min_known_category": sum(len(v) for v in cats.values()),
        "total_7d_delta_ge_min": sum(m["sales_7d_delta"] for m in main_m),
        "total_7d_delta_ge_min_known_category": sum(m["sales_7d_delta"] for v in cats.values() for m in v),
        "categories": len(crow),
        "scaled_share": round(sum(1 for m in main_m if m["scaled"]) / max(len(main_m), 1), 3),
        "coverage": coverage_from(state, latest),
        "rows": {"movers": len(top[:cap] if cap else top), "rising": len(rising[:cap] if cap else rising),
                 "categories": len(crow[:cap] if cap else crow)},
        "rows_full": {"movers": len(top), "rising": len(rising), "categories": len(crow)},
        "public_max_rows": cap,
        "custom_report": custom_readiness(snap, [r["category"] for r in crow[:PUBLIC_N]], MIN_SALES),
        "method": ("7-day gain = latest public sales counter minus the read 7+ days earlier; when a shop has "
                   "fewer than 7 days of reads, the gain over the observed days is scaled to 7. Shops with "
                   f"lifetime sales >= {MIN_SALES} only."),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    for d in dict.fromkeys([out, full_dir]):
        with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)
            fh.write("\n")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
