#!/usr/bin/env python3
"""REPORTS-1 (Mark t778u): aggregate the box-only Etsy Search niche reads into data/price-pages/<cut>.json for the
"Typical Etsy prices for <product type>" pages. Aggregates only (counts, quartiles, bands); no listing rows are published.

  python scripts/price_pages_export.py --cut 2026-10-17 [--internal /workspace/x-etsypulse/internal/niche]

A keyword gets a page only if ONE read has >= MIN_LISTINGS listings with a price (no pooling across dates).
Shops in EXCLUDE_SHOPS (our own) are dropped before counting. Reads older than MAX_AGE_DAYS at export are skipped."""
import argparse, csv, datetime as dt, json, os
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
MIN_LISTINGS = 50
MAX_AGE_DAYS = 7
EXCLUDE_SHOPS = {"meldan0282"}


def q(xs, p):
    xs = sorted(xs); k = (len(xs) - 1) * p; f = int(k); c = min(f + 1, len(xs) - 1)
    return round(xs[f] + (xs[c] - xs[f]) * (k - f), 2)


def stats(rs):
    ps = [float(r["price"]) for r in rs if r.get("price")]
    return {"listings": len(ps), "shops": len({r["shop_name"].lower() for r in rs}),
            "price_p25": q(ps, .25), "price_typical": q(ps, .5), "price_p75": q(ps, .75),
            "price_min": min(ps), "price_max": max(ps),
            "bestseller": sum(r["bestseller"] == "True" for r in rs), "star_seller": sum(r["star_seller"] == "True" for r in rs),
            "free_shipping": sum(r["free_shipping"] == "True" for r in rs),
            "etsy_total_results": int(rs[0].get("total_results") or 0),
            "bands": [["under $15", sum(p < 15 for p in ps)], ["$15–30", sum(15 <= p < 30 for p in ps)],
                      ["$30–60", sum(30 <= p < 60 for p in ps)], ["$60 and up", sum(p >= 60 for p in ps)]]}


def read(internal, cut):
    m = json.load(open(os.path.join(ROOT, "data", "niche", cut, "meta.json")))
    rows = [r for r in csv.DictReader(open(os.path.join(internal, cut, "listings.csv"), encoding="utf-8"))
            if r["shop_name"].lower() not in EXCLUDE_SHOPS and r.get("currency") == "$"]
    by = {}
    for r in rows:
        by.setdefault(r["query"], []).append(r)
    return m, by


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cut", required=True)
    ap.add_argument("--internal", default="/workspace/x-etsypulse/internal/niche")
    ap.add_argument("--today", default=dt.date.today().isoformat())
    a = ap.parse_args()
    m, by = read(a.internal, a.cut)
    read_date = m["captured_at"][:10]
    out = {"cut": a.cut, "read_at_utc": m["captured_at"], "read_date": read_date, "run_id": m["run_id"], "actor": m["actor"],
           "region": m.get("region"), "min_listings": MIN_LISTINGS, "max_age_days": MAX_AGE_DAYS, "pages": [], "skipped": [],
           "history": {}}
    cats = {k["keyword"]: k["from_category"] for k in m.get("keywords", [])}
    age = (dt.date.fromisoformat(a.today) - dt.date.fromisoformat(read_date)).days
    for kw, rs in sorted(by.items()):
        s = stats(rs)
        row = {"keyword": kw, "from_category": cats.get(kw, ""), **s}
        if s["listings"] < MIN_LISTINGS:
            out["skipped"].append({"keyword": kw, "why": f"{s['listings']} listings < {MIN_LISTINGS}"})
        elif age > MAX_AGE_DAYS:
            out["skipped"].append({"keyword": kw, "why": f"read {read_date}, more than a week old"})
        else:
            out["pages"].append(row)
    # earlier reads of the same keywords (shown as history, never as current)
    for c in sorted(d for d in os.listdir(a.internal) if d < a.cut):
        try:
            m2, by2 = read(a.internal, c)
        except FileNotFoundError:
            continue
        for kw, rs in by2.items():
            if kw in by:
                s = stats(rs)
                out["history"].setdefault(kw, []).append({"read_date": m2["captured_at"][:10], "run_id": m2["run_id"],
                                                          "listings": s["listings"], "price_typical": s["price_typical"],
                                                          "price_p25": s["price_p25"], "price_p75": s["price_p75"]})
            elif c != a.cut:
                s = stats(rs)
                out["skipped"].append({"keyword": kw, "why": f"last read {m2['captured_at'][:10]}, more than a week old"})
    os.makedirs(os.path.join(ROOT, "data", "price-pages"), exist_ok=True)
    p = os.path.join(ROOT, "data", "price-pages", f"{a.cut}.json")
    json.dump(out, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(p, len(out["pages"]), "pages;", len(out["skipped"]), "skipped")


if __name__ == "__main__":
    main()
