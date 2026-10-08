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
  * list 3 (niche_list, Mark t620u): the same clean pairs summed by Etsy category ("niche"), ranked by total sales added;
    a niche needs >= min_shops clean shops and its biggest shop <= max_top_shop_share of the total. Its own window: the
    shortest preferred window with >= top_n rankable niches.

Public output (repo data/daily-movers/<snapshot_date>/): movers.csv, pct.csv, niches.csv (top_n rows each) and meta.json (window,
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
NICHE_FIELDS = ["rank", "niche", "category", "department", "sales_added", "shops", "sales_per_shop", "top_shop", "top_shop_url",
                "top_shop_added", "top_shop_share", "window_days", "from_date", "to_date"]


def cfg():
    return json.load(open(CFG_PATH, encoding="utf-8"))


def day0(year):
    return dt.date(year, 1, 1)


def valid_rows(snap: dict, state: dict, snapshot_date: str, w: int, C: dict) -> tuple[list, dict]:
    """Every shop with an exact, clean sales-counter pair (snapshot date, snapshot date - w days) + counted exclusions."""
    g = C.get("guards", {})
    end = dt.date.fromisoformat(snapshot_date)
    end_day = (end - day0(end.year)).days
    excl = {s.lower() for s in C.get("exclude_shops", [])}
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
    return rows, why


def niche_name(category: str) -> str:
    """'home & living > home decor > faux plants & greenery' -> 'Faux plants & greenery' (the Etsy category leaf)."""
    leaf_ = category.split(" > ")[-1].strip()
    return leaf_[:1].upper() + leaf_[1:]


def rank_niches(rows: list, C: dict) -> tuple[list, dict]:
    """NICHES (Mark t620u): roll the clean shop pairs of one window up to their Etsy category (the tracker's category
    field). A niche is ranked only with >= min_shops clean shops and when its biggest shop is <= max_top_shop_share of
    the niche's sales added (so one shop's spike is not called a niche trend). Shops without a category are skipped."""
    N = C.get("niche_list", {})
    groups, why = {}, {}
    for r in rows:
        if not r["category"]:
            why["shop_without_category"] = why.get("shop_without_category", 0) + 1
            continue
        groups.setdefault(r["category"], []).append(r)
    out = []
    for cat, rs in groups.items():
        tot = sum(x["sales_added"] for x in rs)
        top = max(rs, key=lambda x: (x["sales_added"], x["sales_total"]))
        if len(rs) < N.get("min_shops", 10):
            why["niche_too_few_shops"] = why.get("niche_too_few_shops", 0) + 1; continue
        if tot <= 0 or top["sales_added"] > N.get("max_top_shop_share", 0.5) * tot:
            why["niche_one_shop_dominates"] = why.get("niche_one_shop_dominates", 0) + 1; continue
        out.append({"niche": niche_name(cat), "category": cat, "department": cat.split(" > ")[0],
                    "sales_added": tot, "shops": len(rs), "sales_per_shop": round(tot / len(rs), 1),
                    "top_shop": top["shop_name"], "top_shop_url": top["shop_url"], "top_shop_added": top["sales_added"],
                    "top_shop_share": round(top["sales_added"] / tot, 3),
                    "window_days": rs[0]["window_days"], "from_date": rs[0]["from_date"], "to_date": rs[0]["to_date"]})
    out.sort(key=lambda x: (-x["sales_added"], -x["shops"], x["niche"].lower()))
    why["niches_ranked"] = len(out)
    return out, why


def compute(snap: dict, state: dict, snapshot_date: str, C: dict | None = None) -> dict:
    C = C or cfg()
    tried, cache = {}, {}
    chosen = None
    for w in C.get("window_days_preferred", [1, 2]):
        rows, why = cache[w] = valid_rows(snap, state, snapshot_date, w, C)
        tried[w] = {"valid": len(rows), "excluded": why}
        if len(rows) >= C.get("min_valid_shops", 500):
            chosen = (w, rows)
            break
    out = {"snapshot_date": snapshot_date, "tried": tried, "window_days": None, "movers": [], "pct": [],
           "niches": [], "niche_window_days": None, "niche_tried": {}}
    # niches: their own shortest window with >= top_n rankable niches (same preferred windows, same clean pairs)
    N = C.get("niche_list", {})
    if N.get("enabled"):
        for w in C.get("window_days_preferred", [1, 2]):
            rows_w = cache[w][0] if w in cache else valid_rows(snap, state, snapshot_date, w, C)[0]
            nl, nwhy = rank_niches(rows_w, C)
            out["niche_tried"][w] = nwhy
            if len(nl) >= N.get("top_n", C.get("top_n", 10)):
                out["niche_window_days"] = w
                out["niche_from_date"] = (dt.date.fromisoformat(snapshot_date) - dt.timedelta(days=w)).isoformat()
                out["niches"] = [{**r, "rank": i} for i, r in enumerate(nl[:N.get("top_n", C.get("top_n", 10))], 1)]
                break
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


def write_csv(path, rows, fields=None):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields or FIELDS, extrasaction="ignore", lineterminator="\n")
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
               "valid": R.get("valid"), "pct_pool": R.get("pct_pool"), "movers": len(R["movers"]), "pct": len(R["pct"]),
               "niche_window_days": R["niche_window_days"], "niche_tried": R["niche_tried"], "niches": len(R["niches"])}
    if a.cmd == "check":
        print(json.dumps(summary, indent=1)); return
    if not R["window_days"] or len(R["movers"]) < cfg().get("top_n", 10):
        print(json.dumps({**summary, "status": "skipped_not_enough_valid_shops"}))
        sys.exit(3)
    d = os.path.join(a.out_root, R["snapshot_date"])
    os.makedirs(d, exist_ok=True)
    write_csv(os.path.join(d, "movers.csv"), R["movers"])
    write_csv(os.path.join(d, "pct.csv"), R["pct"])
    nC = cfg().get("niche_list", {})
    npath = os.path.join(d, "niches.csv")
    if R["niches"]:
        write_csv(npath, R["niches"], NICHE_FIELDS)
    elif os.path.exists(npath):
        os.remove(npath)   # never leave a stale niche list next to a fresh shop list
    meta = {"snapshot_date": R["snapshot_date"], "window_days": R["window_days"], "from_date": R["from_date"],
            "to_date": R["snapshot_date"], "snapshot_sha256": latest.get("sha256"),
            "rows": {"movers": len(R["movers"]), "pct": len(R["pct"]), "niches": len(R["niches"])},
            "pct_min_base_sales": cfg().get("pct_list", {}).get("min_base_sales"),
            "method": (f"Sales added = a shop's public Etsy sales counter on {R['snapshot_date']} minus the same counter "
                       f"{R['window_days']} day(s) earlier, both read exactly on those dates. No scaling. Shops without both "
                       "reads, with rounded counters, a counter that went down, or an implausible jump are left out."),
            **({"niche_window_days": R["niche_window_days"], "niche_from_date": R["niche_from_date"],
                "niche_min_shops": nC.get("min_shops"), "niche_max_top_shop_share": nC.get("max_top_shop_share"),
                "niche_method": (f"Niche = the shop's Etsy category. Sales added in a niche = the sum of sales added by its shops "
                                 f"over the same {R['niche_window_days']}-day exact counter pairs (no scaling). A niche is ranked only "
                                 f"with at least {nC.get('min_shops')} shops with clean reads and when no single shop makes up more "
                                 f"than {round(100 * nC.get('max_top_shop_share', 0.5))}% of its sales added.")} if R["niches"] else {}),
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    json.dump(meta, open(os.path.join(d, "meta.json"), "w", encoding="utf-8"), indent=2)
    os.makedirs(a.internal_root, exist_ok=True)
    json.dump(summary, open(os.path.join(a.internal_root, R["snapshot_date"] + ".json"), "w"), indent=1)
    print(json.dumps({**summary, "status": "ok", "dir": d}))


if __name__ == "__main__":
    main()
