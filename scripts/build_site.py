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
        out[k] = rows
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
    small = max(m[:20], key=lambda r: r["gain_pct_of_lifetime"])
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
                   f"({broad['shops_moving']}), so it's not one shop carrying it. Median shop {plus(broad['median_7d_delta'])}.")
    big = [r for r in c if r["shops_moving"] >= 10]
    if big:
        med = max(big, key=lambda r: r["median_7d_delta"])
        out.append(f"Best typical shop: in <b>{E(leaf(med['category']))}</b> the median moving shop added "
                   f"<b>{plus(med['median_7d_delta'])}</b> (categories with 10+ moving shops).")
    t3 = sum(r["total_7d_delta"] for r in c[:3])
    tot = sum(r["total_7d_delta"] for r in c)
    out.append(f"The top 3 categories account for <b>{pct(t3 / tot)}</b> of measured gains across "
               f"{len(c)} categories.")
    conc = [r for r in c[:15] if r["shops_moving"] >= 5]
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
    out.append(f"The median shop in this list added <b>{plus(med)}</b> sales in 7 days, about {med / 7:.0f} a day.")
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
        out.append(f"<b>“{E(r['keyword'])}”</b>: median {money(r['price_median'])}; the middle half sells at "
                   f"{money(r['price_p25'])}–{money(r['price_p75'])}. Most crowded band: {E(bk)} "
                   f"({int(bv)} of {int(r['listings'])} page-1 listings).")
    hi = max(rows, key=lambda r: r["bestseller_share"])
    lo = min(rows, key=lambda r: r["bestseller_share"])
    if hi is not lo:
        out.append(f"Bestseller badges: <b>{pct(hi['bestseller_share'])}</b> of page-1 <b>{E(hi['keyword'])}</b> listings "
                   f"vs {pct(lo['bestseller_share'])} for {E(lo['keyword'])}. Fewer badges can mean less entrenched competition on page 1.")
    fs = max(rows, key=lambda r: r["free_shipping_share"])
    out.append(f"Free shipping is most common in <b>{E(fs['keyword'])}</b>: {pct(fs['free_shipping_share'])} of page-1 listings offer it.")
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

NAV = [("index.html", "Overview"), ("movers.html", "Top Movers"), ("categories.html", "Hot Categories"),
       ("rising.html", "Rising Shops"), ("breakouts.html", "Breakouts"), ("niche.html", "Niche Prices")]


def page(name, title, desc, body, ctx, hero=None):
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
</head><body>
<header class="top"><div class="wrap"><a class="brand" href="index.html"><img src="assets/logo-96.png" alt="" width="30" height="30">Etsy Pulse</a>
<a class="x" href="{X_URL}" rel="noopener">Follow @EtsyPulse</a></div></header>
<nav class="tabs" aria-label="Reports"><div class="wrap">{nav}</div></nav>
{hero or ""}
<main class="wrap">
{body}
{cta(ctx)}
</main>
<footer><div class="wrap">
<p><b>Etsy Pulse</b> is published by publicrecords, and the data comes from our own tools: the publicrecords Etsy Shop Sales Tracker panel
(public shop sales counters) and the publicrecords Etsy Search Scraper on Apify. We built them and we sell them, so weigh the links accordingly.</p>
<p>Movers cut {E(ctx['cut'])} (counters read through {E(ctx['snap'])}). Not affiliated with, endorsed by, or sponsored by Etsy, Inc.
Etsy is a trademark of Etsy, Inc.</p>
</div></footer>
</body></html>
"""


def cta(ctx):
    return f"""<section class="cta">
