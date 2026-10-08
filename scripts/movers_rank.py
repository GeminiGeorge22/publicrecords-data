#!/usr/bin/env python3
"""Daily "Etsy's Biggest Movers" (Mark t613u 2026-10-08): top shops by sales added in the shortest window the panel supports.

  python scripts/movers_rank.py export [--snapshot snap.jsonl.gz --state shops.json --latest latest.json] [--out-root DIR]
  python scripts/movers_rank.py check  ...same inputs...   # print counts only, write nothing

Ranking is defined ONLY here, with its knobs in config/movers.json:
  * window: the shortest w in window_days_preferred with >= min_valid_shops shops whose public sales counter was read
    exactly on the snapshot date AND exactly w days earlier (no scaling, no guessing). The panel reads each shop every
    2 days today, so w = 2; 1-day pairs are picked up automatically once they exist.
  * sales added = counter(snapshot date) - counter(snapshot date - w). Excluded, each with a counted reason:
    no read on the snapshot date / no read w days earlier (too little history), non-exact (rounded) counters,
    counter went down (reset / correction), zero, jump > max_jump_ratio x earlier counter (garbage), vintage events,
    counter != snapshot sales_count, duplicates (same shop name, case-insensitive), config exclude_shops.
  * list 1: top_n by sales added (ties: bigger shop first, then name). list 2 (pct_list): sales added as % of the earlier
    counter, shops with >= min_base_sales at the start and >= min_added sales added.

Public output (repo data/daily-movers/<snapshot_date>/): movers.csv, pct.csv (top_n rows each) and meta.json (window,
dates, method; no coverage counts). Box-only counts go to /workspace/x-etsypulse/internal/movers/<snapshot_date>.json.
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
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
CFG_PATH = os.path.join(ROOT, "config", "movers.json")
PUBLIC_ROOT = os.path.join(ROOT, "data", "daily-movers")
INTERNAL_ROOT = os.environ.get("INTERNAL_MOVERS", "/workspace/x-etsypulse/internal/movers")
FIELDS = ["rank", "shop_name", "shop_url", "category", "sales_added", "sales_before", "sales_total", "pct_added",
          "window_days", "from_date", "to_date"]


def cfg():
    return json.load(open(CFG_PATH, encoding="utf-8"))


def day0(year):
    return dt.date(year, 1, 1)


def compute(snap: dict, state: dict, snapshot_date: str, C: dict | None = None) -> dict:
    C = C or cfg()
    g = C.get("guards", {})
    end = dt.date.fromisoformat(snapshot_date)
    end_day = (end - day0(end.year)).days
    excl = {s.lower() for s in C.get("exclude_shops", [])}
    tried = {}
    chosen = None
    for w in C.get("window_days_preferred", [1, 2]):
        rows, why = [], {}

        def drop(k):
            why[k] = why.get(k, 0) + 1

        seen = set()
        for shop, st in state.items():
            reads = [r for r in (st.get("reads") or []) if r[1] is not None]
            last = next((r for r in reversed(reads) if int(r[0]) == end_day), None)
            if last is None:
                drop("no_read_on_snapshot_date"); continue
            prev = next((r for r in reversed(reads) if int(r[0]) == end_day - w), None)
            if prev is None:
                drop(f"no_read_{w}d_earlier"); continue
            s = snap.get(shop) or {}
            if g.get("require_exact_precision", True):
                flags = [r[7] if len(r) > 7 else None for r in (prev, last)]
                if any(f not in (0, None) for f in flags) or s.get("sales_precision") not in (None, "exact"):
                    drop("rounded_counter"); continue
                if any(f is None for f in flags) and (s.get("sales_precision_prev") not in (0, None) or s.get("sales_precision_last") not in (0, None)):
                    drop("rounded_counter"); continue
            added = int(last[1]) - int(prev[1])
            if added < 0:
                drop("counter_went_down"); continue
            if added == 0:
                drop("no_sales_added"); continue
            if prev[1] and added > g.get("max_jump_ratio", 0.5) * prev[1]:
                drop("jump_too_big"); continue
            if g.get("drop_vintage_events", True) and s.get("vintage_event"):
                drop("vintage_event"); continue
            if g.get("require_snapshot_match", True) and s and s.get("sales_count") is not None and int(s["sales_count"]) != int(last[1]):
                drop("snapshot_mismatch"); continue
            key = shop.lower()
            if key in excl:
                drop("excluded_by_config"); continue
            if key in seen:
                drop("duplicate"); continue
            seen.add(key)
            c = s.get("category")
            rows.append({
                "shop": shop,
                "shop_name": s.get("title") or st.get("title") or shop,
                "shop_url": s.get("shop_url") or f"https://www.etsy.com/shop/{shop}",
                "category": html.unescape(c) if c else "",
                "sales_added": added,
                "sales_before": int(prev[1]),
                "sales_total": int(last[1]),
                "pct_added": round(100.0 * added / prev[1], 2) if prev[1] else None,
                "window_days": w,
                "from_date": (end - dt.timedelta(days=w)).isoformat(),
                "to_date": snapshot_date,
            })
        tried[w] = {"valid": len(rows), "excluded": why}
        if len(rows) >= C.get("min_valid_shops", 500):
            chosen = (w, rows)
            break
    out = {"snapshot_date": snapshot_date, "tried": tried, "window_days": None, "movers": [], "pct": []}
    if not chosen:
        return out
    w, rows = chosen
    n = C.get("top_n", 10)
    top = sorted(rows, key=lambda r: (-r["sales_added"], -r["sales_total"], r["shop"].lower()))[:n]
    pc = C.get("pct_list", {})
    pct = []
    if pc.get("enabled"):
        pool = [r for r in rows if r["sales_before"] >= pc.get("min_base_sales", 1000) and r["sales_added"] >= pc.get("min_added", 25)]
        pct = sorted(pool, key=lambda r: (-r["pct_added"], -r["sales_added"], r["shop"].lower()))[:n]
    out.update(window_days=w, from_date=(dt.date.fromisoformat(snapshot_date) - dt.timedelta(days=w)).isoformat(),
               movers=[{**r, "rank": i} for i, r in enumerate(top, 1)],
               pct=[{**r, "rank": i} for i, r in enumerate(pct, 1)],
               pct_pool=len(pct and pool or []), valid=len(rows))
    return out


def load_inputs(a):
    if a.snapshot:
        latest = json.load(open(a.latest))
        blob = open(a.snapshot, "rb").read()
        state = json.load(open(a.state))
    else:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from export_panel_cut import hf_get
        latest = json.loads(hf_get("latest.json"))
        blob = hf_get(latest["path"])
        state = json.loads(hf_get("STATE/shops.json"))
    if latest.get("sha256") and hashlib.sha256(blob).hexdigest() != latest["sha256"]:
        raise SystemExit("snapshot sha256 mismatch vs latest.json")
    snap = {}
    with gzip.GzipFile(fileobj=io.BytesIO(blob)) as f:
        for line in f:
            o = json.loads(line)
            snap[o["shop"]] = o
    return latest, snap, state


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["export", "check"])
    ap.add_argument("--snapshot"); ap.add_argument("--state"); ap.add_argument("--latest")
    ap.add_argument("--out-root", default=PUBLIC_ROOT)
    ap.add_argument("--internal-root", default=INTERNAL_ROOT)
    a = ap.parse_args()
    latest, snap, state = load_inputs(a)
    R = compute(snap, state, latest["snapshot_date"])
    summary = {"snapshot_date": R["snapshot_date"], "window_days": R["window_days"], "tried": R["tried"],
               "valid": R.get("valid"), "pct_pool": R.get("pct_pool"), "movers": len(R["movers"]), "pct": len(R["pct"])}
    if a.cmd == "check":
        print(json.dumps(summary, indent=1)); return
    if not R["window_days"] or len(R["movers"]) < cfg().get("top_n", 10):
        print(json.dumps({**summary, "status": "skipped_not_enough_valid_shops"}))
        sys.exit(3)
    d = os.path.join(a.out_root, R["snapshot_date"])
    os.makedirs(d, exist_ok=True)
    write_csv(os.path.join(d, "movers.csv"), R["movers"])
    write_csv(os.path.join(d, "pct.csv"), R["pct"])
    meta = {"snapshot_date": R["snapshot_date"], "window_days": R["window_days"], "from_date": R["from_date"],
            "to_date": R["snapshot_date"], "snapshot_sha256": latest.get("sha256"),
            "rows": {"movers": len(R["movers"]), "pct": len(R["pct"])},
            "pct_min_base_sales": cfg().get("pct_list", {}).get("min_base_sales"),
            "method": (f"Sales added = a shop's public Etsy sales counter on {R['snapshot_date']} minus the same counter "
                       f"{R['window_days']} day(s) earlier, both read exactly on those dates. No scaling. Shops without both "
                       "reads, with rounded counters, a counter that went down, or an implausible jump are left out."),
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    json.dump(meta, open(os.path.join(d, "meta.json"), "w", encoding="utf-8"), indent=2)
    os.makedirs(a.internal_root, exist_ok=True)
    json.dump(summary, open(os.path.join(a.internal_root, R["snapshot_date"] + ".json"), "w"), indent=1)
    print(json.dumps({**summary, "status": "ok", "dir": d}))


if __name__ == "__main__":
    main()
