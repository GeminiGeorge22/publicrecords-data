#!/usr/bin/env python3
"""REPORTS-2 (Mark t778u): "Etsy shops gaining sales in <niche>" from ONE balanced snapshot pair.

  python scripts/sales_niches_export.py --snapshot 2026-10-17 [--hf /workspace/hf-velocity]

Refuses unless manifest_<snapshot>.json says balanced=true. Pairs: a shop read exactly on the snapshot date AND exactly one day
earlier (as_of in snapshot_<d-1> and snapshot_<d>), both counters exact, earlier counter > 0, counter not down, jump <= 50% of the
earlier counter, no vintage event, not our own shop. Niche = a word rule on the shop's own Etsy headline (the Etsy category is known
for too few shops). A niche gets a page only with >= MIN_SHOPS shops holding a clean pair. Public file: totals + top 10 per niche."""
import argparse, datetime as dt, gzip, json, os, re
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
MIN_SHOPS = 200
TOP_N = 10
EXCLUDE_SHOPS = {"meldan0282"}
# slug, page phrase, headline rule (case-insensitive regex), plain-English rule shown on the page
NICHES = [
    ("jewelry", "jewelry", r"\bjewel(?:le)?ry\b|\bjewellery\b", "“jewelry” or “jewellery”"),
    ("digital-downloads", "digital downloads and printables", r"\bdigital\b|\bprintables?\b|\bdownloads?\b", "“digital”, “printable(s)” or “download(s)”"),
    ("t-shirts-apparel", "t-shirts and apparel", r"\bt-?shirts?\b|\btees?\b|\bapparel\b|\bclothing\b", "“t-shirt(s)”, “tee(s)”, “apparel” or “clothing”"),
    ("home-decor", "home decor", r"\bhome decor\b|\bdecor\b", "“decor” (including “home decor”)"),
    ("art-prints", "art prints", r"\bart prints?\b|\bprints\b", "“prints” or “art print”"),
    ("3d-printing", "3D printing", r"\b3d\b", "“3D”"),
    ("stickers", "stickers", r"\bstickers?\b", "“sticker(s)”"),
    ("embroidery", "embroidery", r"\bembroider\w*", "“embroidery”, “embroidered” or similar"),
]
ALSO_CHECKED = [("wood", r"\bwood\w*"), ("wedding", r"\bwedding\w*|\bbridal\b"), ("kids", r"\bkids?\b|\bchildren\b|\btoys?\b"),
                ("leather", r"\bleather\b"), ("fabric and sewing", r"\bfabric\b|\bsewing\b|\bquilt\w*"), ("patterns", r"\bpatterns?\b"),
                ("ceramics and pottery", r"\bceramics?\b|\bpottery\b"), ("pets", r"\bpets?\b|\bdogs?\b|\bcats?\b"), ("crochet", r"\bcrochet\w*"),
                ("svg and cut files", r"\bsvg\b|cut files?"), ("craft supplies", r"\bsupplies\b|\bcraft supply\b"),
                ("bags", r"\bbags?\b|\bpurses?\b|\btotes?\b"), ("witchy and spiritual", r"\bwitch\w*|\bcrystals?\b|\btarot\b"),
                ("silver", r"\bsilver\b|\bsterling\b"), ("baby", r"\bbaby\b|\bnewborn\b"), ("planners", r"\bplanners?\b"),
                ("candles", r"\bcandles?\b"), ("knitting and yarn", r"\bknit\w*|\byarn\b"), ("miniatures", r"\bminiatures?\b|\bdollhouse\b"),
                ("beads", r"\bbeads?\b"), ("earrings", r"\bearrings?\b"), ("necklaces", r"\bnecklaces?\b"), ("rings", r"\brings\b"),
                ("christmas", r"\bchristmas\b"), ("soap and skincare", r"\bsoaps?\b|\bskin ?care\b"), ("halloween", r"\bhalloween\b")]


def load(hf, d):
    out = {}
    with gzip.open(os.path.join(hf, f"snapshot_{d}.jsonl.gz"), "rt") as f:
        for line in f:
            o = json.loads(line); out[o["shop"]] = o
    return out