<h2>Run this on any niche</h2>
<p>Every number here comes from public Etsy data our tools collect. Point it at your own keyword or category and get
prices, reviews, bestseller badges and shop links for every page-1 listing, as a CSV in a few minutes.</p>
<a class="btn" href="{CTA_URL}" rel="noopener">Try the Etsy Search Scraper</a><a class="btn ghost" href="{TRACKER_URL}" rel="noopener">Track a shop's sales</a>
<div class="disc">Our tools (publicrecords on Apify). Pay per result; Apify's free plan covers a small test.</div>
</section>"""


def hero_cta():
    return (f'<div class="hcta"><a class="hbtn" href="{CTA_URL}" rel="noopener">Run a custom report on any niche →</a>'
            '<small>Your keyword, your CSV: prices, reviews, Bestseller badges, shop links. Our Etsy Search Scraper on Apify, pay per result.</small></div>')


def report_btn(slug, actor_label, text):
    return (f'<div class="rbtn"><span>{text}</span>'
            f'<a href="{R}{slug}" rel="noopener">Run this report yourself →</a></div>'
            f'<p class="note" style="margin-top:6px">Opens our {actor_label} on Apify (publicrecords, pay per result).</p>')


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


def fresh_box(snapshot_label, rows_label, cut):
    return (f'<div class="fresh"><div><b>Free reports refresh {cadence_word()}.</b> Need today\'s numbers for your niche? '
            f'<a href="{CTA_URL}" rel="noopener">Run a live report →</a></div>'
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
          '<span class="r">Shops gaining</span><span class="r">Median shop</span><span>Leader</span>'
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
            f'<span><em>median </em><b>{plus(r["median_7d_delta"])}</b></span>'
            f'<span class="ld"><em>leader </em><a href="{E(r["top_shop_url"])}" rel="nofollow noopener">{E(r["top_shop"])}</a> '
            f'<b>{plus(r["top_shop_7d_delta"])}</b></span></span>'
            f'<span class="big">{plus(r["total_7d_delta"])}</span></div>')
    cols = "34px minmax(160px,1.4fr) 130px 120px 110px minmax(180px,1.4fr) 90px"
    return f'<div class="tc cat" role="table" style="--cols:{cols}">{"".join(out)}</div>'


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
    d.text((60, 596), "data by publicrecords (our tool) · not affiliated with Etsy", font=F(22, "Medium"),
           fill=(255, 236, 222))
    im.save(os.path.join(out_dir, "og.png"), optimize=True)
    return True


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
        for nm in (f"{k}-{cut}.csv", f"{k}-latest.csv"):
            shutil.copy(src, os.path.join(out_dir, "data", nm))
        files[k] = f"data/{k}-{cut}.csv"
    if N:
        for k in ("summary", "listings"):
            src = os.path.join(ROOT, "data", "niche", N["cut"], f"{k}.csv")
            for nm in (f"niche-{k}-{N['cut']}.csv", f"niche-{k}-latest.csv"):
                shutil.copy(src, os.path.join(out_dir, "data", nm))
            files["niche_" + k] = f"data/niche-{k}-{N['cut']}.csv"

    pages = ["index.html", "movers.html", "categories.html", "rising.html"]
    if prev:
        pages.append("breakouts.html")
    if N and any((r.get("listings") or 0) >= 20 for r in N["rows"]):
        pages.append("niche.html")
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": "Etsy Pulse: weekly Etsy shop movers",
          "description": "Etsy shops and categories with the biggest 7-day sales gains, from public shop sales counters.",
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

    src_line = (f'<p class="note">Source: publicrecords Velocity panel, cut {E(cut)}, counters read through {E(snap)}. '
                f'{n(meta["shops_with_gain_ge_min"])} shops with ≥{meta["min_lifetime_sales"]} lifetime sales showed a measurable '
                f'gain (panel of {n(meta["panel_shops"])} shops). Fewer than 7 days of reads are scaled to 7 days.</p>')

    mi, ci, ri = movers_insights(P), category_insights(P), rising_insights(P)
    ni = niche_insights(N) if "niche.html" in pages else []

    # ---- overview
    top = m[0]
    kpis = f"""<div class="kpis">
