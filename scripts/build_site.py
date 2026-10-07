#!/usr/bin/env python3
"""Build the Etsy Pulse static site from the data in this repo.

Usage: python scripts/build_site.py [--out _site]

Inputs (all committed in the repo, nothing fetched at build time):
  data/panel/<cut>/{movers,categories,rising}.csv + meta.json   (scripts/export_panel_cut.py)
  data/niche/<cut>/{summary,listings}.csv + meta.json            (scripts/niche_snapshot.py)
Reports: Overview, Top Movers, Hot Categories, Rising Shops, Niche Prices, and
Breakouts (only when an older panel cut exists to compare with).
Every number on the page is read from those files; the "what this means" bullets
are templated from the same rows. Nothing is invented.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import html
import json
import os
import shutil
import statistics

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SITE_URL = "https://geminigeorge22.github.io/publicrecords-data/"
CTA_URL = "https://publicrecords-redirect.publicrecords.workers.dev/r/site-cta"
TRACKER_URL = "https://publicrecords-redirect.publicrecords.workers.dev/r/site-tracker"
R = "https://publicrecords-redirect.publicrecords.workers.dev/r/"
X_URL = "https://x.com/EtsyPulse"
ORANGE = "#FD5E02"
PUBLIC_N = 10   # t518u: free reports show the top 10 only; the top 50 is the visitor's own custom report
CUSTOM_N = 50
E = html.escape


# ---------------------------------------------------------------- data
def read_csv(p):
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def cuts(kind):
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "data", kind, "20*"))
                  if os.path.isdir(p))


def load_panel(cut):
    d = os.path.join(ROOT, "data", "panel", cut)
    out = {"cut": cut, "meta": json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))}
    for k in ("movers", "categories", "rising"):
        rows = read_csv(os.path.join(d, f"{k}.csv"))
        for r in rows:
            for f in ("rank", "sales_7d_delta", "sales_total", "days_observed", "shops_moving",
                      "total_7d_delta", "median_7d_delta", "shops_in_top50", "top_shop_7d_delta"):
                if r.get(f) not in (None, ""):
                    r[f] = int(float(r[f]))
            if r.get("gain_pct_of_lifetime") not in (None, ""):
                r["gain_pct_of_lifetime"] = float(r["gain_pct_of_lifetime"])
        out[k] = rows[:PUBLIC_N]
    return out


def load_niche(cut):
    d = os.path.join(ROOT, "data", "niche", cut)
    if not os.path.exists(os.path.join(d, "summary.csv")):
        return None
    rows = read_csv(os.path.join(d, "summary.csv"))
    for r in rows:
        for k, v in list(r.items()):
            if k in ("keyword", "from_category"):
                continue
            try:
                r[k] = float(v) if v not in ("", None) else None
            except ValueError:
                pass
    return {"cut": cut, "meta": json.load(open(os.path.join(d, "meta.json"), encoding="utf-8")), "rows": rows}


# ---------------------------------------------------------------- helpers
def leaf(cat):
    s = cat.split(" > ")[-1]
    return s[:1].upper() + s[1:]


def dept(cat):
    s = cat.split(" > ")[0]
    return s[:1].upper() + s[1:]


def n(x):
    return f"{int(x):,}"


def plus(x):
    return f"+{int(x):,}"


def money(x):
    return "—" if x is None else (f"${x:,.0f}" if x >= 10 else f"${x:,.2f}")


def pct(x, d=0):
    return f"{x * 100:.{d}f}%"


def nice_date(iso):
    d = dt.date.fromisoformat(iso)
    return d.strftime("%b %-d, %Y")


def share_word(k, total):
    return f"{k} of the top {total}"


# ---------------------------------------------------------------- insights
def movers_insights(P):
    m, meta = P["movers"], P["meta"]
    out = []
    top10 = m[:10]
    by = {}
    for r in top10:
        by.setdefault(r["category"], []).append(r)
    cat, rows = max(by.items(), key=lambda kv: (len(kv[1]), sum(x["sales_7d_delta"] for x in kv[1])))
    if len(rows) >= 2:
        out.append(f"<b>{E(leaf(cat))}</b> hold {len(rows)} of the top 10, "
                   f"<b>{plus(sum(x['sales_7d_delta'] for x in rows))}</b> sales combined in 7 days.")
    a, b = m[0], m[1]
    out.append(f"#1 <b>{E(a['shop_name'])}</b> added <b>{plus(a['sales_7d_delta'])}</b> sales, "
               f"{a['sales_7d_delta'] / b['sales_7d_delta']:.1f}× the #2 shop ({E(b['shop_name'])}, {plus(b['sales_7d_delta'])}).")
    small = max(m[:PUBLIC_N], key=lambda r: r["gain_pct_of_lifetime"])
    out.append(f"Size isn't the whole story: <b>{E(small['shop_name'])}</b> has {n(small['sales_total'])} lifetime sales "
               f"and added {plus(small['sales_7d_delta'])} this week, <b>{small['gain_pct_of_lifetime']:.1f}%</b> of everything "
               f"it has ever sold.")
    t10 = sum(r["sales_7d_delta"] for r in top10)
    tot = meta["total_7d_delta_ge_min"]
    out.append(f"The top 10 shops took <b>{pct(t10 / tot)}</b> of all 7-day gains we measured "
               f"({plus(t10)} of {plus(tot)} across {n(meta['shops_with_gain_ge_min'])} shops). Momentum is concentrated.")
    d = {}
    for r in m:
        d[dept(r["category"])] = d.get(dept(r["category"]), 0) + 1
    d.pop("Unknown", None)
    if d:
        k, v = max(d.items(), key=lambda kv: kv[1])
        out.append(f"<b>{E(k)}</b> is the busiest department: {v} of the top {len(m)} movers.")
    return out


def category_insights(P):
    c, meta = P["categories"], P["meta"]
    out = []
    a = c[0]
    out.append(f"<b>{E(leaf(a['category']))}</b> lead: {a['shops_moving']} shops gaining, <b>{plus(a['total_7d_delta'])}</b> "
               f"combined. The leader, {E(a['top_shop'])}, is {pct(a['top_shop_7d_delta'] / a['total_7d_delta'])} of that.")
    broad = max(c, key=lambda r: (r["shops_moving"], r["total_7d_delta"]))
    if broad is not a:
        out.append(f"Broadest demand: <b>{E(leaf(broad['category']))}</b> have the most shops gaining "
                   f"({broad['shops_moving']}), so it's not one shop carrying it. A typical shop there added about {plus(broad['median_7d_delta'])} sales this week.")
    big = [r for r in c if r["shops_moving"] >= 10]
    if big:
        med = max(big, key=lambda r: r["median_7d_delta"])
        out.append(f"Best typical shop: in <b>{E(leaf(med['category']))}</b> a typical growing shop added about "
                   f"<b>{plus(med['median_7d_delta'])}</b> sales this week (categories with 10+ growing shops).")
    t3 = sum(r["total_7d_delta"] for r in c[:3])
    tot = meta["total_7d_delta_ge_min"]
    out.append(f"The top 3 categories account for <b>{pct(t3 / tot)}</b> of all the 7-day gains we measured "
               f"({n(meta['categories'])} categories had shops gaining).")
    conc = [r for r in c if r["shops_moving"] >= 5]
    if conc:
        top = max(conc, key=lambda r: r["top_shop_7d_delta"] / r["total_7d_delta"])
        out.append(f"Most top-heavy: <b>{E(leaf(top['category']))}</b>. {E(top['top_shop'])} alone is "
                   f"{pct(top['top_shop_7d_delta'] / top['total_7d_delta'])} of the category's gain. One shop drives most of it.")
    return out


def rising_insights(P):
    r = P["rising"]
    if not r:
        return []
    out = []
    a = r[0]
    out.append(f"<b>{E(a['shop_name'])}</b> ({n(a['sales_total'])} lifetime sales) added <b>{plus(a['sales_7d_delta'])}</b> "
               f"in a week, {a['gain_pct_of_lifetime']:.1f}% of its lifetime total.")
    cnt = {}
    for x in r:
        if x["category"] != "unknown":
            cnt[x["category"]] = cnt.get(x["category"], 0) + 1
    if cnt:
        k, v = max(cnt.items(), key=lambda kv: kv[1])
        if v >= 2:
            out.append(f"<b>{E(leaf(k))}</b> show up {v} times in this list of {len(r)}: the most of any category here.")
    med = statistics.median(x["sales_7d_delta"] for x in r)
    out.append(f"A typical shop in this list added about <b>{plus(med)}</b> sales this week, about {med / 7:.0f} a day.")
    top10 = sum(x["sales_7d_delta"] for x in r[:10])
    out.append(f"The top 10 small shops added {plus(top10)} sales between them in 7 days.")
    return out


def niche_insights(N):
    rows = [r for r in N["rows"] if (r.get("listings") or 0) >= 20]
    out = []
    if not rows:
        return out
    for r in rows[:3]:
        bands = {k[5:]: v for k, v in r.items() if k.startswith("band ")}
        bk, bv = max(bands.items(), key=lambda kv: kv[1] or 0)
        out.append(f"<b>“{E(r['keyword'])}”</b>: typical price {money(r['price_median'])}; most charge "
                   f"{money(r['price_p25'])}–{money(r['price_p75'])}. Most crowded price range: {E(bk)} "
                   f"({int(bv)} of the top {int(r['listings'])} results).")
    hi = max(rows, key=lambda r: r["bestseller_share"])
    lo = min(rows, key=lambda r: r["bestseller_share"])
    if hi is not lo:
        out.append(f"Bestseller badges: <b>{pct(hi['bestseller_share'])}</b> of the top <b>{E(hi['keyword'])}</b> results have one "
                   f"vs {pct(lo['bestseller_share'])} for {E(lo['keyword'])}. Fewer badges can mean the top spots are easier to win.")
    fs = max(rows, key=lambda r: r["free_shipping_share"])
    out.append(f"Free shipping is most common in <b>{E(fs['keyword'])}</b>: {pct(fs['free_shipping_share'])} of the top results offer it.")
    return out


def breakout_rows(cur, prev):
    pr = {r["shop_name"].lower(): r["rank"] for r in prev["movers"]}
    new, jumps = [], []
    for r in cur["movers"]:
        b = pr.get(r["shop_name"].lower())
        if b is None:
            new.append(r)
        elif b - r["rank"] > 0:
            jumps.append({**r, "was": b, "jump": b - r["rank"]})
    jumps.sort(key=lambda r: -r["jump"])
    return new, jumps


# ---------------------------------------------------------------- html pieces
CSS = """
:root{--o:#FD5E02;--o2:#ff8a3d;--bg:#fafaf9;--card:#fff;--ink:#17171a;--mut:#62626b;--line:#ececee;--chip:#f4f4f5;--link:#c2410c;--bar:#ffe3d1}
@media (prefers-color-scheme:dark){:root{--bg:#0e0e10;--card:#17171b;--ink:#f4f4f5;--mut:#a1a1aa;--line:#26262b;--chip:#222227;--link:#ff9a5c;--bar:#3a2416}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Inter,sans-serif}
a{color:var(--link);text-decoration:none}a:hover{text-decoration:underline}
.wrap{max-width:1080px;margin:0 auto;padding:0 16px}
.top{position:sticky;top:0;z-index:10;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:saturate(1.4) blur(10px);border-bottom:1px solid var(--line)}
.top .wrap{display:flex;align-items:center;gap:12px;height:56px}
.brand{display:flex;align-items:center;gap:10px;font-weight:800;color:var(--ink);letter-spacing:-.01em;font-size:17px;white-space:nowrap}
.brand img{width:30px;height:30px;border-radius:8px}
.brand:hover{text-decoration:none}
.top .x{margin-left:auto;font-size:14px;font-weight:600;white-space:nowrap}
nav.tabs{border-bottom:1px solid var(--line);background:var(--bg)}
nav.tabs .wrap{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;padding-top:8px;padding-bottom:8px}
nav.tabs .wrap::-webkit-scrollbar{display:none}
nav.tabs a{flex:0 0 auto;padding:7px 13px;border-radius:999px;background:var(--chip);color:var(--ink);font-size:14px;font-weight:600}
nav.tabs a.on{background:var(--o);color:#fff}
nav.tabs a:hover{text-decoration:none}
.hero{position:relative;overflow:hidden;background:linear-gradient(120deg,#FD5E02 0%,#ff7a1f 55%,#e64a00 100%);color:#fff}
.hero svg.pulse{position:absolute;left:0;right:0;bottom:8px;width:100%;height:90px;opacity:.35}
.hero .wrap{position:relative;padding-top:34px;padding-bottom:40px}
.eyebrow{font-size:13px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;opacity:.9}
.hero h1{font-size:clamp(28px,6.4vw,46px);line-height:1.08;margin:8px 0 10px;letter-spacing:-.025em;font-weight:850}
.hero p.lede{font-size:clamp(16px,2.6vw,19px);margin:0;max-width:680px;opacity:.95}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.chips b{font-weight:800}
.hero .cov{margin:12px 0 0;font-size:13.5px;line-height:1.5;opacity:.95;max-width:760px}
.chips span{background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.28);border-radius:999px;padding:4px 11px;font-size:13px;font-weight:600}
.kpis{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:14px;position:relative}
@media(min-width:760px){.kpis{grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px 14px 12px;box-shadow:0 6px 24px rgba(0,0,0,.06)}
.kpi .v{overflow-wrap:anywhere;font-size:clamp(22px,5.4vw,30px);font-weight:850;letter-spacing:-.02em;line-height:1.1;color:var(--o)}
.kpi .l{font-size:13px;color:var(--mut);margin-top:4px;line-height:1.3}
section{margin:28px 0}
h2{font-size:clamp(21px,4.4vw,27px);letter-spacing:-.02em;margin:0 0 6px;font-weight:800}
.sub{color:var(--mut);margin:0 0 14px;font-size:15px}
.insights{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--o);border-radius:14px;padding:14px 16px 6px}
.insights h3{margin:0 0 6px;font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--o)}
.insights ul{margin:0;padding-left:18px}.insights li{margin:0 0 9px}
.grid{display:grid;grid-template-columns:minmax(0,1fr);gap:12px}
@media(min-width:760px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
.rcard{display:block;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px;color:var(--ink);transition:transform .12s,border-color .12s}
.rcard:hover{text-decoration:none;border-color:var(--o);transform:translateY(-2px)}
.rcard .t{font-weight:800;font-size:18px;display:flex;justify-content:space-between;gap:8px}
.rcard .t span{color:var(--o)}
.rcard .d{color:var(--mut);font-size:14px;margin:2px 0 10px}
.mini{list-style:none;margin:0;padding:0}
.mini li{display:flex;justify-content:space-between;gap:10px;padding:6px 0;border-top:1px solid var(--line);font-size:15px}
.mini li b{font-variant-numeric:tabular-nums;color:var(--o);white-space:nowrap}
.mini li .nm{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* table-cards: cards on mobile, aligned rows on desktop */
.tc{display:grid;gap:10px}
.tc .hd{display:none}
.row{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px;display:grid;grid-template-columns:34px 1fr auto;grid-template-areas:"rk nm big" "rk meta meta" "rk bar bar";column-gap:10px;row-gap:4px;align-items:center}
.row .rk{grid-area:rk;align-self:start;font-weight:800;color:var(--mut);font-variant-numeric:tabular-nums;font-size:15px;padding-top:2px}
.row .nm{grid-area:nm;font-weight:700;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:16px}
.row .big{grid-area:big;font-weight:850;font-size:20px;color:var(--o);font-variant-numeric:tabular-nums;white-space:nowrap;letter-spacing:-.01em}
.row .meta{grid-area:meta;display:flex;flex-wrap:wrap;gap:6px 12px;font-size:13px;color:var(--mut)}
.row .meta .c{background:var(--chip);color:var(--ink);border-radius:999px;padding:1px 9px;font-weight:600}
.row .meta em{font-style:normal}
.row .meta b{color:var(--ink);font-weight:700;font-variant-numeric:tabular-nums}
.row .bar{grid-area:bar;height:6px;border-radius:6px;background:var(--line);overflow:hidden;margin-top:4px}
.row .bar i{display:block;height:100%;background:linear-gradient(90deg,var(--o),var(--o2));border-radius:6px}
.row.top3{border-color:color-mix(in srgb,var(--o) 45%,var(--line))}
.row.top3 .rk{color:var(--o)}
@media(min-width:900px){
 .tc{gap:0;border:1px solid var(--line);border-radius:16px;overflow:hidden;background:var(--card)}
 .tc .hd,.tc .row{display:grid;grid-template-columns:var(--cols);grid-template-areas:none;align-items:center;column-gap:14px;padding:10px 16px;border:0;border-radius:0}
 .tc .hd{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);font-weight:700;background:var(--chip)}
 .tc .row{border-top:1px solid var(--line)}
 .tc .row>*{grid-area:auto}
 .row .meta{display:contents}
 .row .meta>span{font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
 .row .meta>span:not(.c):not(.ld){text-align:right}
 .row .meta em{display:none}
 .row .meta .c{justify-self:start;max-width:100%}
 .row .big{font-size:18px;text-align:right}
 .row .bar{margin:0}
 .tc .hd .r{text-align:right}
}
.dl{display:inline-flex;align-items:center;gap:8px;margin-top:14px;font-weight:700;font-size:15px;background:var(--chip);color:var(--ink);padding:9px 14px;border-radius:10px}
.dl:hover{text-decoration:none;background:var(--line)}
.note{font-size:13px;color:var(--mut);margin-top:10px}
.cta{margin:36px 0;border-radius:20px;background:#17171a;color:#fff;padding:26px 20px;position:relative;overflow:hidden}
@media (prefers-color-scheme:dark){.cta{background:#1d1d22;border:1px solid var(--line)}}
.cta h2{color:#fff}.cta p{color:#d4d4d8;margin:6px 0 16px;max-width:640px}
.fresh{margin:16px 0 0;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px;font-size:15px}
.fresh a{font-weight:800;white-space:nowrap}
.fresh .snap{margin-top:6px;font-size:13px;color:var(--mut);font-variant-numeric:tabular-nums}
.fresh .snap b{color:var(--ink)}
.hcta{margin-top:18px;display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px}
.hbtn{display:inline-flex;align-items:center;gap:8px;background:#fff;color:#c2410c;font-weight:850;font-size:17px;padding:14px 20px;border-radius:14px;box-shadow:0 8px 24px rgba(80,20,0,.28);letter-spacing:-.01em}
.hbtn:hover{text-decoration:none;transform:translateY(-1px)}
.hcta small{font-size:13px;opacity:.92;font-weight:600;max-width:300px;line-height:1.35}
@media(max-width:480px){.hbtn{width:100%;justify-content:center}}
.rbtn{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:10px;margin:14px 0 0;background:var(--card);border:1.5px solid var(--o);border-radius:14px;padding:12px 14px}
.rbtn span{font-size:14px;color:var(--mut);flex:1 1 220px}
.rbtn a{background:var(--o);color:#fff;font-weight:800;padding:10px 16px;border-radius:10px;white-space:nowrap}
.rbtn a:hover{text-decoration:none;filter:brightness(1.06)}
.more50{border-style:dashed}
.more50 span b{color:var(--ink)}
.nc .more{display:block;margin-top:10px;font-weight:800;font-size:14px}
.btn{display:inline-block;background:var(--o);color:#fff;font-weight:800;padding:13px 20px;border-radius:12px;font-size:16px}
.btn:hover{text-decoration:none;filter:brightness(1.06)}
.btn.ghost{background:transparent;border:1px solid #52525b;margin-left:8px;color:#fff}
.cta .disc{font-size:12.5px;color:#a1a1aa;margin-top:14px}
.niche{display:grid;grid-template-columns:minmax(0,1fr);gap:12px}
@media(min-width:760px){.niche{grid-template-columns:repeat(2,minmax(0,1fr))}}
.nc{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px}
.nc h3{margin:0;font-size:19px;letter-spacing:-.01em}
.nc .from{font-size:13px;color:var(--mut);margin-bottom:10px}
.nc .stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px}
.nc .stats div{background:var(--chip);border-radius:10px;padding:8px}
.nc .stats b{display:block;font-size:19px;font-weight:850;color:var(--o);font-variant-numeric:tabular-nums}
.nc .stats span{font-size:12px;color:var(--mut)}
.bands{display:flex;height:26px;border-radius:8px;overflow:hidden;font-size:11px;font-weight:700;color:#fff}
.bands i{display:flex;align-items:center;justify-content:center;font-style:normal;min-width:0;overflow:hidden;white-space:nowrap}
.legend{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12px;color:var(--mut);margin:6px 0 10px}
.legend i{display:inline-block;width:9px;height:9px;border-radius:3px;margin-right:4px;vertical-align:-1px}
.facts{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:13px;color:var(--mut)}.facts b{color:var(--ink)}
footer{border-top:1px solid var(--line);margin-top:30px;padding:22px 0 40px;color:var(--mut);font-size:13.5px}
footer p{margin:0 0 8px}
.method{font-size:14px;color:var(--mut)}
.method h3{color:var(--ink);font-size:16px;margin:16px 0 4px}
"""

PULSE_SVG = ('<svg class="pulse" viewBox="0 0 1200 90" preserveAspectRatio="none" aria-hidden="true">'
             '<polyline fill="none" stroke="#fff" stroke-width="3" stroke-linejoin="round" '
             'points="0,60 380,60 395,70 410,20 425,82 440,60 520,60 535,12 552,84 568,60 650,60 666,8 684,86 700,60 '
             '780,60 860,60 930,30 950,38 1040,6 1200,6"/></svg>')

BAND_COLORS = ["#ffb27a", "#ff8a3d", "#FD5E02", "#b83f00"]

BUILDER = "run.html"
RUN_FALLBACK = R + "site-run"
NAV = [("index.html", "Overview"), ("ai.html", "✦ AI"), ("run.html", "★ Custom report"), ("movers.html", "Top Movers"), ("categories.html", "Hot Categories"),
       ("rising.html", "Rising Shops"), ("breakouts.html", "Breakouts"), ("niche.html", "Niche Prices")]


def page(name, title, desc, body, ctx, hero=None, scripts=""):
    nav = "".join(f'<a href="{h}"{" class=on" if h == name else ""}>{t}</a>' for h, t in NAV if h in ctx["pages"])
    url = SITE_URL + ("" if name == "index.html" else name)
    og = SITE_URL + "og.png?v=" + ctx["cut"]
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{url}">
<meta name="theme-color" content="{ORANGE}">
<link rel="icon" href="assets/favicon.ico" sizes="any"><link rel="icon" type="image/png" sizes="32x32" href="assets/favicon-32.png">
<link rel="apple-touch-icon" href="assets/apple-touch-icon.png">
<meta property="og:type" content="website"><meta property="og:site_name" content="Etsy Pulse">
<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}">
<meta property="og:url" content="{url}"><meta property="og:image" content="{og}">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:site" content="@EtsyPulse">
<meta name="twitter:title" content="{E(title)}"><meta name="twitter:description" content="{E(desc)}">
<meta name="twitter:image" content="{og}">
<script type="application/ld+json">{json.dumps(ctx["ld"], ensure_ascii=False)}</script>
<style>{CSS}</style>
<link rel="stylesheet" href="assets/builder.css?v={ctx['cut']}-b1">
</head><body>
<header class="top"><div class="wrap"><a class="brand" href="index.html"><img src="assets/logo-96.png" alt="" width="30" height="30">Etsy Pulse</a>
<a class="x" href="{X_URL}" rel="noopener">Follow @EtsyPulse</a></div></header>
<nav class="tabs" aria-label="Reports"><div class="wrap">{nav}</div></nav>
{hero or ""}
<main class="wrap">
{body}
{"" if name == BUILDER else cta(ctx)}
</main>
<footer><div class="wrap">
<p><b>Etsy Pulse</b> is published by publicrecords, and the data comes from our own tools: the publicrecords Etsy Shop Sales Tracker panel
(public shop sales counters) and the publicrecords Etsy Search Scraper on Apify. We built them and we sell them, so weigh the links accordingly.</p>
<p>Movers cut {E(ctx['cut'])} (counters read through {E(ctx['snap'])}). Not affiliated with, endorsed by, or sponsored by Etsy, Inc.
Etsy is a trademark of Etsy, Inc.</p>
</div></footer>
{scripts}
</body></html>
"""


def cta(ctx):
    return f"""<section class="cta">
<h2>Run this on any niche</h2>
<p>Every number here comes from public Etsy data our tools collect. Build the same report for your own keyword or your
competitors' shops, right here: charts, plain-English takeaways and a spreadsheet in a few minutes. No code, no API keys.</p>
<a class="btn" href="{BUILDER}?type=niche&amp;from=cta">Build a niche report</a><a class="btn ghost" href="{BUILDER}?type=rivals&amp;from=cta">Compare competitor shops</a>
<div class="disc">Runs our tools (publicrecords on Apify) on your own Apify account after a free sign-in. Pay per result; Apify's free plan includes $5 of usage a month.</div>
</section>"""


def hero_cta():
    return (f'<form class="qform" action="{BUILDER}" method="get" role="search">'
            '<input name="q" type="search" placeholder="Type a niche, e.g. ceramic mug" aria-label="Your Etsy niche or keyword" enterkeyhint="go" autocomplete="off">'
            '<input type="hidden" name="from" value="hero"><button type="submit">Build my report →</button></form>'
            '<div class="qsub">Live Etsy data on your keyword: prices, Bestseller badges, top shops, spreadsheet. Free Apify sign-in, no code, '
            f'pay per result. <a href="{RUN_FALLBACK}" rel="noopener">Or open it on Apify</a></div>')


REPORT_TYPE = {"site-movers": "velocity", "site-categories": "category", "site-rising": "category", "site-niche": "niche"}


def report_btn(slug, actor_label, text):
    return (f'<div class="rbtn"><span>{text}</span>'
            f'<a href="{BUILDER}?type={REPORT_TYPE.get(slug, "niche")}&amp;from={slug}">Run this report yourself →</a></div>'
            f'<p class="note" style="margin-top:6px">Builds it right here with our {actor_label}: free Apify sign-in, no code, pay per result.</p>')


def q(params):
    from urllib.parse import urlencode
    return BUILDER + "?" + html.escape(urlencode(params, doseq=True))


def custom_links(meta):
    """Builder links that rebuild the top 50 of each shop report (Shop Sales Tracker on the visitor's account).
    Settings come from meta.json["custom_report"], computed at export time from the snapshot the tracker serves."""
    cr = meta.get("custom_report") or {}
    field, ms = cr.get("rank_field", "sales_per_day"), cr.get("min_sales", meta.get("min_lifetime_sales", 500))

    def base(part, src, extra=None):
        p = [("type", "category")] + (extra or []) + [("f-minsales", ms), ("f-maxshops", part.get("max_shops") or CUSTOM_N),
                                                       ("rank", field), ("dir", "top"), ("n", CUSTOM_N)]
        return p + [("from", src)]

    mv, rs = cr.get("movers") or {}, cr.get("rising") or {}
    out = {"movers": {"ready": bool(mv.get("ready")), "url": q(base(mv, "site-movers-top50", [("category", "")]))},
           "rising": {"ready": bool(rs.get("ready")),
                      "url": q(base(rs, "site-rising-top50", [("category", "")]) + [("filter", f"sales_count:<=:{rs.get('max_sales', 999)}")])},
           "categories": {}}
    for cat, part in (cr.get("categories") or {}).items():
        out["categories"][cat] = {"ready": bool(part.get("ready")),
                                  "url": q(base(part, "site-categories-top50", [("category", part["tracker_value"])]))}
    return out


def niche_link(keyword=None, src="site-niche-top50"):
    p = [("type", "niche")] + ([("q", keyword)] if keyword else []) + [("f-perkw", CUSTOM_N), ("f-sort", "relevance"),
                                                                       ("f-region", "US"), ("f-fill", 1), ("from", src)]
    return q(p)


def more50(link, what="", ready=True, src="site"):
    if ready:
        return (f'<div class="rbtn more50"><span><b>Want the top {CUSTOM_N}{what}, or a different niche?</b> This free list stops at '
                f'{PUBLIC_N}. Your own report opens with everything already set up: sign in with Apify and press Run.</span>'
                f'<a href="{link}">Run your own report →</a></div>')
    return (f'<div class="rbtn more50"><span><b>Want the top {CUSTOM_N}?</b> This free list stops at {PUBLIC_N}. A custom top-{CUSTOM_N} '
            f'run of this report isn\'t ready yet, because our Shop Sales Tracker doesn\'t return weekly sales gains yet. '
            f'You can run a live report on any niche today.</span>'
            f'<a href="{niche_link(src=src + "-top50-niche")}">Run a niche report →</a></div>')


def publish_cfg():
    try:
        return json.load(open(os.path.join(ROOT, "config", "publish.json"), encoding="utf-8"))
    except FileNotFoundError:
        return {"cadence_days": 7, "publish_weekday": "Mon"}


def next_refresh(cut):
    c = publish_cfg()
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    d = dt.date.fromisoformat(cut) + dt.timedelta(days=max(c["cadence_days"] - 3, 1))
    while days[d.weekday()] != c["publish_weekday"]:
        d += dt.timedelta(days=1)
    return d


def cadence_word():
    n = publish_cfg()["cadence_days"]
    return "weekly" if n == 7 else ("every 2 weeks" if n == 14 else f"every {n} days")


def cov_of(meta):
    """Coverage numbers from meta.json (written by export_panel_cut.py at publish time). Never hardcoded."""
    c = dict(meta.get("coverage") or {})
    c.setdefault("panel_shops", meta.get("panel_shops"))
    c.setdefault("shops_read_once", meta.get("snapshot_rows"))
    c.setdefault("shops_measured", None)
    c.setdefault("series", [])
    c["gaining"] = meta.get("shops_with_gain_any_size")
    c["ranked"] = meta.get("shops_with_gain_ge_min")
    return c


def growth_phrase(series, key):
    """'up from M on <date>' using the most recent earlier date whose value differs; None if no change on record."""
    if not series:
        return None
    v = series[-1][key]
    for row in reversed(series[:-1]):
        if row[key] != v:
            word = "up" if v > row[key] else "down"
            return f"{word} from {n(row[key])} on {nice_date(row['date'])}"
    return None


def coverage_line(meta):
    c = cov_of(meta)
    if c.get("shops_measured") is None:
        return ""
    s = c["series"]
    gm, gr = growth_phrase(s, "measured"), growth_phrase(s, "read_once")
    asof = nice_date(s[-1]["date"]) if s else nice_date(meta["snapshot_date"])
    out = (f"<b>{n(c['shops_measured'])}</b> shops have a measured sales figure (sales counter read on 2+ days) as of {asof}"
           + (f", {gm}" if gm else "") + ". "
           f"<b>{n(c['shops_one_read_only'])}</b> more have been read once so far and need a second read before they get one"
           + (f" (shops read at least once: {n(c['shops_read_once'])}, {gr})" if gr else "") + ". "
           f"The panel lists {n(c['panel_shops'])} shops in total.")
    return out


def coverage_short(meta):
    c = cov_of(meta)
    if c.get("shops_measured") is None:
        return ""
    gm = growth_phrase(c["series"], "measured")
    asof = nice_date(c["series"][-1]["date"]) if c["series"] else nice_date(meta["snapshot_date"])
    return (f"Shops with a measured sales figure: <b>{n(c['shops_measured'])}</b> as of {asof}" + (f", {gm}" if gm else "") + ". "
            f"Another {n(c['shops_one_read_only'])} have one read so far and need a second before they get a figure.")


def fresh_box(snapshot_label, rows_label, cut):
    return (f'<div class="fresh"><div><b>Free reports refresh {cadence_word()}.</b> Want current Etsy data for your own niche or shops? '
            f'<a href="{BUILDER}?from=fresh">Run a report →</a></div>'
            f'<div class="snap">Snapshot <b>{E(snapshot_label)}</b> · <b>{E(rows_label)}</b> · next free refresh '
            f'{next_refresh(cut).strftime("%a %b %-d")}</div></div>')


def insights_block(items, title="What this means for sellers"):
    if not items:
        return ""
    lis = "".join(f"<li>{x}</li>" for x in items)
    return f'<div class="insights"><h3>{title}</h3><ul>{lis}</ul></div>'


def shop_rows(rows, maxv, cols_label, extra=None):
    hd = ('<div class="hd" role="row"><span>#</span><span>Shop</span><span>Category</span>'
          '<span class="r">Lifetime</span><span class="r">Week vs lifetime</span><span>Momentum</span>'
          '<span class="r">7-day sales</span></div>')
    out = [hd]
    for r in rows:
        w = max(2, round(100 * r["sales_7d_delta"] / maxv)) if maxv else 0
        cat = "Unknown" if r["category"] == "unknown" else leaf(r["category"])
        days = r.get("days_observed")
        title = f"{r['category']}; measured over {days} days, scaled to 7" if days and days < 7 else r["category"]
        cls = "row top3" if r["rank"] <= 3 else "row"
        out.append(
            f'<div class="{cls}" role="row"><span class="rk">{r["rank"]}</span>'
            f'<a class="nm" href="{E(r["shop_url"])}" rel="nofollow noopener">{E(r["shop_name"])}</a>'
            f'<span class="meta"><span class="c" title="{E(title)}">{E(cat)}</span>'
            f'<span><b>{n(r["sales_total"])}</b><em> lifetime</em></span>'
            f'<span><em>week = </em><b>{r["gain_pct_of_lifetime"]:.1f}%</b><em> of lifetime</em></span></span>'
            f'<span class="bar"><i style="width:{w}%"></i></span>'
            f'<span class="big">{plus(r["sales_7d_delta"])}</span></div>')
    cols = "34px minmax(150px,1.3fr) minmax(140px,1.2fr) 90px 120px minmax(80px,.8fr) 90px"
    return f'<div class="tc" role="table" style="--cols:{cols}">{"".join(out)}</div>'


def fix_desktop_order():
    # desktop: rank | name | category | lifetime | pct | bar | big  -> handled by DOM order + display:contents
    return ""


def cat_rows(rows):
    maxv = rows[0]["total_7d_delta"] if rows else 1
    hd = ('<div class="hd" role="row"><span>#</span><span>Category</span><span>Department</span>'
          '<span class="r">Shops gaining</span><span class="r">Typical shop</span><span>Leader</span>'
          '<span class="r">7-day sales</span></div>')
    out = [hd]
    for r in rows:
        w = max(2, round(100 * r["total_7d_delta"] / maxv))
        cls = "row top3" if r["rank"] <= 3 else "row"
        out.append(
            f'<div class="{cls}" role="row"><span class="rk">{r["rank"]}</span>'
            f'<span class="nm" title="{E(r["category"])}">{E(leaf(r["category"]))}</span>'
            f'<span class="meta"><span class="c">{E(dept(r["category"]))}</span>'
            f'<span><b>{r["shops_moving"]}</b><em> shops gaining</em></span>'
            f'<span><em>typical shop </em><b>{plus(r["median_7d_delta"])}</b></span>'
            f'<span class="ld"><em>leader </em><a href="{E(r["top_shop_url"])}" rel="nofollow noopener">{E(r["top_shop"])}</a> '
            f'<b>{plus(r["top_shop_7d_delta"])}</b></span></span>'
            f'<span class="big">{plus(r["total_7d_delta"])}</span></div>')
    cols = "34px minmax(160px,1.4fr) 130px 120px 110px minmax(180px,1.4fr) 90px"
    return f'<div class="tc cat" role="table" style="--cols:{cols}">{"".join(out)}</div>'


PLAIN_HEADERS = {"price_median": "typical_price", "price_p25": "most_charge_from", "price_p75": "most_charge_to",
                 "median_shop_reviews": "typical_shop_reviews", "median_7d_delta": "typical_shop_gain_7d",
                 "listings": "top_results_checked"}


def write_public_csv(path, rows):
    """Public download: same rows, headers in plain words (no 'median' / 'p25' jargon)."""
    if not rows:
        open(path, "w").write("")
        return
    fields = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow([PLAIN_HEADERS.get(f, f) for f in fields])
        for r in rows:
            w.writerow([r.get(f, "") for f in fields])


def dl(href, label):
    return f'<a class="dl" href="{href}" download>⬇ {label}</a>'


# ---------------------------------------------------------------- og image
def og_image(out_dir, P):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Pillow missing: og.png skipped")
        return False
    font_path = os.path.join(ROOT, "scripts", "fonts", "Inter.ttf")

    def F(size, weight="Bold"):
        f = ImageFont.truetype(font_path, size)
        try:
            f.set_variation_by_name(weight)
        except Exception:
            pass
        return f

    W, H = 1200, 630
    im = Image.new("RGB", (W, H), ORANGE)
    d = ImageDraw.Draw(im)
    for x in range(W):  # subtle gradient
        t = x / W
        d.line([(x, 0), (x, H)], fill=(253, int(94 + 28 * (1 - abs(t - .5) * 2)), int(2 + 20 * (1 - t))))
    pts = [(0, 552), (400, 552), (418, 566), (438, 522), (458, 586), (476, 552), (600, 552), (620, 518),
           (642, 588), (660, 552), (820, 552), (930, 540), (950, 546), (1090, 524)]
    d.line(pts, fill=(255, 255, 255), width=5, joint="curve")
    d.polygon([(1088, 512), (1124, 520), (1094, 540)], fill="white")
    logo = Image.open(os.path.join(ROOT, "assets", "icon-192.png")).resize((84, 84))
    mask = Image.new("L", (84, 84), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, 84, 84], 18, fill=255)
    ring = Image.new("RGB", (92, 92), "white")
    rmask = Image.new("L", (92, 92), 0)
    ImageDraw.Draw(rmask).rounded_rectangle([0, 0, 92, 92], 22, fill=255)
    im.paste(ring, (60, 52), rmask)
    im.paste(logo, (64, 56), mask)
    d.text((172, 62), "Etsy Pulse", font=F(46, "ExtraBold"), fill="white")
    d.text((174, 116), f"Week to {nice_date(P['meta']['snapshot_date'])}", font=F(26, "Medium"), fill=(255, 236, 222))
    d.text((60, 176), "Top Etsy shops by 7-day sales gain", font=F(54, "ExtraBold"), fill="white")
    y = 262
    for r in P["movers"][:3]:
        d.rounded_rectangle([60, y, 1140, y + 72], 16, fill=(255, 255, 255))
        d.text((84, y + 16), f"#{r['rank']}", font=F(34, "ExtraBold"), fill=ORANGE)
        name = r["shop_name"] if len(r["shop_name"]) <= 24 else r["shop_name"][:23] + "…"
        d.text((160, y + 16), name, font=F(34, "Bold"), fill=(23, 23, 26))
        cat = leaf(r["category"])[:28]
        nb = d.textbbox((0, 0), name, font=F(34, "Bold"))[2]
        d.text((176 + nb, y + 24), cat, font=F(24, "Medium"), fill=(113, 113, 122))
        val = f"+{r['sales_7d_delta']:,}"
        vw = d.textbbox((0, 0), val, font=F(38, "ExtraBold"))[2]
        d.text((1116 - vw, y + 13), val, font=F(38, "ExtraBold"), fill=ORANGE)
        y += 86
    cvo = cov_of(P["meta"])
    if cvo.get("shops_measured") is not None:
        d.text((60, 560), f"Among {cvo['shops_measured']:,} measured shops (of {cvo['panel_shops']:,} in our panel) · gains scaled to 7 days",
               font=F(22, "Medium"), fill=(255, 236, 222))
    d.text((60, 596), "data by publicrecords (our tool) · not affiliated with Etsy", font=F(22, "Medium"),
           fill=(255, 236, 222))
    im.save(os.path.join(out_dir, "og.png"), optimize=True)
    return True


# ---------------------------------------------------------------- AI page (ai.html): Apify MCP server with our two Actors preselected
# Sources (checked 2026-10-07): docs.apify.com/platform/integrations/mcp (URL + ?tools= selection, OAuth sign-in),
# docs.apify.com/platform/integrations/claude-desktop (custom connector; direct "Add custom connector" dialog link),
# docs.apify.com/platform/integrations/chatgpt (Developer mode -> Create app, OAuth), mcp.apify.com configurator
# (Cursor cursor:// and VS Code vscode:mcp/install buttons, ?tools= and ?client= prefill), cursor.com/docs/context/mcp/install-links.
MCP_TOOLS = "publicrecords/etsy-search-scraper,publicrecords/etsy-shop-velocity"
MCP_URL = "https://mcp.apify.com?tools=" + MCP_TOOLS
MCP_SETUP = "https://mcp.apify.com/?tools=" + MCP_TOOLS          # Apify's own setup page, our tools preselected
CLAUDE_ADD = "https://claude.ai/new?modal=add-custom-connector#settings/customize-connectors"
CHATGPT_SETTINGS = "https://chatgpt.com/#settings/Connectors"
TINY_RUN = "https://tinyurl.com/etsypulse-run"


def mcp_links():
    import base64
    from urllib.parse import quote
    cur = "cursor://anysphere.cursor-deeplink/mcp/install?name=etsy-pulse&config=" + quote(
        base64.b64encode(json.dumps({"url": MCP_URL}, separators=(",", ":")).encode()).decode())
    vsc = "vscode:mcp/install?" + quote(json.dumps({"name": "etsy-pulse", "url": MCP_URL}, separators=(",", ":")))
    return {"cursor": cur, "vscode": vsc}


AI_CSS = """
.aih .wrap{display:grid;gap:22px;align-items:center}
@media(min-width:900px){.aih .wrap{grid-template-columns:1fr 1.05fr}}
.aih video,.aih img.poster{width:100%;height:auto;border-radius:16px;box-shadow:0 16px 40px rgba(70,15,0,.35);display:block;background:#ff7a1f}
.steps3{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0 0;padding:0;list-style:none;counter-reset:s}
.steps3 li{counter-increment:s;background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.3);border-radius:999px;padding:6px 13px 6px 6px;font-weight:700;font-size:14.5px;display:flex;align-items:center;gap:8px}
.steps3 li:before{content:counter(s);background:#fff;color:#c2410c;border-radius:50%;width:24px;height:24px;display:inline-flex;align-items:center;justify-content:center;font-weight:850;font-size:13px}
.apps{display:grid;grid-template-columns:minmax(0,1fr);gap:12px}
@media(min-width:760px){.apps{grid-template-columns:repeat(2,minmax(0,1fr))}}
.app{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px}
.app h3{margin:0 0 4px;font-size:19px}.app p{margin:4px 0 10px;color:var(--mut);font-size:14.5px}
.app ol{margin:6px 0 0;padding-left:20px;font-size:14.5px;color:var(--mut)}.app ol li{margin:0 0 4px}.app ol b{color:var(--ink)}
.app .acts{display:flex;flex-wrap:wrap;gap:8px}
.abtn{display:inline-flex;align-items:center;gap:6px;background:var(--o);color:#fff;font-weight:800;padding:10px 15px;border-radius:10px;font-size:15px;border:0;cursor:pointer;font-family:inherit}
.abtn:hover{text-decoration:none;filter:brightness(1.06)}
.abtn.ghost{background:var(--chip);color:var(--ink)}
.urlbox{display:flex;gap:8px;align-items:stretch;margin:12px 0 0;background:var(--card);border:1.5px solid var(--o);border-radius:12px;padding:6px 6px 6px 12px}
.urlbox code{flex:1;min-width:0;overflow-x:auto;white-space:nowrap;font-size:13.5px;align-self:center;scrollbar-width:thin}
.uses{display:grid;grid-template-columns:minmax(0,1fr);gap:12px}
@media(min-width:700px){.uses{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(min-width:1000px){.uses{grid-template-columns:repeat(3,minmax(0,1fr))}}
.use{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px}
.use h3{margin:0 0 4px;font-size:17px}.use p{margin:0 0 10px;color:var(--mut);font-size:14px}
.use q{display:block;background:var(--chip);border-radius:12px 12px 12px 4px;padding:10px 12px;font-size:14.5px;quotes:none;font-weight:600}
.use .f{margin-top:8px;font-size:12.5px;color:var(--mut)}
.convo{display:grid;gap:10px;max-width:760px}
.convo .u{justify-self:end;background:var(--o);color:#fff;font-weight:700;border-radius:16px 16px 4px 16px;padding:10px 14px;max-width:90%}
.convo .b{justify-self:start;background:var(--card);border:1px solid var(--line);border-radius:16px 16px 16px 4px;padding:12px 14px;max-width:96%;font-size:15px}
.convo .b ul{margin:6px 0 0;padding-left:18px}.convo .b li{margin:0 0 3px}
.convo .t{font-size:12.5px;color:var(--mut)}
.costs{display:grid;grid-template-columns:minmax(0,1fr);gap:10px}
@media(min-width:760px){.costs{grid-template-columns:repeat(3,minmax(0,1fr))}}
.costs div{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}
.costs b{display:block;font-size:16px;margin-bottom:4px}.costs p{margin:0;color:var(--mut);font-size:14px}
.try{background:var(--card);border:1px dashed var(--line);border-radius:14px;padding:14px 16px;font-size:14.5px}
.try ul{margin:6px 0 0;padding-left:18px}
"""

AI_JS = """<script>
document.querySelectorAll('[data-copy]').forEach(function(b){b.addEventListener('click',function(){
var t=b.getAttribute('data-copy'),o=b.textContent;function ok(){b.textContent='Copied ✓';setTimeout(function(){b.textContent=o},1600)}
if(navigator.clipboard){navigator.clipboard.writeText(t).then(ok,function(){prompt('Copy this link:',t)})}else{prompt('Copy this link:',t)}
try{navigator.sendBeacon&&navigator.sendBeacon('https://publicrecords-redirect.publicrecords.workers.dev/e/ai-copy')}catch(e){}});});
</script>"""


def ai_page(ctx, files):
    L = mcp_links()
    copy = lambda label="Copy link": f'<button class="abtn" type="button" data-copy="{E(MCP_URL)}">{label}</button>'
    hero = f"""<div class="hero aih">{PULSE_SVG}<div class="wrap" style="padding-bottom:40px">
<div><div class="eyebrow">Etsy Pulse · AI</div>
<h1>Ask your Etsy data anything</h1>
<p class="lede">Connect our Etsy tools to Claude, ChatGPT or Cursor. Ask in plain words: your AI pulls fresh Etsy search and shop data,
answers right in the chat, and turns it into a report when you ask.</p>
<ol class="steps3"><li>Click Connect</li><li>Sign in with Apify (free)</li><li>Ask your AI</li></ol>
<div class="hcta"><a class="hbtn" href="#connect">Connect your AI →</a><small>Runs on your own Apify account. Pay per search: from 13¢ for 1 keyword, top 20 listings.</small></div></div>
<div><video autoplay muted loop playsinline preload="metadata" poster="assets/ai/etsypulse-ai-wide-poster.png" width="1200" height="676"
aria-label="Demo: connect Etsy Pulse, sign in with Apify, ask about 5 Etsy niches, get answers and a report">
<source src="assets/ai/etsypulse-ai-wide.webm" type="video/webm"><source src="assets/ai/etsypulse-ai-wide.mp4" type="video/mp4">
<img class="poster" src="assets/ai/etsypulse-ai-wide-poster.png" alt="Demo of the Etsy Pulse AI connection"></video></div>
</div></div>"""

    apps = f"""<section id="connect"><h2>Connect in a minute</h2>
<p class="sub">It's Apify's official MCP server (the standard way AI apps plug into tools) with our two Etsy tools already picked:
the Etsy Search Scraper and the Etsy Shop Sales Tracker. One link works in every app below.</p>
<div class="urlbox"><code>{E(MCP_URL)}</code>{copy()}</div>
<div class="apps" style="margin-top:14px">
<div class="app"><h3>Claude</h3><p>claude.ai or the Claude desktop app.</p>
<div class="acts">{copy("1. Copy link")}<a class="abtn ghost" href="{E(CLAUDE_ADD)}" target="_blank" rel="noopener">2. Open Claude connectors →</a></div>
<ol><li>Name it <b>Etsy Pulse</b> and paste the link as the server URL.</li><li>Press <b>Add</b>, then <b>Connect</b>, and sign in with Apify.</li></ol></div>
<div class="app"><h3>ChatGPT</h3><p>Needs Developer mode (Plus, Pro, Business, Enterprise and Edu plans).</p>
<div class="acts">{copy("1. Copy link")}<a class="abtn ghost" href="{E(CHATGPT_SETTINGS)}" target="_blank" rel="noopener">2. Open ChatGPT settings →</a></div>
<ol><li>Go to <b>Apps</b> → <b>Create</b>. No Create button? Turn on <b>Developer mode</b> under Advanced.</li>
<li>Name it <b>Etsy Pulse</b>, paste the link, keep <b>OAuth</b>, press Create and sign in with Apify.</li></ol></div>
<div class="app"><h3>Cursor</h3><p>One click adds it. Cursor opens and asks you to confirm.</p>
<div class="acts"><a class="abtn" href="{E(L['cursor'])}">Add to Cursor</a></div>
<ol><li>Then sign in with Apify when Cursor asks.</li></ol></div>
<div class="app"><h3>VS Code</h3><p>One click adds it (Copilot agent mode).</p>
<div class="acts"><a class="abtn" href="{E(L['vscode'])}">Add to VS Code</a></div>
<ol><li>Then sign in with Apify when VS Code asks.</li></ol></div>
</div>
<p class="note">Another AI app? <a href="{E(MCP_SETUP)}" target="_blank" rel="noopener">Open Apify's setup page</a> with our tools already picked: it has steps for
Claude Code, Codex, GitHub Copilot CLI and more.</p></section>"""

    uses = [
        ("Compare niches", "Find the opening before you make anything.",
         "Compare “aprons”, “faux plants” and “pet storage”: what top sellers charge, how many have a Bestseller badge, and which looks easiest to break into.",
         "Uses: price, Bestseller badge, number of Etsy results"),
        ("Price-check a listing", "See where your price sits against the top 20.",
         "I sell a personalized pet toy basket for $18. Pull the top 20 for “pet toy basket” and tell me where my price sits.",
         "Uses: price, position, free shipping"),
        ("Ads vs Bestsellers", "Who's paying to be there, and who earned it.",
         "For “ceramic mug”, which of the top 20 are paid ads and which have a Bestseller badge or Star Seller? What do the badge winners have in common?",
         "Uses: ad flag, Bestseller, Star Seller, reviews, rating"),
        ("Titles and tags", "Write like the listings that rank.",
         "Read the titles of the top 20 “scarf pin brooch” listings and write 3 title options and 13 tag ideas in the same style for mine.",
         "Uses: listing titles. Etsy tags aren't in the data, so tag ideas come from the titles."),
        ("Weekly niche watch", "A short check-in on your niche and your rivals.",
         "Run my 3 keywords and look up shops X and Y. Write a short niche watch: top shops, price range, Bestseller badges, lifetime sales and reviews. I'll ask again next week to compare.",
         "Uses: Etsy Search + Shop Sales Tracker (lifetime sales, reviews, active listings)"),
        ("Charts and plans", "Turn answers into something you can use.",
         "Put it all in a report: a price chart per niche, the top shops, and a one-page plan for my first 10 listings.",
         "Your AI makes the chart or file from the rows our tools return."),
    ]
    uses_html = "".join(f'<div class="use"><h3>{E(t)}</h3><p>{E(d)}</p><q>{E(p)}</q><div class="f">{E(f)}</div></div>' for t, d, p, f in uses)

    convo = """<section><h2>What it looks like</h2><p class="sub">The conversation from the video, with the real numbers from our own Etsy search run
(Oct 7, 2026, top 10 listings for each of 5 niches, US shopper).</p>
<div class="convo">
<div class="u">Who are the top sellers in my 5 niches?</div>
<div class="b"><div class="t">Ran Etsy Search Scraper · 5 niches · top 10 each</div>#1 on Etsy search right now: <b>backpacks</b> HKwoodwork ($18, Bestseller badge),
<b>aprons</b> VivifyCreationsUS ($12), <b>pet storage</b> PeachBlossomAU ($12), <b>patches</b> CustomPatchesTX ($7), <b>faux plants</b> WaterFreeGreenery ($36).</div>
<div class="u">How do Bestseller shops price vs the rest?</div>
<div class="b">Listings with a Bestseller badge charge more in 3 of 4 niches (patches had none in the top 10). Typical prices, badge vs the rest of the top 10:
<ul><li>backpacks: <b>$62 vs $16</b></li><li>aprons: $22 vs $20</li><li>pet storage: $14 vs $12</li><li>faux plants: $23 vs $36 (the one where badge holders charge less)</li></ul>
<div class="t">Small groups: 2 to 5 badge holders per niche.</div></div>
<div class="u">Put it all in a report with the other analytics</div>
<div class="b">Here's your report: typical price, the range most top sellers charge, Bestseller badges, free shipping and the #1 shop for each niche, with charts.
<div class="t">Ask for a document or PDF if your AI app can make files.</div></div>
</div>
<p class="note">Source: publicrecords Etsy Search Scraper, Apify run mZPhcYgZOJ8SKb9fW, Oct 7, 2026 (data/niche/2026-10-07/listings.csv, top 10 per keyword).
Answers in your chat will be worded by your AI and use the data from your own run.</p></section>"""

    costs = f"""<section><h2>How it works, and what it costs</h2>
<div class="costs">
<div><b>Runs through Apify</b><p>Apify is the platform our tools run on. The link is Apify's MCP server with our two Etsy tools picked. You sign in with your own Apify account: free to create, and the free plan includes $5 of usage a month.</p></div>
<div><b>Pay per search</b><p>Etsy Search: from 13¢ for 1 keyword and the top 20 listings ($0.005 per run + $0.006 per listing, Apify usage included). Shop Sales Tracker: $0.005 per run + $0.003 per shop, plus Apify usage.</p></div>
<div><b>Your account, your data</b><p>Every run and its results stay in your Apify account. Sign-in happens on Apify's own screen; we never see your password. Remove access any time in Apify Console → Settings → API &amp; Integrations.</p></div>
</div></section>"""

    tryit = f"""<section><div class="try"><b>No account yet? Try it with our free files.</b> Download our free top-10 listings file
(<a href="{files.get('niche_listings', 'data/niche-listings-latest.csv')}">CSV</a>) and drop it into any AI chat. Then ask:
<ul><li>“What should I charge for pet storage?”</li><li>“Which listings have a Bestseller badge, and what do they have in common?”</li>
<li>“Write me a one-page report on these 5 niches.”</li></ul>
<p class="note" style="margin-bottom:0">The free file is a weekly snapshot (top 10 per niche). Connect above for fresh data on any keyword.
Rather not use AI? <a href="{BUILDER}?from=ai">Build a report here</a> or <a href="{TINY_RUN}" rel="noopener">run it on Apify</a>.</p></div></section>"""

    body = (f"<style>{AI_CSS}</style>{apps}<section><h2>What you can do</h2><p class=\"sub\">Six things to ask once you're connected. "
            f"Copy a prompt, swap in your own niche.</p><div class=\"uses\">{uses_html}</div></section>{convo}{costs}{tryit}")
    return page("ai.html", "Ask your Etsy data anything: connect Etsy Pulse to Claude, ChatGPT or Cursor | Etsy Pulse",
                "Connect our Etsy tools to your AI through Apify's MCP server. Ask about any niche and get answers and reports from fresh Etsy data. Pay per search, from 13¢ for 1 keyword and the top 20 listings.",
                body, ctx, hero, scripts=AI_JS)


# ---------------------------------------------------------------- public checks
import re as _re
BANNED = _re.compile(r"\bmedian\b|middle half|\bpage[ -]1\b|7-day pace|\biqr\b", _re.I)


def unesc_link(d):
    return {**d, "url": html.unescape(d["url"])}


def visible_text(h):
    """What a visitor can read: page text plus <title> and meta/og descriptions (scripts, styles and tags removed)."""
    metas = " ".join(_re.findall(r'<meta[^>]+(?:name|property)="(?:description|og:title|og:description|twitter:title|twitter:description)"[^>]+content="([^"]*)"', h))
    body = _re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", h)
    body = _re.sub(r"(?s)<[^>]+>", " ", body)
    return html.unescape(body + " " + metas)


def check_public(out_dir):
    """Fail the build if a public file breaks the rules: banned robot words in visible text / CSV headers / builder strings,
    or a report CSV with more than PUBLIC_N rows (niche listings: PUBLIC_N per keyword)."""
    bad = []
    for root, _, fs in os.walk(out_dir):
        for f in fs:
            p = os.path.join(root, f)
            rel = os.path.relpath(p, out_dir)
            if f.endswith(".html"):
                for mt in BANNED.finditer(visible_text(open(p, encoding="utf-8").read())):
                    bad.append(f"{rel}: banned word '{mt.group(0)}'")
            elif f.endswith(".csv"):
                rows = list(csv.reader(open(p, encoding="utf-8")))
                if rows and BANNED.search(",".join(rows[0])):
                    bad.append(f"{rel}: banned word in CSV header")
                body = rows[1:]
                if "niche-listings" in f:
                    per = {}
                    for r_ in body:
                        per[r_[0]] = per.get(r_[0], 0) + 1
                    if per and max(per.values()) > PUBLIC_N:
                        bad.append(f"{rel}: {max(per.values())} rows for one keyword (max {PUBLIC_N})")
                elif "niche-summary" not in f and len(body) > PUBLIC_N:
                    bad.append(f"{rel}: {len(body)} rows (max {PUBLIC_N})")
            elif f == "builder.js":
                for lit in _re.findall(r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'', open(p, encoding="utf-8").read()):
                    t = visible_text(lit[0] or lit[1])
                    if BANNED.search(t):
                        bad.append(f"{rel}: banned word in text '{t[:60]}'")
    if bad:
        raise SystemExit("public check failed:\n  " + "\n  ".join(bad))
    print("public check ok: no banned words, every report <= %d rows" % PUBLIC_N)


# ---------------------------------------------------------------- build
def build(out_dir):
    pc = cuts("panel")
    if not pc:
        raise SystemExit("no data/panel/<cut>/ — run scripts/export_panel_cut.py")
    P = load_panel(pc[-1])
    prev = load_panel(pc[-2]) if len(pc) >= 2 else None
    nc = cuts("niche")
    N = load_niche(nc[-1]) if nc else None
    meta = P["meta"]
    cut, snap = P["cut"], meta["snapshot_date"]

    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(os.path.join(out_dir, "data"))
    shutil.copytree(os.path.join(ROOT, "assets"), os.path.join(out_dir, "assets"))

    # downloads (dated + latest alias)
    files = {}
    for k in ("movers", "categories", "rising"):
        src = os.path.join(ROOT, "data", "panel", cut, f"{k}.csv")
        rows_ = read_csv(src)[:PUBLIC_N]
        for nm in (f"{k}-{cut}.csv", f"{k}-latest.csv"):
            write_public_csv(os.path.join(out_dir, "data", nm), rows_)
        files[k] = f"data/{k}-{cut}.csv"
    if N:
        for k in ("summary", "listings"):
            src = os.path.join(ROOT, "data", "niche", N["cut"], f"{k}.csv")
            rows_ = read_csv(src)
            if k == "listings":   # top PUBLIC_N results per keyword
                seen = {}
                rows_ = [x for x in sorted(rows_, key=lambda x: (x["query"], int(float(x.get("position") or 0))))
                         if seen.setdefault(x["query"], []).append(1) or len(seen[x["query"]]) <= PUBLIC_N]
            for nm in (f"niche-{k}-{N['cut']}.csv", f"niche-{k}-latest.csv"):
                write_public_csv(os.path.join(out_dir, "data", nm), rows_)
            files["niche_" + k] = f"data/niche-{k}-{N['cut']}.csv"
        files["niche_listings_rows"] = len(rows_)

    # panel coverage for the report builder (numbers come from meta.json written at publish time)
    _c = cov_of(meta)
    with open(os.path.join(out_dir, "data", "coverage.json"), "w", encoding="utf-8") as fh:
        json.dump({"snapshot_date": snap, "as_of": nice_date((_c.get("series") or [{"date": snap}])[-1]["date"]),
                   "panel_shops": _c.get("panel_shops"), "shops_read_once": _c.get("shops_read_once"),
                   "shops_measured": _c.get("shops_measured"), "shops_measured_7d_span": _c.get("shops_measured_7d_span"),
                   "series": _c.get("series") or []}, fh)
    pages = ["index.html", "ai.html", BUILDER, "movers.html", "categories.html", "rising.html"]
    if prev:
        pages.append("breakouts.html")
    if N and any((r.get("listings") or 0) >= 20 for r in N["rows"]):
        pages.append("niche.html")
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": "Etsy Pulse: weekly Etsy shop movers",
          "description": "Etsy shops and categories with the biggest 7-day sales gains among the shops publicrecords measures, from public shop sales counters.",
          "url": SITE_URL, "dateModified": cut, "creator": {"@type": "Organization", "name": "publicrecords"},
          "isAccessibleForFree": True, "license": "https://creativecommons.org/licenses/by/4.0/"}
    ctx = {"pages": pages, "cut": cut, "snap": snap, "ld": ld}
    og_ok = og_image(out_dir, P)
    m, c, r = P["movers"], P["categories"], P["rising"]
    spans = sorted({x["days_observed"] for x in m if x.get("days_observed")})
    if spans and spans[-1] < 7:
        rng = f"{spans[0]}–{spans[-1]}" if spans[0] != spans[-1] else f"{spans[0]}"
        span_note = f"Gains scaled to 7 days from {rng} days of reads"
    else:
        span_note = f"Updated {nice_date(cut)}"

    cv = cov_of(meta)
    meas = cv.get("shops_measured")
    meas_txt = f"{n(meas)} measured shops" if meas is not None else "the shops we measure"
    src_line = (f'<p class="note">Source: publicrecords Velocity panel, cut {E(cut)}, counters read through {E(snap)}. '
                f'The panel lists {n(cv["panel_shops"])} shops; {n(meas) + " have a measured sales figure (sales counter read on 2+ days); " if meas is not None else ""}'
                f'{n(meta["shops_with_gain_ge_min"])} of those with ≥{meta["min_lifetime_sales"]} lifetime sales showed a gain and are ranked here. '
                f'Fewer than 7 days of reads are scaled to 7 days.</p>')
    cov_html = f'<p class="cov">{coverage_short(meta)}</p>' if coverage_short(meta) else ""

    mi, ci, ri = movers_insights(P), category_insights(P), rising_insights(P)
    ni = niche_insights(N) if "niche.html" in pages else []

    # ---- overview
    top = m[0]
    kpis = f"""<div class="kpis">
<div class="kpi"><div class="v">{plus(top['sales_7d_delta'])}</div><div class="l">#1 of the measured shops this week: {E(top['shop_name'])}</div></div>
<div class="kpi"><div class="v">{E(leaf(c[0]['category']))}</div><div class="l">Top category among measured shops, {plus(c[0]['total_7d_delta'])} across {c[0]['shops_moving']} shops</div></div>
<div class="kpi"><div class="v">{plus(meta['total_7d_delta_ge_min'])}</div><div class="l">7-day gain across the {n(meta['shops_with_gain_ge_min'])} gaining shops with {meta['min_lifetime_sales']}+ lifetime sales (scaled)</div></div>
<div class="kpi"><div class="v">{len(c)}</div><div class="l">categories with measured shops gaining</div></div>
</div>"""
    hero = f"""<div class="hero">{PULSE_SVG}<div class="wrap">
<div class="eyebrow">Etsy Pulse · Weekly report</div>
<h1>Etsy shops on the move this week</h1>
<p class="lede">The biggest 7-day sales jumps among the Etsy shops we measure, read from public Etsy sales counters.</p>
{hero_cta()}
<div class="chips">{f'<span><b>{n(cv["panel_shops"])}</b> shops in our panel</span>' if cv.get("panel_shops") else ''}{f'<span><b>{n(meas)}</b> with a measured sales figure</span>' if meas is not None else ''}<span><b>{n(meta['shops_with_gain_ge_min'])}</b> gaining, {meta['min_lifetime_sales']}+ sales, ranked here</span><span>{E(span_note)}</span></div>
{cov_html}
</div></div>"""

    def mini(rows, f_name, f_val, k=3):
        return "<ul class=mini>" + "".join(
            f'<li><span class="nm">{E(f_name(x))}</span><b>{f_val(x)}</b></li>' for x in rows[:k]) + "</ul>"

    CL = custom_links(meta)
    cards = [
        ("movers.html", "Top Movers", f"{len(m)}", "Measured shops with the biggest 7-day sales gain.",
         mini(m, lambda x: x["shop_name"], lambda x: plus(x["sales_7d_delta"]))),
        ("categories.html", "Hot Categories", f"{len(c)}", "Where the gains are piling up, by category.",
         mini(c, lambda x: leaf(x["category"]), lambda x: plus(x["total_7d_delta"]))),
        ("rising.html", "Rising Shops", f"{len(r)}", "Fastest measured shops with under 1,000 lifetime sales.",
         mini(r, lambda x: x["shop_name"], lambda x: plus(x["sales_7d_delta"]))),
    ]
    if "niche.html" in pages:
        nr = [x for x in N["rows"] if (x.get("listings") or 0) >= 20]
        cards.append(("niche.html", "Niche Prices", f"{len(nr)}", "What top sellers charge, and their badges, in the niches of this week's top movers.",
                      mini(nr, lambda x: x["keyword"], lambda x: f"typical {money(x['price_median'])}")))
    if prev:
        new, _ = breakout_rows(P, prev)
        cards.append(("breakouts.html", "Breakouts", f"{len(new)}", f"New to the top {len(m)} since {prev['cut']}.",
                      mini(new, lambda x: x["shop_name"], lambda x: f"#{x['rank']}")))
    else:
        cards.append(("#breakouts", "Breakouts", "soon", "Shops new to the top list vs the last cut.",
                      '<ul class=mini><li><span class="nm">Starts with the next weekly cut: we need two cuts to compare.</span></li></ul>'))
    cards_html = "".join(f'<a class="rcard" href="{h}"><div class="t">{t}<span>{k}</span></div><div class="d">{d}</div>{mn}</a>'
                         for h, t, k, d, mn in cards)
    over_ins = mi[:3] + ci[1:2] + (ni[:1] if ni else [])
    body = f"""{fresh_box(nice_date(snap), f"{meas_txt} · {len(m)} movers · {len(c)} categories · {len(r)} rising", cut)}
{kpis}
<section>{insights_block(over_ins, "This week's takeaways")}</section>
<section><h2>Reports</h2><p class="sub">Each report has its own page, a plain-English read and a CSV.</p>
<div class="grid">{cards_html}</div></section>
<section><h2>Top 10 movers</h2><p class="sub">Biggest 7-day gain in sales. Bar = size vs #1.</p>
{shop_rows(m[:PUBLIC_N], m[0]['sales_7d_delta'], None)}
{more50(CL["movers"]["url"], " movers", CL["movers"]["ready"], "site-home")}</section>
<section class="method" id="method"><h2>How we measure</h2>
<h3>Sales gains</h3><p>{E(meta['method'])} Lifetime sales and the gain come from the public sales counter on each Etsy shop page.
"Week vs lifetime" = the 7-day gain as a share of everything the shop has sold.</p>
<h3>Coverage</h3><p>{coverage_line(meta)} A shop's sales gain can only be computed once its counter has been read on two different days, so the rankings
use only measured shops. This cut ranks the {n(meta['shops_with_gain_ge_min'])} measured shops with at least
{meta['min_lifetime_sales']} lifetime sales whose counter went up ({n(meta['shops_with_gain_any_size'])} measured shops of any size went up).
These are not all of Etsy: they are the shops in our panel that we could measure this week. Categories come from each shop's listings; {n(meta['shops_with_gain_ge_min'] - meta['shops_with_gain_ge_min_known_category'])} shops with no category are left out of Hot Categories.</p>
{"<h3>Niche prices</h3><p>The top results of an Etsy search (US shopper, Etsy's best-match order, first results page) for keywords taken from the categories of this week's leading movers, captured " + E((N['meta'].get('captured_at') or '')[:10]) + " with our Etsy Search Scraper (Apify run " + E(N['meta']['run_id']) + "). Typical price is the middle price of those results; most charge = the middle 50% of prices.</p>" if "niche.html" in pages else ""}
<h3>Free top {PUBLIC_N}, your own top {CUSTOM_N}</h3><p>Free reports show the top {PUBLIC_N}. For the top {CUSTOM_N}, or any other niche or category, run your own report: the button under each report opens the builder already set up.</p>
<p id="breakouts">Breakouts appear once there are two weekly cuts to compare.</p></section>"""
    desc_home = (f"This week's Etsy movers among {meas_txt}: {top['shop_name']} {plus(top['sales_7d_delta'])} sales in 7 days; "
                 f"{leaf(c[0]['category'])} lead categories ({plus(c[0]['total_7d_delta'])}). From public Etsy sales counters; gains scaled to 7 days where we have fewer days of reads.")
    w = lambda name, html_: open(os.path.join(out_dir, name), "w", encoding="utf-8").write(html_)
    w("index.html", page("index.html", f"Etsy Pulse: Etsy shops on the move this week ({nice_date(snap)})", desc_home, body, ctx, hero))

    def simple_hero(eyebrow, h1, lede):
        return (f'<div class="hero">{PULSE_SVG}<div class="wrap" style="padding-bottom:30px"><div class="eyebrow">{eyebrow}</div>'
                f'<h1>{h1}</h1><p class="lede">{lede}</p>{hero_cta()}<div class="chips"><span>Week to {nice_date(snap)}</span>'
                + (f'<span><b>{n(meas)}</b> measured of {n(cv["panel_shops"])} shops in our panel</span>' if meas is not None else '')
                + f'<span>{E(span_note)}</span></div></div></div>')

    # ---- movers
    body = f"""{fresh_box(nice_date(snap), f"top {len(m)} of {n(meta['shops_with_gain_ge_min'])} gaining shops ({meta['min_lifetime_sales']}+ sales) · {meas_txt}", cut)}<section>{insights_block(mi)}{report_btn("site-movers", "Etsy Shop Sales Tracker", "Track 7-day sales for any shops you choose: yours, competitors, or the ones above.")}</section>
<section><h2>Top {len(m)} shops by 7-day sales gain</h2><p class="sub">Measured shops with at least {meta['min_lifetime_sales']} lifetime sales. Tap a shop to open it on Etsy.</p>
{shop_rows(m, m[0]['sales_7d_delta'], None)}
{more50(CL["movers"]["url"], "", CL["movers"]["ready"], "site-movers")}
{dl(files['movers'], f'Download CSV (top {len(m)}, cut {cut})')}{src_line}</section>"""
    w("movers.html", page("movers.html", f"Top {len(m)} Etsy shops by 7-day sales gain ({nice_date(snap)}) | Etsy Pulse",
                          f"{top['shop_name']} leads with {plus(top['sales_7d_delta'])} sales in 7 days. Free top {len(m)} with categories and CSV.",
                          body, ctx, simple_hero("Report · Top Movers", "Top Movers", "The biggest 7-day sales gains among the Etsy shops we measure, from public sales counters.")))

    # ---- categories
    body = f"""{fresh_box(nice_date(snap), f"top {len(c)} of {n(meta['categories'])} categories", cut)}<section>{insights_block(ci)}{report_btn("site-categories", "Etsy Shop Sales Tracker", "Feed in the shops of any category and see who is gaining sales week to week.")}</section>
<section><h2>Categories ranked by combined 7-day gain</h2><p class="sub">Sum of 7-day sales gains of every measured shop in the category. The top {len(c)} of {n(meta['categories'])} categories with shops gaining.</p>
{cat_rows(c)}
{more50(CL["categories"].get(c[0]["category"], {}).get("url", ""), " shops in " + E(leaf(c[0]["category"])), CL["categories"].get(c[0]["category"], {}).get("ready", False), "site-categories")}
{dl(files['categories'], f'Download CSV (top {len(c)}, cut {cut})')}{src_line}</section>"""
    w("categories.html", page("categories.html", f"Top Etsy categories by sales gain among measured shops ({nice_date(snap)}) | Etsy Pulse",
                              f"{leaf(c[0]['category'])} lead with {plus(c[0]['total_7d_delta'])} sales across {c[0]['shops_moving']} shops. Top {len(c)} of {meta['categories']} categories.",
                              body, ctx, simple_hero("Report · Hot Categories", "Hot Categories", "Where the sales gains of the shops we measure are piling up this week.")))

    # ---- rising
    body = f"""{fresh_box(nice_date(snap), f"top {len(r)}", cut)}<section>{insights_block(ri)}{report_btn("site-rising", "Etsy Shop Sales Tracker", "Watch small shops in your niche and catch the next riser early.")}</section>
<section><h2>Fastest measured shops under 1,000 lifetime sales</h2><p class="sub">Same 7-day gain, smaller shops ({meta['min_lifetime_sales']}–999 lifetime sales). These are the ones to learn from if you're early.</p>
{shop_rows(r, r[0]['sales_7d_delta'] if r else 1, None)}
{more50(CL["rising"]["url"], " small shops", CL["rising"]["ready"], "site-rising")}
{dl(files['rising'], f'Download CSV (top {len(r)}, cut {cut})')}{src_line}</section>"""
    w("rising.html", page("rising.html", f"Fastest-rising small Etsy shops we measure ({nice_date(snap)}) | Etsy Pulse",
                          f"Small Etsy shops (under 1,000 sales) with the biggest 7-day jumps among the shops we measure. {r[0]['shop_name']} added {plus(r[0]['sales_7d_delta'])}." if r else "Rising small Etsy shops.",
                          body, ctx, simple_hero("Report · Rising Shops", "Rising Shops", "Small measured shops with big weeks: under 1,000 lifetime sales.")))

    # ---- breakouts
    if prev:
        new, jumps = breakout_rows(P, prev)
        bi = []
        if new:
            bi.append(f"<b>{len(new)}</b> shops are new to the top {len(m)} since {prev['cut']}. Highest: "
                      f"<b>{E(new[0]['shop_name'])}</b> at #{new[0]['rank']} ({plus(new[0]['sales_7d_delta'])}).")
        if jumps:
            bi.append(f"Biggest climb: <b>{E(jumps[0]['shop_name'])}</b>, #{jumps[0]['was']} → #{jumps[0]['rank']}.")
        body = (f"<section>{insights_block(bi)}</section><section><h2>New to the top {len(m)}</h2>"
                f"<p class=sub>Not in the {prev['cut']} top {PUBLIC_N}.</p>{shop_rows(new[:PUBLIC_N], m[0]['sales_7d_delta'], None) if new else '<p>None this week.</p>'}"
                f"{more50(CL['movers']['url'], ' movers', CL['movers']['ready'], 'site-breakouts')}{src_line}</section>")
        w("breakouts.html", page("breakouts.html", f"Etsy breakout shops ({nice_date(snap)}) | Etsy Pulse",
                                 "Etsy shops new to the weekly top movers list.", body, ctx,
                                 simple_hero("Report · Breakouts", "Breakouts", f"New to the top list since {prev['cut']}.")))

    # ---- niche
    if "niche.html" in pages:
        nr = [x for x in N["rows"] if (x.get("listings") or 0) >= 20]
        cards = []
        for x in nr:
            bands = [(k[5:], int(v or 0)) for k, v in x.items() if k.startswith("band ")]
            tot = sum(v for _, v in bands) or 1
            segs = "".join(f'<i style="width:{100 * v / tot:.1f}%;background:{BAND_COLORS[i]}">{v if v / tot > .08 else ""}</i>'
                           for i, (_, v) in enumerate(bands) if v)
            leg = "".join(f'<span><i style="background:{BAND_COLORS[i]}"></i>{E(lbl)}</span>' for i, (lbl, _) in enumerate(bands))
            cards.append(f"""<div class="nc"><h3>“{E(x['keyword'])}”</h3>
<div class="from">from {E(leaf(x['from_category']) if x['from_category'] else 'hot categories')} · top {int(x['listings'])} results{(' · Etsy shows ' + n(x['etsy_total_results']) + ' results') if x.get('etsy_total_results') else ''}</div>
<div class="stats"><div><b>{money(x['price_median'])}</b><span>typical price</span></div>
<div><b>{money(x['price_p25'])}–{money(x['price_p75'])}</b><span>most charge</span></div>
<div><b>{pct(x['bestseller_share'])}</b><span>Bestseller badge</span></div></div>
<div class="bands">{segs}</div><div class="legend">{leg}</div>
<div class="facts"><span>Free shipping <b>{pct(x['free_shipping_share'])}</b></span><span>Typical shop reviews <b>{n(x['median_shop_reviews'] or 0)}</b></span></div>
<a class="more" href="{niche_link(x['keyword'], 'site-niche-top50')}">Want the top {CUSTOM_N} for “{E(x['keyword'])}”? Run your own report →</a></div>""")
        skipped = [x["keyword"] for x in N["rows"] if (x.get("listings") or 0) < 20]
        kws = [k["keyword"] for k in N["meta"]["keywords"]]
        missing = [k for k in kws if k not in [x["keyword"] for x in nr]]
        miss_note = (f" Not shown (fewer than 20 listings captured this run): {', '.join(missing)}." if missing else "")
        body = f"""{fresh_box(nice_date((N['meta'].get('captured_at') or N['cut'])[:10]), f"{N['meta']['rows']['listings']} listings · {len(nr)} niches", cut)}<section>{insights_block(ni)}{report_btn("site-niche", "Etsy Search Scraper", "Get this price breakdown for your own keyword: the top results as a spreadsheet.")}</section>
<section><h2>What top sellers charge in the niches of this week's top movers</h2><p class="sub">Keywords are the categories of this week's leading Top Movers shops. Prices are what Etsy shows US shoppers in the top search results (Etsy's best-match order).</p>
<div class="niche">{''.join(cards)}</div>
{more50(niche_link(src="site-niche-top50-any"), " results", True)}
{dl(files['niche_summary'], f"Download summary CSV ({len(N['rows'])} keywords)")} {dl(files['niche_listings'], f"Download listings CSV (top {PUBLIC_N} per keyword, {files['niche_listings_rows']} rows)")}
<p class="note">Source: publicrecords Etsy Search Scraper, Apify run {E(N['meta']['run_id'])}{(' + ' + ', '.join(E(x) for x in N['meta'].get('extra_run_ids', []))) if N['meta'].get('extra_run_ids') else ''}, captured {E((N['meta'].get('captured_at') or '')[:16].replace('T', ' '))} UTC, {N['meta']['rows']['listings']} listings.{E(miss_note)}</p></section>"""
        w("niche.html", page("niche.html", f"Etsy niche prices: {', '.join(x['keyword'] for x in nr)} | Etsy Pulse",
                             "What top Etsy sellers charge, how prices spread and how many have a Bestseller badge, in the niches of this week's top movers.",
                             body, ctx, simple_hero("Report · Niche Prices", "Niche Prices", "What top Etsy sellers charge in the niches of this week's top movers.")))

    # ---- report builder (run.html): Sign in with Apify, run our Actors on the visitor's account, report in-page
    builder_hero = (f'<div class="hero">{PULSE_SVG}<div class="wrap" style="padding-bottom:52px"><div class="eyebrow">Etsy Pulse · Custom report</div>'
                    '<h1>Build your own Etsy report</h1><p class="lede">Pick a report, type a niche or a few shops, press Run. '
                    'Charts, plain-English takeaways and a spreadsheet in a few minutes. No code, no API keys.</p></div></div>')
    body = """<div id="builder" class="bld"><noscript><div class="berr">The report builder needs JavaScript. You can still run our tools directly on Apify:
<a href="https://apify.com/publicrecords/etsy-search-scraper">Etsy Search Scraper</a> · <a href="https://apify.com/publicrecords/etsy-shop-velocity">Etsy Shop Sales Tracker</a>.</div></noscript></div>
<div id="progress" hidden></div>
<div id="report" hidden></div>
<section class="how-sec"><h2>How it works</h2><p class="sub">Three steps. Your data and your spend stay in your own Apify account.</p>
<div class="how">
<div><b>Sign in with Apify (free)</b><p>Apify is the platform our tools run on. New accounts are free, no credit card, and the free plan includes $5 of usage every month.</p></div>
<div><b>Press Run</b><p>The report runs on your account. Keyword reports cost $0.006 per listing plus $0.005 per keyword (20 listings ≈ $0.13, Apify platform usage included); shop reports $0.003 per shop plus $0.005 (plus Apify platform usage, usually under $0.02 a run). The price updates as you change options, and you see “about $X, at most $Y” before you start.</p></div>
<div><b>Read it, download it</b><p>Takeaways, charts and a sortable table appear right here. Download the spreadsheet (CSV), or print / save as PDF. Your runs and data also stay in your Apify account.</p></div>
</div>
<p class="note">Sign-in uses Apify's own OAuth screen; we never see your password. Apify offers one permission level (full account access): this page uses it only to start the report you asked for and read its results. The key stays in this browser tab and is gone when you close it. Remove the approval any time in Apify Console → Settings → API &amp; Integrations.</p></section>"""
    w(BUILDER, page(BUILDER, "Build your own Etsy report: prices, bestsellers, top shops, shop sales | Etsy Pulse",
                    "Type a niche or a few Etsy shops and get a live report: price bands, Bestseller share, top shops, sales pace, CSV. Free Apify sign-in, no code.",
                    body, ctx, builder_hero, scripts=f'<script src="assets/builder.js?v={cut}-b6" defer></script>'))

    # ---- AI page
    w("ai.html", ai_page(ctx, files))

    # ---- seo files
    with open(os.path.join(out_dir, "robots.txt"), "w") as fh:
        fh.write(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}sitemap.xml\n")
    with open(os.path.join(out_dir, "sitemap.xml"), "w") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for p in pages:
            fh.write(f"  <url><loc>{SITE_URL}{'' if p == 'index.html' else p}</loc><lastmod>{cut}</lastmod></url>\n")
        fh.write("</urlset>\n")
    open(os.path.join(out_dir, ".nojekyll"), "w").close()
    report = {"cut": cut, "snapshot": snap, "pages": pages, "og": og_ok,
              "rows": {"movers": len(m), "categories": len(c), "rising": len(r),
                       "niche_keywords": len([x for x in (N["rows"] if N else []) if (x.get("listings") or 0) >= 20])},
              "breakouts": bool(prev), "public_max_rows": PUBLIC_N,
              "custom_links": {"movers": unesc_link(CL["movers"]), "rising": unesc_link(CL["rising"]),
                               "categories": {k: unesc_link(v) for k, v in CL["categories"].items()},
                               "niche": {x["keyword"]: html.unescape(niche_link(x["keyword"], "site-niche-top50")) for x in (N["rows"] if N else [])
                                         if (x.get("listings") or 0) >= 20}}}
    with open(os.path.join(out_dir, "build.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    check_public(out_dir)
    print(json.dumps(report))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "_site"))
    build(ap.parse_args().out)