def pairs(hf, snap):
    prev = (dt.date.fromisoformat(snap) - dt.timedelta(days=1)).isoformat()
    a, b = load(hf, prev), load(hf, snap)
    rows, why = [], {}
    for shop, o in b.items():
        def drop(k):
            why[k] = why.get(k, 0) + 1
        p = a.get(shop)
        if o.get("as_of") != snap or not p or p.get("as_of") != prev:
            drop("no_read_on_both_dates"); continue
        if o.get("sales_precision") != "exact" or p.get("sales_precision") != "exact":
            drop("rounded_counter"); continue
        s0, s1 = p.get("sales_count"), o.get("sales_count")
        if s0 is None or s1 is None or s0 <= 0:
            drop("no_prior_count"); continue
        d = s1 - s0
        if d < 0:
            drop("counter_went_down"); continue
        if d > 0.5 * s0:
            drop("jump_too_big"); continue
        if o.get("vintage_event"):
            drop("vintage_event"); continue
        if shop.lower() in EXCLUDE_SHOPS:
            drop("own_shop_excluded"); continue
        rows.append({"shop": o.get("title") or shop, "shop_url": o.get("shop_url") or f"https://www.etsy.com/shop/{shop}",
                     "headline": o.get("headline") or "", "sales_before": s0, "sales_total": s1, "sales_added": d})
    return prev, rows, why, len(b)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--snapshot", required=True); ap.add_argument("--hf", default="/workspace/hf-velocity")
    a = ap.parse_args()
    man = json.load(open(os.path.join(a.hf, f"manifest_{a.snapshot}.json")))
    if man.get("balanced") is not True:
        raise SystemExit(f"manifest_{a.snapshot}: balanced={man.get('balanced')} -> held, no page")
    prev, rows, why, snap_rows = pairs(a.hf, a.snapshot)
    out = {"snapshot_date": a.snapshot, "from_date": prev, "window_days": 1, "balanced": True,
           "manifest_sha256": man.get("sha256"), "snapshot_rows": snap_rows, "clean_pairs": len(rows),
           "clean_pairs_gaining": sum(r["sales_added"] > 0 for r in rows), "excluded": why, "min_shops": MIN_SHOPS,
           "rule": "headline words", "pages": [], "skipped": []}
    for slug, phrase, rx, rule in NICHES:
        m = [r for r in rows if re.search(rx, r["headline"], re.I)]
        g = sorted((r for r in m if r["sales_added"] > 0), key=lambda r: (-r["sales_added"], -r["sales_total"], r["shop"].lower()))
        tot = sum(r["sales_added"] for r in g)
        if len(m) < MIN_SHOPS:
            out["skipped"].append({"niche": phrase, "shops": len(m), "why": f"{len(m)} shops < {MIN_SHOPS}"}); continue
        top = [{**{k: r[k] for k in ("shop", "shop_url", "sales_before", "sales_total", "sales_added")},
                "headline": r["headline"][:90], "rank": i} for i, r in enumerate(g[:TOP_N], 1)]
        names = [t["shop"].lower() for t in top]
        assert len(set(names)) == len(names), f"duplicate shop label in {slug}"
        out["pages"].append({"slug": slug, "niche": phrase, "rule": rule, "regex": rx, "shops": len(m), "shops_gaining": len(g),
                             "sales_added": tot, "top_shop_share": round(g[0]["sales_added"] / tot, 3) if tot else None,
                             "top10_share": round(sum(t["sales_added"] for t in top) / tot, 3) if tot else None, "top": top})
    for phrase, rx in ALSO_CHECKED:
        n = sum(1 for r in rows if re.search(rx, r["headline"], re.I))
        out["skipped"].append({"niche": phrase, "shops": n, "why": (f"{n} shops < {MIN_SHOPS}" if n < MIN_SHOPS else "meets the threshold; not built in this batch")})
    d = os.path.join(ROOT, "data", "sales-niches"); os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{a.snapshot}.json")
    json.dump(out, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(p, len(rows), "pairs;", [(x["niche"], x["shops"], x["shops_gaining"], x["sales_added"], x["top_shop_share"]) for x in out["pages"]])


if __name__ == "__main__":
    main()