<div class="kpi"><div class="v">{plus(top['sales_7d_delta'])}</div><div class="l">#1 shop this week: {E(top['shop_name'])}</div></div>
<div class="kpi"><div class="v">{E(leaf(c[0]['category']))}</div><div class="l">Hottest category, {plus(c[0]['total_7d_delta'])} across {c[0]['shops_moving']} shops</div></div>
<div class="kpi"><div class="v">{plus(meta['total_7d_delta_ge_min'])}</div><div class="l">7-day gain across the {n(meta['shops_with_gain_ge_min'])} shops we measured (scaled)</div></div>
<div class="kpi"><div class="v">{len(c)}</div><div class="l">categories with shops gaining</div></div>
</div>"""
    hero = f"""<div class="hero">{PULSE_SVG}<div class="wrap">
<div class="eyebrow">Etsy Pulse · Weekly report</div>
<h1>What's selling on Etsy right now</h1>
<p class="lede">The shops and categories with the biggest 7-day sales jumps, read from public Etsy sales counters.</p>
{hero_cta()}
<div class="chips"><span>Week to {nice_date(snap)}</span><span>{n(meta['shops_with_gain_ge_min'])} shops measured</span><span>{E(span_note)}</span></div>
</div></div>"""

    def mini(rows, f_name, f_val, k=3):
        return "<ul class=mini>" + "".join(
            f'<li><span class="nm">{E(f_name(x))}</span><b>{f_val(x)}</b></li>' for x in rows[:k]) + "</ul>"

    cards = [
        ("movers.html", "Top Movers", f"{len(m)}", "Shops with the biggest 7-day sales gain.",
         mini(m, lambda x: x["shop_name"], lambda x: plus(x["sales_7d_delta"]))),
        ("categories.html", "Hot Categories", f"{len(c)}", "Where the gains are piling up, by category.",
         mini(c, lambda x: leaf(x["category"]), lambda x: plus(x["total_7d_delta"]))),
        ("rising.html", "Rising Shops", f"{len(r)}", "Fastest shops with under 1,000 lifetime sales.",
         mini(r, lambda x: x["shop_name"], lambda x: plus(x["sales_7d_delta"]))),
    ]
    if "niche.html" in pages:
        nr = [x for x in N["rows"] if (x.get("listings") or 0) >= 20]
        cards.append(("niche.html", "Niche Prices", f"{len(nr)}", "Page-1 prices and badges for the hottest niches.",
                      mini(nr, lambda x: x["keyword"], lambda x: f"median {money(x['price_median'])}")))
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
    body = f"""{fresh_box(nice_date(snap), f"{n(meta['shops_with_gain_ge_min'])} shops measured · {len(m)} movers · {len(c)} categories · {len(r)} rising", cut)}
{kpis}
<section>{insights_block(over_ins, "This week's takeaways")}</section>
<section><h2>Reports</h2><p class="sub">Each report has its own page, a plain-English read and a CSV.</p>
<div class="grid">{cards_html}</div></section>
<section><h2>Top 10 movers</h2><p class="sub">Biggest 7-day gain in sales. Bar = size vs #1.</p>
{shop_rows(m[:10], m[0]['sales_7d_delta'], None)}
<a class="dl" href="movers.html">See all {len(m)} →</a></section>
<section class="method" id="method"><h2>How we measure</h2>
<h3>Sales gains</h3><p>{E(meta['method'])} Lifetime sales and the gain come from the public sales counter on each Etsy shop page.
"Week vs lifetime" = the 7-day gain as a share of everything the shop has sold.</p>
<h3>Coverage</h3><p>The panel follows {n(meta['panel_shops'])} Etsy shops. This cut covers the {n(meta['shops_with_gain_ge_min'])} shops with at least
{meta['min_lifetime_sales']} lifetime sales and two or more counter reads showing a gain. Categories come from each shop's listings; {n(meta['shops_with_gain_ge_min'] - meta['shops_with_gain_ge_min_known_category'])} shops with no category are left out of Hot Categories.</p>
{"<h3>Niche prices</h3><p>Page 1 of Etsy search (US, relevance sort) for keywords taken from the categories of this week's leading movers, captured " + E((N['meta'].get('captured_at') or '')[:10]) + " with our Etsy Search Scraper (Apify run " + E(N['meta']['run_id']) + ").</p>" if "niche.html" in pages else ""}
<p id="breakouts">Breakouts appear once there are two weekly cuts to compare.</p></section>"""
    desc_home = (f"This week's Etsy movers: {top['shop_name']} {plus(top['sales_7d_delta'])} sales in 7 days; "
                 f"{leaf(c[0]['category'])} lead categories ({plus(c[0]['total_7d_delta'])}). From public Etsy sales counters; gains scaled to 7 days where we have fewer days of reads.")
    w = lambda name, html_: open(os.path.join(out_dir, name), "w", encoding="utf-8").write(html_)
    w("index.html", page("index.html", f"Etsy Pulse: what's selling on Etsy this week ({nice_date(snap)})", desc_home, body, ctx, hero))

    def simple_hero(eyebrow, h1, lede):
        return (f'<div class="hero">{PULSE_SVG}<div class="wrap" style="padding-bottom:30px"><div class="eyebrow">{eyebrow}</div>'
                f'<h1>{h1}</h1><p class="lede">{lede}</p>{hero_cta()}<div class="chips"><span>Week to {nice_date(snap)}</span>'
                f'<span>{E(span_note)}</span></div></div></div>')

    # ---- movers
    body = f"""{fresh_box(nice_date(snap), f"{len(m)} rows of {n(meta['shops_with_gain_ge_min'])} shops measured", cut)}<section>{insights_block(mi)}{report_btn("site-movers", "Etsy Shop Sales Tracker", "Track 7-day sales for any shops you choose: yours, competitors, or the ones above.")}</section>
