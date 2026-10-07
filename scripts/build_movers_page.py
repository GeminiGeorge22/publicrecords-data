#!/usr/bin/env python3
"""Build the public "Etsy Top Movers" page from the newest CSV in data/top-movers/.

Usage: python scripts/build_movers_page.py [--out _site]

Rank move compares each shop's rank with the newest cut that is at least
7 days older than the current one. If no such cut exists, the column shows
an em dash and the page says it is the first week. Nothing is invented.
"""
import argparse
import csv
import datetime as dt
import glob
import html
import json
import os
import re
import urllib.parse

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DATA = os.path.join(ROOT, "data", "top-movers")
SITE_URL = "https://geminigeorge22.github.io/publicrecords-data/"
ACTOR_STORE_URL = "https://apify.com/publicrecords/etsy-shop-velocity"
ACTOR_ID = "iSqAcbENkn1ZdUMm1"
# Apify Console "try this Actor" deep link (opens the Actor's input form).
RUN_URL = f"https://console.apify.com/actors/{ACTOR_ID}?addFromActorId={ACTOR_ID}"
PREFILL_SHOPS = 3


def load(path):
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if rows and "section" in rows[0]:
        rows = [r for r in rows if r.get("section") == "top20_7d"]
    rows.sort(key=lambda r: int(r["rank"]))
    return rows


def cuts():
    out = []
    for p in glob.glob(os.path.join(DATA, "*.csv")):
        m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\.csv", os.path.basename(p))
        if m:
            out.append((dt.date.fromisoformat(m.group(1)), p))
    return sorted(out)


def build(out_dir):
    all_cuts = cuts()
    if not all_cuts:
        raise SystemExit("no CSV in data/top-movers/")
    cut_date, cur_path = all_cuts[-1]
    rows = load(cur_path)
    prior = [c for c in all_cuts if c[0] <= cut_date - dt.timedelta(days=7)]
    prior_date, prior_ranks = None, None
    if prior:
        prior_date, prior_path = prior[-1]
        prior_ranks = {r["shop_name"].lower(): int(r["rank"]) for r in load(prior_path)}

    def move(r):
        if prior_ranks is None:
            return "—", "no prior week in this series"
        before = prior_ranks.get(r["shop_name"].lower())
        if before is None:
            return "new", f"not in the top 20 on {prior_date}"
        d = before - int(r["rank"])
        if d > 0:
            return f"▲ {d}", f"was #{before} on {prior_date}"
        if d < 0:
            return f"▼ {-d}", f"was #{before} on {prior_date}"
        return "=", f"also #{before} on {prior_date}"

    title = f"Etsy top-selling shops this week — {cut_date.isoformat()}"
    top_names = ", ".join(r["shop_name"] for r in rows[:3])
    desc = (f"The 20 Etsy shops that gained the most sales in the 7 days to {cut_date.isoformat()}, "
            f"with category and rank move. Leaders: {top_names}. Updated weekly.")
    prefill = {"shops": [r["shop_name"] for r in rows[:PREFILL_SHOPS]]}
    prefill_json = json.dumps(prefill)

    trs = []
    for r in rows:
        mv, why = move(r)
        url = r.get("shop_url") or f"https://www.etsy.com/shop/{urllib.parse.quote(r['shop_name'])}"
        trs.append(
            "<tr>"
            f"<td class=\"num\">{int(r['rank'])}</td>"
            f"<td><a href=\"{html.escape(url)}\" rel=\"nofollow noopener\">{html.escape(r['shop_name'])}</a></td>"
            f"<td>{html.escape(r['category'])}</td>"
            f"<td class=\"num\">+{int(float(r['sales_7d_delta'])):,}</td>"
            f"<td class=\"num\" title=\"{html.escape(why)}\">{html.escape(mv)}</td>"
            "</tr>"
        )
    if prior_ranks is None:
        move_note = ("Rank move: this is the first week of the series, so there is no prior week to compare "
                     "against yet (shown as —).")
    else:
        move_note = f"Rank move compares with the {prior_date.isoformat()} list; “new” means the shop was not in that top 20."

    ld = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": title,
        "description": desc,
        "url": SITE_URL,
        "dateModified": cut_date.isoformat(),
        "creator": {"@type": "Organization", "name": "publicrecords"},
        "isAccessibleForFree": True,
    }

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{SITE_URL}">
<meta property="og:type" content="website">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:url" content="{SITE_URL}">
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
<style>
body{{font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;color:#1b1b1b}}
h1{{font-size:1.6rem;margin-bottom:.25rem}}
.sub{{color:#555;margin-top:0}}
table{{border-collapse:collapse;width:100%;margin:1rem 0}}
th,td{{padding:.45rem .6rem;border-bottom:1px solid #e3e3e3;text-align:left;vertical-align:top}}
th{{background:#f6f6f6;font-weight:600}}
.num{{text-align:right;white-space:nowrap}}
a{{color:#0b57d0}}
code{{background:#f3f3f3;padding:.1rem .3rem;border-radius:3px;font-size:.9em}}
footer{{color:#666;font-size:.9rem;border-top:1px solid #e3e3e3;margin-top:2rem;padding-top:1rem}}
</style>
</head>
<body>
<main>
<h1>{html.escape(title)}</h1>
<p class="sub">The 20 Etsy shops with the largest 7-day gain in sales, for the week ending {cut_date.isoformat()}.</p>
<table>
<thead><tr><th class="num">#</th><th>Shop</th><th>Category</th><th class="num">7-day sold delta</th><th class="num">Rank move</th></tr></thead>
<tbody>
{chr(10).join(trs)}
</tbody>
</table>
<p class="sub">{html.escape(move_note)} Where a shop had fewer than 7 days of counter history, its delta is scaled to 7 days.</p>
<p>Track any of these shops yourself: <a href="{html.escape(RUN_URL)}">run the Etsy Shop Sales Tracker on Apify</a> with input <code>{html.escape(prefill_json)}</code>.</p>
</main>
<footer>
Published by publicrecords. Data from the publicrecords Velocity panel cut of {cut_date.isoformat()} (public Etsy shop sales counters).
Not affiliated with, endorsed by, or sponsored by Etsy, Inc. Etsy is a trademark of Etsy, Inc.
</footer>
</body>
</html>
"""
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(page)
    with open(os.path.join(out_dir, "robots.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}sitemap.xml\n")
    with open(os.path.join(out_dir, "sitemap.xml"), "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                 f"  <url><loc>{SITE_URL}</loc><lastmod>{cut_date.isoformat()}</lastmod><changefreq>weekly</changefreq></url>\n"
                 "</urlset>\n")
    open(os.path.join(out_dir, ".nojekyll"), "w").close()
    print(f"built {out_dir}/index.html from {os.path.relpath(cur_path, ROOT)}; prior={prior_date}; title={title}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "_site"))
    build(ap.parse_args().out)