<section><h2>Top {len(m)} shops by 7-day sales gain</h2><p class="sub">Shops with at least {meta['min_lifetime_sales']} lifetime sales. Tap a shop to open it on Etsy.</p>
{shop_rows(m, m[0]['sales_7d_delta'], None)}
{dl(files['movers'], f'Download CSV ({len(m)} rows, cut {cut})')}{src_line}</section>"""
    w("movers.html", page("movers.html", f"Top {len(m)} Etsy shops by 7-day sales gain ({nice_date(snap)}) | Etsy Pulse",
                          f"{top['shop_name']} leads with {plus(top['sales_7d_delta'])} sales in 7 days. Full top {len(m)} with categories and CSV.",
                          body, ctx, simple_hero("Report · Top Movers", "Top Movers", "The Etsy shops with the biggest 7-day sales gain, from public sales counters.")))

    # ---- categories
    body = f"""{fresh_box(nice_date(snap), f"{len(c)} categories", cut)}<section>{insights_block(ci)}{report_btn("site-categories", "Etsy Shop Sales Tracker", "Feed in the shops of any category and see who is gaining sales week to week.")}</section>
<section><h2>Categories ranked by combined 7-day gain</h2><p class="sub">Sum of 7-day sales gains of every measured shop in the category. Showing the top 20 of {len(c)}; all are in the CSV.</p>
{cat_rows(c[:20])}
{dl(files['categories'], f'Download CSV ({len(c)} rows, cut {cut})')}{src_line}</section>"""
    w("categories.html", page("categories.html", f"Hottest Etsy categories this week ({nice_date(snap)}) | Etsy Pulse",
                              f"{leaf(c[0]['category'])} lead with {plus(c[0]['total_7d_delta'])} sales across {c[0]['shops_moving']} shops. {len(c)} categories ranked.",
                              body, ctx, simple_hero("Report · Hot Categories", "Hot Categories", "Where this week's Etsy sales gains are piling up.")))

    # ---- rising
    body = f"""{fresh_box(nice_date(snap), f"{len(r)} rows", cut)}<section>{insights_block(ri)}{report_btn("site-rising", "Etsy Shop Sales Tracker", "Watch small shops in your niche and catch the next riser early.")}</section>
<section><h2>Fastest shops under 1,000 lifetime sales</h2><p class="sub">Same 7-day gain, smaller shops ({meta['min_lifetime_sales']}–999 lifetime sales). These are the ones to learn from if you're early.</p>
{shop_rows(r, r[0]['sales_7d_delta'] if r else 1, None)}
{dl(files['rising'], f'Download CSV ({len(r)} rows, cut {cut})')}{src_line}</section>"""
    w("rising.html", page("rising.html", f"Fastest-rising small Etsy shops ({nice_date(snap)}) | Etsy Pulse",
                          f"Small Etsy shops (under 1,000 sales) with the biggest 7-day jumps. {r[0]['shop_name']} added {plus(r[0]['sales_7d_delta'])}." if r else "Rising small Etsy shops.",
                          body, ctx, simple_hero("Report · Rising Shops", "Rising Shops", "Small shops with big weeks: under 1,000 lifetime sales.")))

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
                f"<p class=sub>Not in the {prev['cut']} list.</p>{shop_rows(new, m[0]['sales_7d_delta'], None) if new else '<p>None this week.</p>'}"
                f"{src_line}</section>")
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
<div class="from">from {E(leaf(x['from_category']) if x['from_category'] else 'hot categories')} · {int(x['listings'])} page-1 listings{(' · Etsy shows ' + n(x['etsy_total_results']) + ' results') if x.get('etsy_total_results') else ''}</div>
<div class="stats"><div><b>{money(x['price_median'])}</b><span>median price</span></div>
<div><b>{money(x['price_p25'])}–{money(x['price_p75'])}</b><span>middle half</span></div>
<div><b>{pct(x['bestseller_share'])}</b><span>Bestseller badge</span></div></div>
<div class="bands">{segs}</div><div class="legend">{leg}</div>
<div class="facts"><span>Free shipping <b>{pct(x['free_shipping_share'])}</b></span><span>Median reviews <b>{n(x['median_shop_reviews'] or 0)}</b></span></div></div>""")
        skipped = [x["keyword"] for x in N["rows"] if (x.get("listings") or 0) < 20]
        kws = [k["keyword"] for k in N["meta"]["keywords"]]
        missing = [k for k in kws if k not in [x["keyword"] for x in nr]]
        miss_note = (f" Not shown (fewer than 20 listings captured this run): {', '.join(missing)}." if missing else "")
        body = f"""{fresh_box(nice_date((N['meta'].get('captured_at') or N['cut'])[:10]), f"{N['meta']['rows']['listings']} listings · {len(nr)} niches", cut)}<section>{insights_block(ni)}{report_btn("site-niche", "Etsy Search Scraper", "Get this price breakdown for your own keyword: every page-1 listing as a CSV.")}</section>
<section><h2>Page-1 prices in this week's hottest niches</h2><p class="sub">Keywords are the categories of this week's leading Top Movers shops. Prices are what Etsy shows US shoppers on page 1 (relevance sort).</p>
<div class="niche">{''.join(cards)}</div>
{dl(files['niche_summary'], f"Download summary CSV ({len(N['rows'])} keywords)")} {dl(files['niche_listings'], f"Download listings CSV ({N['meta']['rows']['listings']} rows)")}
<p class="note">Source: publicrecords Etsy Search Scraper, Apify run {E(N['meta']['run_id'])}{(' + ' + ', '.join(E(x) for x in N['meta'].get('extra_run_ids', []))) if N['meta'].get('extra_run_ids') else ''}, captured {E((N['meta'].get('captured_at') or '')[:16].replace('T', ' '))} UTC, {N['meta']['rows']['listings']} listings.{E(miss_note)}</p></section>"""
        w("niche.html", page("niche.html", f"Etsy niche prices: {', '.join(x['keyword'] for x in nr)} | Etsy Pulse",
                             "Median prices, price bands and Bestseller-badge share on page 1 of Etsy search for this week's hottest niches.",
                             body, ctx, simple_hero("Report · Niche Prices", "Niche Prices", "What page 1 of Etsy search costs in this week's hottest niches.")))

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
              "breakouts": bool(prev)}
    with open(os.path.join(out_dir, "build.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    print(json.dumps(report))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "_site"))
    build(ap.parse_args().out)
