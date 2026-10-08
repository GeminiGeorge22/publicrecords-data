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
import re
import statistics
from zoneinfo import ZoneInfo

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
# DOMAIN-1: the site's base URL is ONE value, config/site.json "base_url" (canonical/og:url/sitemap/robots/JSON-LD all derive
# from SITE_URL). Flip it to "https://www.etsypulse.ca/" only after DNS for www.etsypulse.ca resolves to GitHub Pages and the
# Pages custom domain is set (scripts: /workspace/domain-1/apply.sh). GITHUB_IO_URL stays as the legacy address.
GITHUB_IO_URL = "https://geminigeorge22.github.io/publicrecords-data/"
SITE_URL = json.load(open(os.path.join(ROOT, "config", "site.json"), encoding="utf-8"))["base_url"]
assert SITE_URL.startswith("https://") and SITE_URL.endswith("/"), "config/site.json base_url must be https://... ending in /"
CTA_URL = "https://publicrecords-redirect.publicrecords.workers.dev/r/site-cta"
TRACKER_URL = "https://publicrecords-redirect.publicrecords.workers.dev/r/site-tracker"
R = "https://publicrecords-redirect.publicrecords.workers.dev/r/"
# BEACON-1 (Mark 2026-10-08): every page sends ONE anonymous page-view beacon to the worker: page name, referrer host only,
# utm_content/from tag, ?me=1 (own) and ?test=1 (not logged) passed through. No cookies (credentials:'omit'), no storage, no IDs.
VIEW_BEACON = "https://publicrecords-redirect.publicrecords.workers.dev/e/view"
def view_js(name):
    pg = re.sub(r"\.html$", "", name).replace("index", "home")
    return ("<script>(function(){try{var q=new URLSearchParams(location.search),r='';try{r=document.referrer?new URL(document.referrer).hostname:''}catch(e){}"
            f"var u='{VIEW_BEACON}?p={pg}'+(r?'&r='+encodeURIComponent(r):'')+'&from='+encodeURIComponent((q.get('utm_content')||q.get('from')||'').slice(0,40))"
            "+(q.get('me')==='1'?'&me=1':'')+(q.get('test')==='1'?'&test=1':'');"
            "fetch(u,{method:'POST',mode:'no-cors',credentials:'omit',keepalive:true,referrerPolicy:'no-referrer'})}catch(e){}})();</script>")
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


# SITE-1 (t566u): the AI page's sample conversation + free CSV come from ONE existing Etsy Search run on build >= 0.2.8,
# fetched read-only by scripts/ai_sample.py into data/ai-sample/. Numbers on the page are computed from these rows.
AI_SAMPLE_DIR = os.path.join(ROOT, "data", "ai-sample")
AI_SAMPLE_MAX = 20   # default maxItems of the buyer path (whole run); the sample CSV is that one run, all of its rows


def load_ai_sample():
    mp = os.path.join(AI_SAMPLE_DIR, "meta.json")
    if not os.path.exists(mp):
        return None
    meta = json.load(open(mp, encoding="utf-8"))
    rows = read_csv(os.path.join(AI_SAMPLE_DIR, "listings.csv"))
    b = tuple(int(x) for x in str(meta.get("build_number") or "0.0.0").split("."))
    if meta.get("status") != "SUCCEEDED" or b < (0, 2, 8) or len(rows) != meta.get("dataset_item_count"):
        raise SystemExit(f"ai-sample: run {meta.get('run_id')} not usable (status/build/row count)")
    for r in rows:
        r["price"] = float(r["price"])
        r["position"] = int(r["position"])
        for k in ("bestseller", "star_seller", "is_ad", "free_shipping"):
            r[k] = r.get(k) == "True"
    rows.sort(key=lambda r: r["position"])
    return {"meta": meta, "rows": rows}


def money(v):
    return f"${v:,.2f}"


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
        if r["category"] != "unknown":   # shops with no category yet are not a category
            by.setdefault(r["category"], []).append(r)
    cat, rows = max(by.items(), key=lambda kv: (len(kv[1]), sum(x["sales_7d_delta"] for x in kv[1]))) if by else (None, [])
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
    share = t10 / tot
    out.append(f"The top 10 shops took <b>{pct(share)}</b> of all 7-day gains we measured "
               f"({plus(t10)} of {plus(tot)}). "
               + ("Momentum is concentrated." if share >= 0.25 else "Gains are spread across many shops, not just the top 10."))
    d = {}
    for r in m:
        d[dept(r["category"])] = d.get(dept(r["category"]), 0) + 1
    d.pop("Unknown", None)
    if d:
        k, v = max(d.items(), key=lambda kv: kv[1])
        if v >= 2:
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
    # share of the gains of shops WITH a category (shops with no category yet are not in any category's total)
    tot = meta.get("total_7d_delta_ge_min_known_category") or meta["total_7d_delta_ge_min"]
    out.append(f"The top 3 categories account for <b>{pct(t3 / tot)}</b> of the 7-day gains of shops with a known category "
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
.top .lang{font-size:14px;font-weight:700;white-space:nowrap;color:var(--mut)}.top .lang b{color:var(--ink)}
@media(max-width:420px){.top .x .fw{display:none}}
.howtr{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px}
.howtr ol{margin:8px 0 10px;padding-left:20px}.howtr li{margin:0 0 8px}.howtr li p{margin:2px 0 0;color:var(--mut);font-size:14.5px}
.howtr .note{font-size:14px;color:var(--mut)}
.rlinks{display:flex;flex-wrap:wrap;gap:8px}.rlinks a{background:var(--chip);color:var(--ink);border-radius:999px;padding:6px 12px;font-weight:600;font-size:14px}
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
NAV = [("index.html", "Overview"), ("movers/", "⚡ Daily Movers"), ("ai.html", "✦ AI"), ("run.html", "★ Custom report"), ("categories.html", "Hot Categories"),
       ("rising.html", "Rising Shops"), ("breakouts.html", "Breakouts"), ("niche.html", "Niche Prices")]


# ---------------------------------------------------------------- TR-1: Turkish home (/tr/)
# Mark t607u (2026-10-08): a Turkish home at /tr/ built from config/i18n/tr.json (strings only). Every number comes from the
# same snapshot as the English home, so the daily publish keeps /tr/ current. Only the home is translated; other reports link
# to the English pages. check_tr() runs the Turkish copy rules (see TR_BANNED / TR_COVERAGE) and pins the TR price line to the
# exact $/¢ amounts of the English home CTA, so a price change on the English side fails the build until tr.json follows.
I18N_DIR = os.path.join(ROOT, "config", "i18n")
TR_PATH = "tr/"


def load_tr():
    return json.load(open(os.path.join(I18N_DIR, "tr.json"), encoding="utf-8"))


def lang_switch(cur):
    if cur == "en":
        return '<span class="lang" aria-label="Language"><b>EN</b> · <a href="/tr/" hreflang="tr" lang="tr">TR</a></span>'
    return '<span class="lang" aria-label="Dil"><a href="/" hreflang="en" lang="en">EN</a> · <b>TR</b></span>'


def hreflang_links():
    return (f'<link rel="alternate" hreflang="en" href="{SITE_URL}">'
            f'<link rel="alternate" hreflang="tr" href="{SITE_URL}{TR_PATH}">'
            f'<link rel="alternate" hreflang="x-default" href="{SITE_URL}">')


def n_tr(x):
    return f"{int(x):,}".replace(",", ".")


def plus_tr(x):
    return "+" + n_tr(x)


def pct_tr(x, d=0):
    return "%" + f"{x * 100:.{d}f}".replace(".", ",")


def dec_tr(x, d=1):
    return f"{x:.{d}f}".replace(".", ",")


def date_tr(iso, T):
    d_ = dt.date.fromisoformat(iso)
    return f"{d_.day} {T['months'][d_.month - 1]} {d_.year}"


MONEY_RX = re.compile(r"\$[\d][\d,]*(?:\.\d+)?|\d+(?:\.\d+)?\s?¢")


def money_tokens(text):
    return sorted(set(t.replace(" ", "") for t in MONEY_RX.findall(html.unescape(re.sub(r"<[^>]+>", " ", text)))))


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
{hreflang_links() if name == "index.html" else ""}
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
<a class="x" href="{X_URL}" rel="noopener"><span class="fw">Follow </span>@EtsyPulse</a>{lang_switch("en")}</div></header>
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
{view_js(name)}
{scripts}
</body></html>
"""


def cta(ctx):
    return f"""<section class="cta">
<h2>Run this on any niche</h2>
<p>Every number here comes from public Etsy data our tools collect. Build the same report for your own keyword or your
competitors' shops, right here: charts, plain-English takeaways and a spreadsheet in a few minutes. No code, no API keys.</p>
<a class="btn" href="{BUILDER}?type=niche&amp;from=cta">Build a niche report</a><a class="btn ghost" href="{BUILDER}?type=rivals&amp;from=cta">Compare competitor shops</a>
<div class="disc">Runs our tools (publicrecords on Apify) on your own Apify account after a free sign-in. Pay per result. From 13¢ for 1 keyword (top 20 listings). $6 per 1,000 listings + 0.5¢ per run. If Etsy blocks a search, you get the most recent cached results, clearly dated, at the same rate; if there's nothing cached, you pay nothing. Apify's free plan includes $5 of usage a month.</div>
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
        return {"publish": "daily_on_new_snapshot", "niche_cadence_days": 7}


def cadence_word(kind="panel"):
    """DAILY-1: shop reports publish every day a newer complete snapshot lands (scripts/box_refresh.py); the niche price
    snapshot (a paid search run) stays weekly. No promised next-refresh date: a skipped (incomplete) snapshot would break it."""
    c = publish_cfg()
    if kind == "niche":
        n = c.get("niche_cadence_days", 7)
        return "weekly" if n == 7 else f"every {n} days"
    return "daily" if c.get("publish") == "daily_on_new_snapshot" else "weekly"


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
    """t619u: no shop-coverage counts in public copy (panel size, measured, read-once). A plain line only."""
    return "New shops get a sales figure after their second daily read."


def coverage_short(meta):
    """t619u: removed from the home hero ('Another N have one read so far and need a second...'). Kept as a no-op."""
    return ""


def fresh_box(snapshot_label, rows_label, cut, kind="panel"):
    what = "This free report refreshes" if kind == "niche" else "Free reports refresh"
    when = "when new sales counters land" if cadence_word(kind) == "daily" else ""
    return (f'<div class="fresh"><div><b>{what} {cadence_word(kind)}{(" " + when) if when else ""}.</b> Want current Etsy data for your own niche or shops? '
            f'<a href="{BUILDER}?from=fresh">Run a report →</a></div>'
            f'<div class="snap">Snapshot <b>{E(snapshot_label)}</b> · <b>{E(rows_label)}</b> · refreshed {cadence_word(kind)}</div></div>')


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
        cat = "" if r["category"] == "unknown" else leaf(r["category"])[:28]   # no "Unknown" label on the card
        nb = d.textbbox((0, 0), name, font=F(34, "Bold"))[2]
        d.text((176 + nb, y + 24), cat, font=F(24, "Medium"), fill=(113, 113, 122))
        val = f"+{r['sales_7d_delta']:,}"
        vw = d.textbbox((0, 0), val, font=F(38, "ExtraBold"))[2]
        d.text((1116 - vw, y + 13), val, font=F(38, "ExtraBold"), fill=ORANGE)
        y += 86
    # DAILY-1: no shop-coverage count on the social card (X shows it under posts that quote other numbers).
    d.text((60, 560), "From public Etsy sales counters",
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
# BEACON-1: page links go through logged worker hand-offs that 302 to the exact URLs above (worker TARGETS keep them identical).
# MCP_URL itself stays direct: it is the address people copy/paste into their AI app (copies are counted by the ai-copy beacon).
MCP_SETUP_LINK = R + "ai-mcp-connect"
CLAUDE_ADD_LINK = R + "ai-claude-connect"
CHATGPT_SETTINGS = "https://chatgpt.com/#settings/Connectors"
# AI-PAGE-2 (t570u): a client is named on the page only after a committed real-test pass on that client and surface.
# claude: PASS on claude.ai web (Mark's account, 2026-10-07 23:50Z; Search run NbmK5QVMvSggPpUIi, 26.9 s, 12 rows;
# lookup_shops 3 calls). The Claude iPhone app fails at "add connector". chatgpt / cursor / vscode: no pass yet, so their
# cards, hero and meta mentions stay off. Re-enable a client by adding its key here (check_public enforces the rest).
TESTED_CLIENTS = ["claude"]
CLIENT_NAMES = {"claude": "Claude", "chatgpt": "ChatGPT", "cursor": "Cursor", "vscode": "VS Code"}
# Names that must not appear in ai.html's visible text unless their client is tested (other apps are not named at all).
CLIENT_NAME_RX = {"chatgpt": r"ChatGPT|OpenAI", "cursor": r"\bCursor\b", "vscode": r"VS ?Code|Copilot",
                  "other": r"\bCodex\b|Claude Code|\bWindsurf\b|\bGemini\b"}


def tested_names():
    n = [CLIENT_NAMES[k] for k in TESTED_CLIENTS]
    return n[0] if len(n) == 1 else ", ".join(n[:-1]) + " or " + n[-1]


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
<h1>Ask AI about any Etsy niche</h1>
<p class="lede">Connect our Etsy tools to {tested_names()}. Ask in plain words about any keyword or niche: your AI pulls fresh public Etsy search and shop data,
answers right in the chat, and turns it into a report when you ask.</p>
<ol class="steps3"><li>Click Connect</li><li>Sign in with Apify (free)</li><li>Ask your AI</li></ol>
<div class="hcta"><a class="hbtn" href="#connect">Connect your AI →</a><small>Runs on your own Apify account. From 13¢ for 1 keyword (top 20 listings). $6 per 1,000 listings + 0.5¢ per run. If Etsy blocks a search, you get the most recent cached results, clearly dated, at the same rate; if there's nothing cached, you pay nothing.</small></div></div>
<div><video autoplay muted loop playsinline preload="metadata" poster="assets/ai/etsypulse-ai-wide-poster.png" width="1200" height="676"
aria-label="Demo: connect Etsy Pulse, sign in with Apify, ask AI who the top sellers are in a few Etsy niches and how Bestsellers price, using public Etsy search data, then get a report">
<source src="assets/ai/etsypulse-ai-wide.webm" type="video/webm"><source src="assets/ai/etsypulse-ai-wide.mp4" type="video/mp4">
<img class="poster" src="assets/ai/etsypulse-ai-wide-poster.png" alt="Demo: ask AI about any Etsy niche with Etsy Pulse, using public Etsy search data"></video></div>
</div></div>"""

    cards = {
        "claude": f"""<div class="app"><h3>Claude</h3><p>Connect on claude.ai in a browser first (the iPhone app can't add it yet).</p>
<div class="acts">{copy("1. Copy link")}<a class="abtn ghost" href="{E(CLAUDE_ADD_LINK)}" target="_blank" rel="noopener">2. Open Claude connectors →</a></div>
<ol><li>Name it <b>Etsy Pulse</b> and paste the link as the server URL.</li><li>Press <b>Add</b>, then <b>Connect</b>, and sign in with Apify.</li>
<li>In Claude: <b>Customize → Connectors → Etsy Pulse → set tools to Always allow.</b> One question uses 3 tools (run, check status, read results), so otherwise Claude stops to ask 3 times.</li></ol></div>""",
        "chatgpt": f"""<div class="app"><h3>ChatGPT</h3><p>Needs Developer mode (Plus, Pro, Business, Enterprise and Edu plans).</p>
<div class="acts">{copy("1. Copy link")}<a class="abtn ghost" href="{E(CHATGPT_SETTINGS)}" target="_blank" rel="noopener">2. Open ChatGPT settings →</a></div>
<ol><li>Go to <b>Apps</b> → <b>Create</b>. No Create button? Turn on <b>Developer mode</b> under Advanced.</li>
<li>Name it <b>Etsy Pulse</b>, paste the link, keep <b>OAuth</b>, press Create and sign in with Apify.</li></ol></div>""",
        "cursor": f"""<div class="app"><h3>Cursor</h3><p>One click adds it. Cursor opens and asks you to confirm.</p>
<div class="acts"><a class="abtn" href="{E(L['cursor'])}">Add to Cursor</a></div>
<ol><li>Then sign in with Apify when Cursor asks.</li></ol></div>""",
        "vscode": f"""<div class="app"><h3>VS Code</h3><p>One click adds it (Copilot agent mode).</p>
<div class="acts"><a class="abtn" href="{E(L['vscode'])}">Add to VS Code</a></div>
<ol><li>Then sign in with Apify when VS Code asks.</li></ol></div>""",
    }
    cards_html = "\n".join(cards[k] for k in TESTED_CLIENTS if k in cards)
    apps = f"""<section id="connect"><h2>Connect in a minute</h2>
<p class="sub">It's Apify's official MCP server (the standard way AI apps plug into tools) with our two Etsy tools already picked:
the Etsy Search Scraper and the Etsy Shop Sales Tracker. Copy the link below and follow the steps.</p>
<div class="urlbox"><code>{E(MCP_URL)}</code>{copy()}</div>
<div class="apps" style="margin-top:14px">
{cards_html}
</div>
<p class="note">Another AI app? <a href="{E(MCP_SETUP_LINK)}" target="_blank" rel="noopener">Open Apify's setup page</a> with our tools already picked.
We list an app here only after we've run a real question through it.</p></section>"""

    # AI-PAGE-2: copy-paste prompts stay small (one keyword, top 5-10, or one shop) so a first answer lands in about 30 s.
    # A 60-row, full-page first try dropped Mark's mobile connection. No multi-niche or many-row runs here.
    uses = [
        ("Top sellers", "Start here: one keyword, done in about 30 seconds.",
         "Top 5 ceramic mugs on Etsy: who sells them, what they charge, and which have a Bestseller badge?",
         "Uses: shop, price, Bestseller badge"),
        ("Price-check a listing", "See where your price sits against the top 10.",
         "I sell a personalized pet toy basket for $18. Pull the top 10 for “pet toy basket” and tell me where my price sits.",
         "Uses: price, position, free shipping"),
        ("Ads vs Bestsellers", "Who's paying to be there, and who earned it.",
         "For “ceramic mug”, which of the top 10 are paid ads and which have a Bestseller badge or Star Seller? What do the badge winners have in common?",
         "Uses: ad flag, Bestseller, Star Seller, reviews, rating"),
        ("Titles and tags", "Write like the listings that rank.",
         "Read the titles of the top 10 “scarf pin brooch” listings and write 3 title options and 13 tag ideas in the same style for mine.",
         "Uses: listing titles. Etsy tags aren't in the data, so tag ideas come from the titles."),
        ("Check one shop", "A quick look at one rival.",
         "Look up the Etsy shop [shop name]: total sales on its shop page, reviews, and how fast it's selling.",
         "Uses: Shop Sales Tracker (total sales, reviews, active listings; sales per day once a shop has been read twice)"),
        ("Charts and plans", "Turn answers into something you can use.",
         "Put that in a report: a price chart, the top shops, and a one-page plan for my first 10 listings.",
         "Your AI makes the chart or file from the rows our tools already returned."),
    ]
    uses_html = "".join(f'<div class="use"><h3>{E(t)}</h3><p>{E(d)}</p><q>{E(p)}</q><div class="f">{E(f)}</div></div>' for t, d, p, f in uses)

    S = files.get("ai_sample")
    convo, tryit_file, tryit_kw = "", "", "a ceramic mug"
    if S:
        M, R = S["meta"], S["rows"]
        kw = M["queries"][0]
        kws = kw if kw.endswith("s") else kw + "s"
        n = len(R)
        top = R[:10]
        when = dt.datetime.fromisoformat(M["finished_at"].replace("Z", "+00:00")).astimezone(ZoneInfo("America/Toronto"))
        day = when.strftime("%b %-d, %Y")

        def tags(r):
            t = [x for x, on in (("Bestseller", r["bestseller"]), ("ad", r["is_ad"])) if on]
            return f" ({', '.join(t)})" if t else ""
        lis = "".join(f"<li>{r['position']}. {E(r['shop_name'])} <b>{money(r['price'])}</b>{tags(r)}</li>" for r in top)
        tp = [r["price"] for r in top]
        nb = sum(r["bestseller"] for r in top)
        na = sum(r["is_ad"] for r in top)
        B = [r["price"] for r in R if r["bestseller"]]
        O = [r["price"] for r in R if not r["bestseller"]]
        if B and O:
            from decimal import Decimal, ROUND_HALF_UP   # exact cents from the CSV strings (35.495 -> $35.50)
            avg = lambda xs: float((sum(Decimal(repr(x)) for x in xs) / len(xs)).quantize(Decimal("0.01"), ROUND_HALF_UP))
            ab, ao = avg(B), avg(O)
            lead = "Yes, on average." if ab > ao else "No, not on average."
            a2 = (f"{lead} {len(B)} of the {n} listings in the run have a Bestseller badge. Average price sellers charge:"
                  f"<ul><li>Bestseller: <b>{money(ab)}</b> ({money(min(B))} to {money(max(B))})</li>"
                  f"<li>The rest: <b>{money(ao)}</b> ({money(min(O))} to {money(max(O))})</li></ul>"
                  f'<div class="t">Small groups: {len(B)} badge listings vs {len(O)} others, from one search.</div>')
        else:
            a2 = f"All {n} listings in the run {'have' if B else 'lack'} a Bestseller badge, so there's nothing to compare."
        convo = f"""<section><h2>What it looks like</h2><p class="sub">A sample conversation with real numbers from one Etsy search run
on {day} (US shopper). Every dollar figure is what Etsy sellers charge.</p>
<div class="convo">
<div class="u">Top 10 {E(kws)} on Etsy: who sells them, what they charge, and which have a Bestseller badge?</div>
<div class="b"><div class="t">Ran Etsy Search Scraper on “{E(kw)}” (US shopper, {n} listings back)</div>The top 10 on Etsy search right now, with what each seller charges:
<ul>{lis}</ul>Sellers charge {money(min(tp))} to {money(max(tp))} across the top 10. {nb} of 10 have a Bestseller badge and {na} are paid ads.</div>
<div class="u">Do Bestseller listings charge more than the rest?</div>
<div class="b">{a2}</div>
<div class="u">Put it in a report with a price chart</div>
<div class="b">Here's your report: a price chart of all {n} listings, the top shops, Bestseller badges and paid ads, from the rows above.
<div class="t">Ask for a document or PDF if your AI app can make files.</div></div>
</div>
<p class="note">Source: publicrecords Etsy Search Scraper, Apify run {E(M['run_id'])} (build {E(M['build_number'])}), “{E(kw)}”, {n} listings, {day}.
Answers in your chat will be worded by your AI and use the data from your own run.</p></section>"""
        tryit_file = (f'Download the {n} “{E(kw)}” listings from that run (<a href="{files["ai_sample_csv"]}">CSV</a>) and drop it into any AI chat. Then ask:'
                      f'<ul><li>“What should I charge for {"an" if kw[:1] in "aeiou" else "a"} {E(kw)}?”</li><li>“Which listings have a Bestseller badge, and what do they have in common?”</li>'
                      f'<li>“Write me a one-page report on this niche.”</li></ul>'
                      f'<p class="note" style="margin-bottom:0">The free file is one search from {day}. Connect above for fresh data on any keyword.')

    costs = f"""<section><h2>How it works, and what it costs</h2>
<div class="costs">
<div><b>Runs through Apify</b><p>Apify is the platform our tools run on. The link is Apify's MCP server with our two Etsy tools picked. You sign in with your own Apify account: free to create, and the free plan includes $5 of usage a month.</p></div>
<div><b>Pay per result</b><p>Etsy Search: From 13¢ for 1 keyword (top 20 listings). $6 per 1,000 listings + 0.5¢ per run. If Etsy blocks a search, you get the most recent cached results, clearly dated, at the same rate; if there's nothing cached, you pay nothing. Apify usage included. On default settings one search returns the top 20 listings in total, even for several keywords; your AI can ask for more at the same rate. Shop Sales Tracker: $0.005 per run + $0.003 per shop ($3 per 1,000 shops), plus Apify platform usage when your AI calls it (Apify bills usage for its always-on Standby mode, which AI apps use).</p></div>
<div><b>Your account, your results</b><p>Every run and its results stay in your Apify account. Sign-in happens on Apify's own screen; we never see your password. Remove access any time in Apify Console → Settings → API &amp; Integrations.</p></div>
</div></section>"""

    if not tryit_file:
        tryit_file = (f'Download our free top-10 listings file (<a href="{files.get("niche_listings", "data/niche-listings-latest.csv")}">CSV</a>) and drop it into any AI chat. Then ask:'
                      '<ul><li>“Which listings have a Bestseller badge, and what do they have in common?”</li><li>“Write me a one-page report on these niches.”</li></ul>'
                      '<p class="note" style="margin-bottom:0">The free file is one sample run, dated above. Connect above for fresh data on any keyword.')
    tryit = f"""<section><div class="try"><b>No account yet? Try it with our free file.</b> {tryit_file}
Rather not use AI? <a href="{BUILDER}?from=ai">Build a report here</a> or <a href="{RUN_FALLBACK}" rel="noopener">run it inside Apify</a>.</p></div></section>"""

    body = (f"<style>{AI_CSS}</style>{apps}<section><h2>What you can do</h2><p class=\"sub\">Six things to ask once you're connected. "
            f"Copy a prompt, swap in your own niche. Keep the first question small (one keyword, top 5 or 10) so it finishes in about 30 seconds; "
            f"bigger asks take longer.</p><div class=\"uses\">{uses_html}</div></section>{convo}{costs}{tryit}")
    return page("ai.html", f"Ask AI about any Etsy niche: connect Etsy Pulse to {tested_names()} | Etsy Pulse",
                f"Connect our Etsy tools to {tested_names()} through Apify's MCP server. Ask about any Etsy keyword or niche and get answers and reports from fresh public Etsy market data. From 13¢ for 1 keyword (top 20 listings). $6 per 1,000 listings + 0.5¢ per run. If Etsy blocks a search, you get the most recent cached results, clearly dated, at the same rate; if there's nothing cached, you pay nothing.",
                body, ctx, hero, scripts=AI_JS)



def tr_shop_rows(rows, maxv, T):
    c_ = T["cols"]
    hd = (f'<div class="hd" role="row"><span>{c_["rank"]}</span><span>{c_["shop"]}</span><span>{c_["cat"]}</span>'
          f'<span class="r">{c_["life"]}</span><span class="r">{c_["pct"]}</span><span>{c_["bar"]}</span>'
          f'<span class="r">{c_["big"]}</span></div>')
    out = [hd]
    for r in rows:
        w = max(2, round(100 * r["sales_7d_delta"] / maxv)) if maxv else 0
        cat = T["unknown_cat"] if r["category"] == "unknown" else leaf(r["category"])
        cls = "row top3" if r["rank"] <= 3 else "row"
        out.append(
            f'<div class="{cls}" role="row"><span class="rk">{r["rank"]}</span>'
            f'<a class="nm" href="{E(r["shop_url"])}" rel="nofollow noopener">{E(r["shop_name"])}</a>'
            f'<span class="meta"><span class="c" title="{E(r["category"])}">{E(cat)}</span>'
            f'<span><b>{n_tr(r["sales_total"])}</b><em>{T["row_life"]}</em></span>'
            f'<span><em>{T["row_week"]}</em><b>{pct_tr(r["gain_pct_of_lifetime"] / 100, 1)}</b><em>{T["row_of_life"]}</em></span></span>'
            f'<span class="bar"><i style="width:{w}%"></i></span>'
            f'<span class="big">{plus_tr(r["sales_7d_delta"])}</span></div>')
    cols = "34px minmax(150px,1.3fr) minmax(140px,1.2fr) 100px 120px minmax(80px,.8fr) 100px"
    return f'<div class="tc" role="table" style="--cols:{cols}">{"".join(out)}</div>'


def tr_insights(P, T):
    m, c, meta = P["movers"], P["categories"], P["meta"]
    out = []
    by = {}
    for r in m[:10]:
        if r["category"] != "unknown":
            by.setdefault(r["category"], []).append(r)
    if by:
        cat, rows = max(by.items(), key=lambda kv: (len(kv[1]), sum(x["sales_7d_delta"] for x in kv[1])))
        if len(rows) >= 2:
            out.append(T["ins_cat_top10"].format(cat=E(leaf(cat)), k=len(rows), gain=plus_tr(sum(x["sales_7d_delta"] for x in rows))))
    a, b = m[0], m[1]
    out.append(T["ins_lead"].format(a=E(a["shop_name"]), a_gain=plus_tr(a["sales_7d_delta"]), b=E(b["shop_name"]),
                                    b_gain=plus_tr(b["sales_7d_delta"]), x=dec_tr(a["sales_7d_delta"] / b["sales_7d_delta"])))
    sm = max(m[:PUBLIC_N], key=lambda r: r["gain_pct_of_lifetime"])
    out.append(T["ins_small"].format(shop=E(sm["shop_name"]), total=n_tr(sm["sales_total"]), gain=plus_tr(sm["sales_7d_delta"]),
                                     pct=pct_tr(sm["gain_pct_of_lifetime"] / 100, 1)))
    t10 = sum(r["sales_7d_delta"] for r in m[:10])
    tot = meta["total_7d_delta_ge_min"]
    out.append(T["ins_share"].format(pct=pct_tr(t10 / tot), t10=plus_tr(t10), tot=plus_tr(tot)) + " "
               + (T["ins_share_hi"] if t10 / tot >= 0.25 else T["ins_share_lo"]))
    ca = c[0]
    out.append(T["ins_cat_lead"].format(cat=E(leaf(ca["category"])), shops=ca["shops_moving"], gain=plus_tr(ca["total_7d_delta"]),
                                        top=E(ca["top_shop"]), pct=pct_tr(ca["top_shop_7d_delta"] / ca["total_7d_delta"])))
    return out


def tr_home(ctx, P):
    """/tr/index.html: the Turkish home. Strings from config/i18n/tr.json, numbers from the same panel cut as the EN home."""
    T = load_tr()
    m, c, meta = P["movers"], P["categories"], P["meta"]
    cut, snap = ctx["cut"], ctx["snap"]
    top = m[0]
    day = date_tr(snap, T)
    url = SITE_URL + TR_PATH
    og = SITE_URL + "og.png?v=" + cut
    title = T["title"].format(date=day)
    desc = T["desc"].format(shop=top["shop_name"], gain=plus_tr(top["sales_7d_delta"]), cat=leaf(c[0]["category"]),
                            cat_gain=plus_tr(c[0]["total_7d_delta"]))
    nv = T["nav"]
    nav = (f'<a href="/tr/" class=on>{nv["home"]}</a>' + (f'<a href="/tr/movers/">{T["movers"]["nav"]}</a>' if dm_days() else "") + f'<a href="/ai.html?from=tr">{nv["ai"]}</a>'
           f'<a href="/{BUILDER}?from=tr-nav">{nv["run"]}</a><a href="/?from=tr#reports">{nv["movers"]}</a>')
    kpis = f"""<div class="kpis">
<div class="kpi"><div class="v">{plus_tr(top['sales_7d_delta'])}</div><div class="l">{T['kpi_top'].format(shop=E(top['shop_name']))}</div></div>
<div class="kpi"><div class="v">{E(leaf(c[0]['category']))}</div><div class="l">{T['kpi_cat'].format(shops=c[0]['shops_moving'], gain=plus_tr(c[0]['total_7d_delta']))}</div></div>
<div class="kpi"><div class="v">{plus_tr(meta['total_7d_delta_ge_min'])}</div><div class="l">{T['kpi_total'].format(min=n_tr(meta['min_lifetime_sales']))}</div></div>
<div class="kpi"><div class="v">{n_tr(meta['categories'])}</div><div class="l">{T['kpi_cats']}</div></div>
</div>"""
    form = (f'<form class="qform" action="/{BUILDER}" method="get" role="search">'
            f'<input name="q" type="search" placeholder="{E(T["form_placeholder"])}" aria-label="{E(T["form_aria"])}" enterkeyhint="go" autocomplete="off">'
            f'<input type="hidden" name="from" value="tr-hero"><button type="submit">{E(T["form_button"])}</button></form>'
            f'<div class="qsub">{E(T["form_sub"])} <a href="{RUN_FALLBACK}?t=tr" rel="noopener">{E(T["form_fallback"])}</a></div>')
    hero = f"""<div class="hero">{PULSE_SVG}<div class="wrap">
<div class="eyebrow">{E(T['eyebrow'].format(date=day))}</div>
<h1>{E(T['h1'])}</h1>
<p class="lede">{E(T['lede'])}</p>
{form}
<div class="chips"><span>{E(T['growth'])}</span></div>
</div></div>"""
    how = f"""<section id="nasil"><h2>{T['how_h2']}</h2><p class="sub">{T['how_sub']}</p><div class="howtr">
<ol><li><b>{T['how_1_t']}</b><p>{T['how_1_p']}</p></li><li><b>{T['how_2_t']}</b><p>{T['how_2_p']}</p></li><li><b>{T['how_3_t']}</b><p>{T['how_3_p']}</p></li></ol>
<p class="note">{T['how_note']}</p>
<p><a class="btn" href="/{BUILDER}?from=tr-how">{T['how_btn']}</a></p>
<p class="note">{T['how_store']} <a href="{R}site-store-search?t=tr">Etsy Search Scraper</a> · <a href="{R}site-store-tracker?t=tr">Etsy Shop Sales Tracker</a></p>
<p class="note">{T['how_ai']} <a href="/ai.html?from=tr">{T['how_ai_link']}</a></p>
</div></section>"""
    rl = "".join(f'<a href="/{h}?from=tr">{E(t)}</a>' for h, t in T["reports"].items() if h in ctx["pages"])
    cta_ = f"""<section class="cta">
<h2>{T['cta_h2']}</h2>
<p>{T['cta_p']}</p>
<a class="btn" href="/{BUILDER}?type=niche&amp;from=tr-cta">{T['cta_niche']}</a><a class="btn ghost" href="/{BUILDER}?type=rivals&amp;from=tr-cta">{T['cta_rivals']}</a>
<div class="disc">{T['price_line']}</div>
</section>"""
    body = f"""{kpis}
<section>{insights_block(tr_insights(P, T), T['takeaways'])}</section>
<section><h2>{T['top10_h2']}</h2><p class="sub">{T['top10_sub']}</p>
{tr_shop_rows(m[:PUBLIC_N], m[0]['sales_7d_delta'], T)}</section>
{how}
<section><h2>{T['reports_h2']}</h2><div class="rlinks">{rl}</div></section>
{cta_}"""
    return f"""<!doctype html>
<html lang="tr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{url}">
{hreflang_links()}
<meta name="theme-color" content="{ORANGE}">
<link rel="icon" href="/assets/favicon.ico" sizes="any"><link rel="icon" type="image/png" sizes="32x32" href="/assets/favicon-32.png">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<meta property="og:type" content="website"><meta property="og:site_name" content="Etsy Pulse"><meta property="og:locale" content="{T['og_locale']}">
<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}">
<meta property="og:url" content="{url}"><meta property="og:image" content="{og}">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:site" content="@EtsyPulse">
<meta name="twitter:title" content="{E(title)}"><meta name="twitter:description" content="{E(desc)}">
<meta name="twitter:image" content="{og}">
<style>{CSS}</style>
<link rel="stylesheet" href="/assets/builder.css?v={cut}-b1">
</head><body>
<header class="top"><div class="wrap"><a class="brand" href="/tr/"><img src="/assets/logo-96.png" alt="" width="30" height="30">Etsy Pulse</a>
<a class="x" href="{X_URL}" rel="noopener">{E(T['follow'])}</a>{lang_switch("tr")}</div></header>
<nav class="tabs" aria-label="Raporlar"><div class="wrap">{nav}</div></nav>
{hero}
<main class="wrap">
{body}
</main>
<footer><div class="wrap">
<p>{T['footer_1']}</p>
<p>{E(T['footer_2'].format(cut=date_tr(cut, T), snap=day))}</p>
</div></footer>
{view_js("tr-home")}
</body></html>
"""


# Turkish copy rules (TR-1). Same bans as the English site, in Turkish: no median/medyan/ortanca, no middle half, no
# "first results page", no "automated"/otomatik label claims, no real-time/gerçek zamanlı/anlık veri, no per-keyword prices,
# no "your Etsy data", no "blocked pages charge nothing" (false since PRICE-2), no shop-coverage counts anywhere on the page.
TR_BANNED = re.compile(r"medyan|ortanca|orta(?:daki)?\s+yar[ıi]|ortadaki\s+%\s?50|(?:\b1\.|birinci|ilk)\s+(?:arama\s+)?(?:sonuç\s+)?sayfa|sayfa\s+1\b|"
                       r"otomati[kz]|otomasyon|gerçek\s+zamanl[ıi]|anl[ıi]k\s+veri|anahtar\s+kelime\s+başına|kelime\s+başına\s+20|"
                       r"etsy\s+veriler(?:in|iniz)\b|etsy\s+verin\b|senin\s+etsy\s+veri|"
                       r"engellenen\s+(?:sayfa|arama)\w*\s+(?:için\s+)?(?:ücretsiz|ücret\s+alınmaz|hiçbir\s+şey|bedava)", re.I)
TR_COVERAGE = re.compile(r"\d[\d.,]*\s*\+?\s*(?:etsy\s+)?mağaza(?:yı|dan|nın)?\s+(?:ölç|takip|izl|oku|tara|panel)|"
                         r"panel(?:imiz)?(?:de|deki)\s+[\d.,]+|[\d.,]+\s+mağazalık|ölçülen\s+[\d.,]+\s+mağaza|[\d.,]+\s+ölçülen\s+mağaza", re.I)
TR_PRICE_OK = re.compile(r"1 anahtar kelime \(ilk 20 ilan\) 13¢'den başlar")


def check_tr(out_dir, en_cta_html, P):
    """TR-1 guards for /tr/index.html (on top of check_public, which already scans tr/ with the English rules)."""
    bad = []
    p = os.path.join(out_dir, "tr", "index.html")
    if not os.path.exists(p):
        raise SystemExit("tr check failed: tr/index.html missing")
    raw = open(p, encoding="utf-8").read()
    vt = visible_text(raw)
    metas = " ".join(html.unescape(x) for x in DESC_RX.findall(raw))
    if '<html lang="tr">' not in raw:
        bad.append('tr/index.html: missing <html lang="tr">')
    if f'<link rel="canonical" href="{SITE_URL}{TR_PATH}">' not in raw:
        bad.append("tr/index.html: canonical must be " + SITE_URL + TR_PATH)
    for f_ in (p, os.path.join(out_dir, "index.html")):
        h_ = open(f_, encoding="utf-8").read()
        if hreflang_links() not in h_:
            bad.append(f"{os.path.relpath(f_, out_dir)}: hreflang en/tr/x-default links missing")
    en_home = open(os.path.join(out_dir, "index.html"), encoding="utf-8").read()
    if 'href="/tr/" hreflang="tr"' not in en_home:
        bad.append("index.html: EN · TR switch missing")
    nb = raw.count(VIEW_BEACON + "?p=tr-home")
    if nb != 1 or raw.count(VIEW_BEACON + "?p=") != 1 or "credentials:'omit'" not in raw:
        bad.append("tr/index.html: needs exactly one cookieless page-view beacon p=tr-home")
    for mt in TR_BANNED.finditer(vt + " " + metas):
        bad.append(f"tr/index.html: banned Turkish copy '{mt.group(0)}'")
    for mt in TR_COVERAGE.finditer(vt + " " + metas):
        bad.append(f"tr/index.html: shop-coverage count '{mt.group(0)}' (no coverage counts on /tr/)")
    if COVERAGE_DESC.search(metas):
        bad.append("tr/index.html: shop-coverage count in a meta description/title (DAILY-1)")
    for mt in BANNED_PRICE.finditer(TR_PRICE_OK.sub(" ", PRICE_OK.sub(" ", vt))):
        bad.append(f"tr/index.html: stale price line '{mt.group(0)}' (PRICE-1)")
    # price line: identical $/¢ amounts to the English home CTA price line (the default buyer path)
    dm = re.search(r'<div class="disc">(.*?)</div>', raw, re.S)
    em = re.search(r'<div class="disc">(.*?)</div>', en_cta_html, re.S)
    if not dm or not em or money_tokens(dm.group(1)) != money_tokens(em.group(1)):
        bad.append(f"tr/index.html: price line amounts {money_tokens(dm.group(1)) if dm else None} != EN home CTA "
                   f"{money_tokens(em.group(1)) if em else None} (update config/i18n/tr.json price_line)")
    if not TR_PRICE_OK.search(vt) and "13¢" in (em.group(1) if em else ""):
        bad.append("tr/index.html: the 13¢ line must keep its scope: '1 anahtar kelime (ilk 20 ilan) 13¢'den başlar'")
    # today's numbers: #1 shop and its gain from this cut
    top = P["movers"][0]
    if E(top["shop_name"]) not in raw or plus_tr(top["sales_7d_delta"]) not in vt:
        bad.append("tr/index.html: today's #1 shop / gain missing")
    if bad:
        raise SystemExit("tr check failed:\n  " + "\n  ".join(bad))
    print("tr check ok: lang=tr, hreflang, beacon tr-home, Turkish bans, price amounts = EN", money_tokens(dm.group(1)))


# ---------------------------------------------------------------- public checks
import re as _re
# t591u (Mark 2026-10-08): the hero says the dataset grows every day instead of the "N gaining, 500+ sales, ranked here"
# and "Gains scaled to 7 days where a shop has N days of reads" chips; check_public keeps those lines from coming back.
GROWTH_LINE = "Our dataset grows every day as we read more Etsy shops."
UNCLEAR_LINES = _re.compile(r"ranked here|gaining,\s*\d+\+\s*sales|gains scaled to 7 days (?:where|from)|scaled to 7 days where", _re.I)
BANNED = _re.compile(r"\bmedian\b|middle half|\bpage[ -]1\b|7-day pace|\biqr\b", _re.I)
# PRICE-1 (t566u): a price on a page must be what the default buyer path charges. MCP-2 is live (Etsy Search 0.2.10
# LRdhNvPXU8Yei84J8, default maxItems 20, owner run 5jf38ytVjcPMi7nm3 = 20 rows = $0.125), so "13¢" is allowed ONLY as
# "13¢ for 1 keyword" with the top-20-listings scope (PRICE_OK is removed before BANNED_PRICE runs). maxItems caps the whole
# run, not each keyword: "13¢ per keyword", "20 per keyword", any ¢/$ "per keyword" price, 63¢ and a bare 13¢ stay banned.
PRICE_OK = _re.compile(r"(?:from\s+)?13\s?¢ for 1 keyword\s*(?:\(top 20 listings\)|,?\s*(?:and\s+)?(?:the\s+)?top 20 listings)", _re.I)
# PRICE-2 (Master read-back 21:11 ET): Etsy Search 0.2.11 serves the most recent cached rows (data_source "cache", as_of)
# when Etsy blocks a keyword on both tries, charged per row delivered, so "Blocked pages charge nothing" is false. Shop Sales
# Tracker is exactly actor-start $0.005 + shop-row $0.003 (0.2.14); the two lookup events are gone. Never "real-time".
STALE_PRICE = _re.compile(r"blocked (?:pages?|searche?s?|reads?) (?:charges?|costs?) nothing|blocked pages are never charged|\bnever charged\b|"
                          r"\blookups?\b|shop[- ]history[- ]records?|velocity[- ]records?|\$0?\.05 per (?:shop|record|lookup)|\$0?\.10? per (?:shop|record|lookup)|"
                          r"\$0\.003 per shop plus|usually under \$0\.02|real[- ]?time|\bautomated\b|🤖", _re.I)
BANNED_PRICE = _re.compile(r"(?:[¢$]|cents?)\s*[\d.,]*\s*(?:per|/|a|for each|each)\s+keyword|\b20 (?:listings )?(?:per|/|for each|each) keyword|\b13\s?¢|\b13 cents\b|\b63\s?¢|\b63 cents\b|≈\s?\$0\.13\b|\$0\.13\b|\$0\.63\b|top 20 listings\)?\s*(?:for|=|≈|:)|\b20 listings\s*(?:for|=|≈|:)", _re.I)


def unesc_link(d):
    return {**d, "url": html.unescape(d["url"])}


def visible_text(h):
    """What a visitor can read: page text plus <title> and meta/og descriptions (scripts, styles and tags removed)."""
    metas = " ".join(_re.findall(r'<meta[^>]+(?:name|property)="(?:description|og:title|og:description|twitter:title|twitter:description)"[^>]+content="([^"]*)"', h))
    body = _re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", h)
    body = _re.sub(r"(?s)<[^>]+>", " ", body)
    return html.unescape(body + " " + metas)


DESC_RX = _re.compile(r'<meta[^>]+(?:name|property)="(?:description|og:description|twitter:description|og:title|twitter:title)"[^>]+content="([^"]*)"')
# DAILY-1: no shop-coverage count in any meta/og/twitter description or title (X shows the home one under our posts).
COVERAGE_DESC = _re.compile(r"measured shops|in our panel|shops (?:tracked|measured|read)|\b\d[\d,]*\+?\s+(?:measured\s+|tracked\s+)?(?:Etsy\s+)?shops\b(?!\.)", _re.I)


def redirect_page(target):
    """MOVERS-2: static redirect for a retired URL (GitHub Pages cannot send a 301)."""
    u = SITE_URL + target
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Etsy Pulse: Daily Movers</title>'
            f'<link rel="canonical" href="{u}"><meta name="robots" content="noindex,follow">'
            f'<meta http-equiv="refresh" content="0; url=/{target}">'
            f'{view_js("movers-old")}<script>location.replace("/{target}"+location.search+location.hash)</script></head>'
            f'<body><p>Moved to <a href="/{target}">Daily Movers</a>.</p></body></html>')


# t619u: shop-coverage counts and the 'one read so far / need a second' line must never come back in visible text,
# meta, or builder strings (panel size, measured count, read-once count, 'measured N of M').
COVERAGE_VISIBLE = _re.compile(
    r"need a second|one read so far|read once so far|have one read|\b\d[\d,]*\s+(?:etsy\s+)?shops in our panel|panel lists|"
    r"measured of [\d,]+|\b\d[\d,]*\s+(?:measured|tracked)\s+shops|\b\d[\d,]*\s+with a measured sales figure|"
    r"\b\d[\d,]*\s+shops have a measured|shops with a measured sales figure:\s*\d|"
    r"\b\d[\d,]*\s+(?:more\s+)?have (?:been read|a measured)", _re.I)


def check_public(out_dir, meta=None):
    """Fail the build if a public file breaks the rules: banned robot words in visible text / CSV headers / builder strings,
    or a report CSV with more than PUBLIC_N rows (niche listings: PUBLIC_N per keyword)."""
    bad = []
    for root, _, fs in os.walk(out_dir):
        for f in fs:
            p = os.path.join(root, f)
            rel = os.path.relpath(p, out_dir)
            if f.endswith(".html"):
                vt = visible_text(open(p, encoding="utf-8").read())
                for mt in BANNED.finditer(vt):
                    bad.append(f"{rel}: banned word '{mt.group(0)}'")
                for mt in BANNED_PRICE.finditer(TR_PRICE_OK.sub(" ", PRICE_OK.sub(" ", vt))):
                    bad.append(f"{rel}: stale price line '{mt.group(0)}' (PRICE-1)")
                for mt in STALE_PRICE.finditer(vt):
                    bad.append(f"{rel}: stale/false price or banned copy '{mt.group(0)}' (PRICE-2)")
                # AI-PAGE-2: only clients with a committed real-test pass are named; no "your Etsy data" (t559u).
                for k, rx in CLIENT_NAME_RX.items():
                    if k not in TESTED_CLIENTS:
                        for mt in _re.finditer(rx, vt):
                            bad.append(f"{rel}: untested client named '{mt.group(0)}' (AI-PAGE-2, TESTED_CLIENTS)")
                raw = open(p, encoding="utf-8").read()
                for k, rx in {"cursor": r"cursor://", "vscode": r"vscode:mcp", "chatgpt": r"chatgpt\.com"}.items():
                    if k not in TESTED_CLIENTS and _re.search(rx, raw):
                        bad.append(f"{rel}: untested client link '{rx}' (AI-PAGE-2)")
                for mt in UNCLEAR_LINES.finditer(vt + " " + " ".join(html.unescape(x) for x in DESC_RX.findall(raw))):
                    bad.append(f"{rel}: removed line '{mt.group(0)}' is back (t591u)")
                for mt in COVERAGE_VISIBLE.finditer(vt + " " + " ".join(html.unescape(x) for x in DESC_RX.findall(raw))):
                    bad.append(f"{rel}: shop-coverage count / removed line '{mt.group(0)}' (t619u)")
                if _re.search(r"your Etsy data", vt, _re.I):
                    bad.append(f"{rel}: 'your Etsy data' (t559u)")
                for dsc in DESC_RX.findall(raw):
                    dsc = html.unescape(dsc)
                    if f == "index.html" and COVERAGE_DESC.search(dsc) or _re.search(r"\d[\d,]*\+?\s+(?:measured|tracked)\s+shops|shops in our panel|\d[\d,]*\+?\s+shops\s+(?:tracked|measured)", dsc, _re.I):
                        bad.append(f"{rel}: shop-coverage count in a meta description/title '{dsc[:80]}' (DAILY-1)")
                # SITE-2: any "N shops in our panel" / measured count must be the live snapshot's value, never a stale literal.
                if meta:
                    cv_ = cov_of(meta)
                    for mt in _re.finditer(r"([\d,]+)\s+shops in our panel|panel lists ([\d,]+) shops|of ([\d,]+) shops in our panel", vt):
                        v_ = int(next(g for g in mt.groups() if g).replace(",", ""))
                        if v_ != cv_.get("panel_shops"):
                            bad.append(f"{rel}: panel count {v_:,} != snapshot manifest {cv_.get('panel_shops')} (SITE-2)")
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
                elif f.startswith("ai-sample-"):   # SITE-1: one run, all rows, must equal the dataset item count
                    S_ = load_ai_sample()
                    if not S_ or S_["meta"]["run_id"] not in f or len(body) != S_["meta"]["dataset_item_count"] or len(body) > AI_SAMPLE_MAX:
                        bad.append(f"{rel}: {len(body)} rows; must equal its run's dataset item count and be <= {AI_SAMPLE_MAX}")
                elif "niche-summary" not in f and len(body) > PUBLIC_N:
                    bad.append(f"{rel}: {len(body)} rows (max {PUBLIC_N})")
            elif f == "builder.js":
                for lit in _re.findall(r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'', open(p, encoding="utf-8").read()):
                    t = visible_text(lit[0] or lit[1])
                    if BANNED.search(t):
                        bad.append(f"{rel}: banned word in text '{t[:60]}'")
                    if STALE_PRICE.search(t):
                        bad.append(f"{rel}: stale/false price or banned copy in text '{t[:60]}' (PRICE-2)")
                    if COVERAGE_VISIBLE.search(t) or _re.search(r"panel_shops|shops_measured\)", t):
                        bad.append(f"{rel}: shop-coverage count in builder text '{t[:60]}' (t619u)")
    # DOMAIN-1: every canonical / og:url / sitemap / robots URL uses SITE_URL; once on the custom domain, no github.io URL
    # may remain in any public page (github.io now 301s to the custom domain).
    for root, _, fs in os.walk(out_dir):
        for f in fs:
            if not f.endswith((".html", ".xml", ".txt")):
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, out_dir)
            raw = open(p, encoding="utf-8").read()
            for mt in _re.finditer(r'<link rel="canonical" href="([^"]+)"|<meta property="og:url" content="([^"]+)"|<loc>([^<]+)</loc>|^Sitemap: (\S+)', raw, _re.M):
                u = next(g for g in mt.groups() if g)
                if not u.startswith(SITE_URL):
                    bad.append(f"{rel}: URL '{u}' does not use the site base {SITE_URL} (DOMAIN-1)")
            if SITE_URL != GITHUB_IO_URL and "geminigeorge22.github.io" in raw:
                bad.append(f"{rel}: legacy github.io URL left after the custom-domain switch (DOMAIN-1)")
    # BEACON-1 guards: every page carries exactly one cookieless page-view beacon; no page links straight to an Apify Store
    # page or the MCP setup page / Claude connector dialog (those go through logged worker /r/ hand-offs).
    direct = _re.compile(r'href="(https://(?:apify\.com/publicrecords/|mcp\.apify\.com/?\?tools=|claude\.ai/new\?modal=add-custom-connector)[^"]*)"')
    for f in sorted(os.listdir(out_dir)):
        if not f.endswith(".html"):
            continue
        h = open(os.path.join(out_dir, f), encoding="utf-8").read()
        nb = h.count(VIEW_BEACON + "?p=")
        if nb != 1:
            bad.append(f"{f}: {nb} page-view beacons (need exactly 1)")
        if "credentials:'omit'" not in h:
            bad.append(f"{f}: page-view beacon must be cookieless (credentials:'omit')")
        for mt in direct.finditer(h):
            bad.append(f"{f}: direct hand-off link {mt.group(1)[:80]} (use the worker /r/ slug)")
    bj = os.path.join(out_dir, "assets", "builder.js")
    if os.path.exists(bj) and "https://apify.com/publicrecords/" in open(bj, encoding="utf-8").read():
        bad.append("assets/builder.js: direct Store link (use /r/site-store-*)")
    # LINKS-1 (Mark t584u): public pages link only www.etsypulse.ca for our own pages: no URL shorteners, no github.io, and
    # workers.dev only as the publicrecords-redirect worker's logged /r/<slug> hand-offs and /e/<event> beacons (BEACON-1).
    short_rx = _re.compile(r"\b(?:tinyurl\.com|bit\.ly|t\.ly|is\.gd|rebrand\.ly|cutt\.ly)/[^\s\"'<)]*", _re.I)
    wd_rx = _re.compile(r"(?:https?:)?//([a-z0-9.-]+\.workers\.dev)(/[^\s\"'<)]*)?", _re.I)
    wd_ok = _re.compile(r"^(?:/r/[a-z0-9-]+(?:\?[^\s\"'<)]*)?|/e/(?:[a-z0-9-]+)?(?:\?[^\s\"'<)]*)?|/?)$")
    for root, _, fs in os.walk(out_dir):
        for f in fs:
            if not f.endswith((".html", ".xml", ".txt", ".js")):
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, out_dir)
            raw = open(p, encoding="utf-8").read()
            for mt in short_rx.finditer(raw):
                bad.append(f"{rel}: URL shortener link '{mt.group(0)[:60]}' (link https://www.etsypulse.ca pages instead)")
            for mt in wd_rx.finditer(raw):
                host, path = mt.group(1).lower(), mt.group(2) or ""
                if host != "publicrecords-redirect.publicrecords.workers.dev" or not wd_ok.match(path):
                    bad.append(f"{rel}: workers.dev URL '{mt.group(0)[:80]}' is not a logged /r/ hand-off or /e/ beacon")
            if f.endswith(".js") and SITE_URL != GITHUB_IO_URL and "geminigeorge22.github.io" in raw:
                bad.append(f"{rel}: legacy github.io URL left after the custom-domain switch (DOMAIN-1)")
    if bad:
        raise SystemExit("public check failed:\n  " + "\n  ".join(bad))
    print("public check ok: no banned words, every report <= %d rows" % PUBLIC_N)


# ---------------------------------------------------------------- DAILY MOVERS (Mark t613u): /movers/, /movers/<date>/, /tr/movers/
# Daily "Etsy's biggest movers": top shops by sales added in the shortest window the panel supports (scripts/movers_rank.py,
# config/movers.json). Data: data/daily-movers/<snapshot_date>/ written by the box publish loop. Pages live in subfolders,
# so every link here is root-absolute. The CTA tagline + its two links come only from config/movers.json.
DM_DIR = os.path.join(ROOT, "data", "daily-movers")


def movers_cfg():
    return json.load(open(os.path.join(ROOT, "config", "movers.json"), encoding="utf-8"))


def dm_days():
    return sorted(d for d in os.listdir(DM_DIR) if re.match(r"\d{4}-\d{2}-\d{2}$", d)
                  and os.path.exists(os.path.join(DM_DIR, d, "movers.csv"))) if os.path.isdir(DM_DIR) else []


def dm_load(day):
    d = os.path.join(DM_DIR, day)
    meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
    cast = lambda rows: [{**r, "rank": int(r["rank"]), "sales_added": int(r["sales_added"]), "sales_before": int(r["sales_before"]),
                          "sales_total": int(r["sales_total"]), "pct_added": float(r["pct_added"] or 0)} for r in rows]
    pct_p = os.path.join(d, "pct.csv")
    nich_p = os.path.join(d, "niches.csv")
    nich = ([{**r, "rank": int(r["rank"]), "sales_added": int(r["sales_added"]), "shops": int(r["shops"]),
              "top_shop_added": int(r["top_shop_added"])} for r in read_csv(nich_p)][:PUBLIC_N]
            if os.path.exists(nich_p) and meta.get("niche_window_days") else [])
    return {"day": day, "meta": meta, "movers": cast(read_csv(os.path.join(d, "movers.csv")))[:PUBLIC_N],
            "pct": cast(read_csv(pct_p))[:PUBLIC_N] if os.path.exists(pct_p) else [], "niches": nich}


def short_date(iso, lang="en", T=None):
    d_ = dt.date.fromisoformat(iso)
    return f"{d_.day} {T['months'][d_.month - 1]}" if lang == "tr" else d_.strftime("%b %-d")


def dm_rows(rows, key, lang="en", T=None):
    L = (T or {}).get("movers", {})
    num = n_tr if lang == "tr" else n
    pl = plus_tr if lang == "tr" else plus
    if key == "sales_added":
        hd_last = L.get("col_added", "Sales added") if lang == "tr" else "Sales added"
    else:
        hd_last = L.get("col_pct", "Growth") if lang == "tr" else "Growth"
    cols_ = (L.get("cols") if lang == "tr" else None) or ["#", "Shop", "Category", "Total sales", "Before", "Size vs #1"]
    if key != "sales_added":
        cols_ = cols_[:4] + [L.get("col_added", "Sales added") if lang == "tr" else "Sales added"] + cols_[5:]
    hd = (f'<div class="hd" role="row"><span>{cols_[0]}</span><span>{cols_[1]}</span><span>{cols_[2]}</span>'
          f'<span class="r">{cols_[3]}</span><span class="r">{cols_[4]}</span><span>{cols_[5]}</span><span class="r">{hd_last}</span></div>')
    maxv = rows[0][key] if rows else 1
    out = [hd]
    for r in rows:
        w = max(2, round(100 * r[key] / maxv)) if maxv else 0
        cat = leaf(r["category"]) if r["category"] else ""
        chip = f'<span class="c" title="{E(r["category"])}">{E(cat)}</span>' if cat else "<span></span>"
        big = pl(r["sales_added"]) if key == "sales_added" else (
            ("%" + dec_tr(r["pct_added"], 1)) if lang == "tr" else f"+{r['pct_added']:.1f}%")
        out.append(
            f'<div class="{"row top3" if r["rank"] <= 3 else "row"}" role="row"><span class="rk">{r["rank"]}</span>'
            f'<a class="nm" href="{E(r["shop_url"])}" rel="nofollow noopener">{E(r["shop_name"])}</a>'
            f'<span class="meta">{chip}'
            f'<span><b>{num(r["sales_total"])}</b><em> {L.get("row_total", "total sales") if lang == "tr" else "total sales"}</em></span>'
            + (f'<span><em>{L.get("row_before", "was ") if lang == "tr" else "was "}</em><b>{num(r["sales_before"])}</b></span></span>' if key == "sales_added"
               else f'<span><b>{pl(r["sales_added"])}</b><em> {L.get("row_sales", "sales") if lang == "tr" else "sales added"}</em></span></span>')
            + f'<span class="bar"><i style="width:{w}%"></i></span><span class="big">{big}</span></div>')
    cols = "34px minmax(150px,1.3fr) minmax(120px,1fr) 110px 150px minmax(80px,.8fr) 100px"
    return f'<div class="tc" role="table" style="--cols:{cols}">{"".join(out)}</div>'


def dm_niche_rows(rows, lang="en", T=None):
    """NICHES (Mark t620u): top niches by sales added. Columns: #, niche, department, shops behind it, top shop, bar, sales added."""
    L = (T or {}).get("movers", {})
    tr = lang == "tr"
    num = n_tr if tr else n
    pl = plus_tr if tr else plus
    cols_ = L.get("niche_cols") if tr else ["#", "Niche", "Department", "Shops", "Top shop", "Size vs #1", "Sales added"]
    nm_tr, dp_tr = L.get("niche_names", {}), L.get("dept_names", {})
    hd = (f'<div class="hd" role="row"><span>{cols_[0]}</span><span>{cols_[1]}</span><span>{cols_[2]}</span>'
          f'<span class="r">{cols_[3]}</span><span>{cols_[4]}</span><span>{cols_[5]}</span><span class="r">{cols_[6]}</span></div>')
    maxv = rows[0]["sales_added"] if rows else 1
    out = [hd]
    for r in rows:
        w = max(2, round(100 * r["sales_added"] / maxv)) if maxv else 0
        key = r["category"].split(" > ")[-1].strip()
        name = nm_tr.get(key, r["niche"]) if tr else r["niche"]
        dk = r["category"].split(" > ")[0].strip()
        dname = dp_tr.get(dk, dept(r["category"])) if tr else dept(r["category"])
        out.append(
            f'<div class="{"row top3" if r["rank"] <= 3 else "row"}" role="row"><span class="rk">{r["rank"]}</span>'
            f'<span class="nm" title="{E(r["category"])}">{E(name)}</span>'
            f'<span class="meta"><span class="c">{E(dname)}</span>'
            f'<span><em>{L.get("row_shops", "shops: ") if tr else "shops: "}</em><b>{num(r["shops"])}</b></span>'
            f'<span class="ld"><em>{L.get("row_top", "top: ") if tr else "top: "}</em><a href="{E(r["top_shop_url"])}" rel="nofollow noopener">{E(r["top_shop"])}</a>'
            f' <b>{pl(r["top_shop_added"])}</b></span></span>'
            f'<span class="bar"><i style="width:{w}%"></i></span><span class="big">{pl(r["sales_added"])}</span></div>')
    cols = "34px minmax(150px,1.2fr) minmax(110px,.9fr) 70px minmax(150px,1.1fr) minmax(80px,.8fr) 100px"
    return f'<div class="tc" role="table" style="--cols:{cols}">{"".join(out)}</div>'


DM_CSS = """.tagline{background:linear-gradient(135deg,#FD5E02,#ff8a3d);color:#fff;border-radius:18px;padding:22px 22px 18px;margin:26px 0}
.tagline h2{color:#fff;margin:0 0 6px;font-size:26px;letter-spacing:-.02em}.tagline p{margin:0 0 14px;color:#fff;opacity:.95}
.tagline .btn{background:#fff;color:#c2410c;display:inline-block;margin:0 8px 8px 0;border-radius:999px;padding:10px 18px;font-weight:800}
.tagline .btn.ghost{background:transparent;color:#fff;border:2px solid #fff}
.tagline .disc{font-size:12.5px;color:#fff;opacity:.9;margin-top:6px}
.dmwin{display:inline-block;background:var(--chip);border-radius:999px;padding:3px 12px;font-size:14px;font-weight:700;margin:0 0 12px}
.jump{display:inline-block;margin:0 0 0 10px;font-weight:700;font-size:14px}
#niches{scroll-margin-top:70px}
.arch{display:flex;flex-wrap:wrap;gap:8px}.arch a{background:var(--chip);color:var(--ink);border-radius:999px;padding:5px 12px;font-weight:600;font-size:14px}
"""


def dm_tagline(lang, T, price_disc, src):
    C = movers_cfg()
    L = cta_l = C["cta_links"]
    if lang == "tr":
        M = T["movers"]
        p, b1, b2 = M["tag_p"], M["tag_btn_browser"], M["tag_btn_ai"]
    else:
        p = ("Any niche, any list of shops: build the same report right here in your browser, "
             "or connect our tools to your AI chat and just ask.")
        b1, b2 = "Run a report in your browser →", "Use it in your AI chat →"
    sep = "&amp;" if "?" in L["browser"] else "?"
    return (f'<section class="tagline"><h2>{E(C["tagline"][lang])}</h2><p>{E(p)}</p>'
            f'<a class="btn" href="{L["browser"]}{sep}from={src}">{E(b1)}</a>'
            f'<a class="btn ghost" href="{cta_l["claude"]}{"&amp;" if "?" in cta_l["claude"] else "?"}from={src}">{E(b2)}</a>'
            f'<div class="disc">{price_disc}</div></section>')


def dm_page(out_dir, D, days, ctx, lang="en", archive=False):
    """One movers page. lang en: /movers/ (latest) or /movers/<day>/ (archive); lang tr: /tr/movers/ (latest)."""
    T = load_tr()
    M = T["movers"]
    day, meta = D["day"], D["meta"]
    w, frm = int(meta["window_days"]), meta["from_date"]
    top = D["movers"][0]
    tr = lang == "tr"
    path = (f"{TR_PATH}movers/" if tr else (f"movers/{day}/" if archive else "movers/"))
    url = SITE_URL + path
    sd = short_date(day, lang, T)
    if tr:
        title = M["title"].format(date=sd)
        h1 = M["h1"].format(date=sd)
        win = (M["win_1"] if w == 1 else M["win_n"]).format(n=w, frm=short_date(frm, "tr", T), to=sd)
        lede = M["lede"]
        desc = M["desc"].format(shop=top["shop_name"], gain=plus_tr(top["sales_added"]), win=win)
        h2a, suba, h2b, subb = M["h2_added"], M["sub_added"], M["h2_pct"], M["sub_pct"].format(min=n_tr(meta.get("pct_min_base_sales") or 1000))
        price = T["price_line"]
        eyebrow = M["eyebrow"]
        method = M["method"].format(n=w)
    else:
        title = f"Etsy's biggest movers, {sd}" + (f" {day[:4]}" if archive else "") + " | Etsy Pulse"
        h1 = f"Etsy's biggest movers, {sd}"
        win = (f"Sales added in 24 hours, {short_date(frm)} → {sd}" if w == 1 else f"Sales added in {w} days, {short_date(frm)} → {sd}")
        lede = "The Etsy shops that added the most sales, read straight from their public Etsy sales counters. New list every day."
        desc = f"{top['shop_name']} added {plus(top['sales_added'])} sales ({win.lower()}). Today's top 10 Etsy movers from public sales counters."
        h2a, suba = "Top 10 by sales added", "Tap a shop to open it on Etsy. Bar = size vs #1."
        h2b = "Biggest jumps for their size"
        subb = f"Sales added as a share of what the shop had sold before, shops with {n(meta.get('pct_min_base_sales') or 1000)}+ sales."
        price = re.search(r'<div class="disc">(.*?)</div>', cta(ctx), re.S).group(1)
        eyebrow = "Etsy Pulse · Daily movers"
        method = (f"Sales added = the shop's public Etsy sales counter on the last day minus the same counter "
                  f"{'one day' if w == 1 else f'{w} days'} earlier, both read on those exact dates. Nothing is scaled or estimated. "
                  "Shops we didn't read on both dates, rounded counters, counters that went down and implausible jumps are left out. "
                  "These are the biggest movers among the shops we read, not all of Etsy.")
    beacon = "tr-movers" if tr else ("movers-day" if archive else "movers-daily")
    if tr:
        nav = (f'<a href="/tr/">{T["nav"]["home"]}</a><a href="/tr/movers/" class=on>{M["nav"]}</a>'
               f'<a href="/ai.html?from=tr-movers">{T["nav"]["ai"]}</a><a href="/{BUILDER}?from=tr-movers-nav">{T["nav"]["run"]}</a>')
        lsw = lang_switch_to("tr", "/movers/", "/tr/movers/")
    else:
        nav = "".join(f'<a href="/{"" if h == "index.html" else h}"{" class=on" if h == "movers/" else ""}>{t}</a>' for h, t in NAV if h in ctx["pages"])
        lsw = lang_switch_to("en", "/movers/", "/tr/movers/")
    alt = (f'<link rel="alternate" hreflang="en" href="{SITE_URL}movers/">'
           f'<link rel="alternate" hreflang="tr" href="{SITE_URL}{TR_PATH}movers/">'
           f'<link rel="alternate" hreflang="x-default" href="{SITE_URL}movers/">') if not archive else ""
    arch = ""
    past = [x for x in reversed(days) if x != day][:30]
    if not tr and past:
        arch = ('<section><h2>Earlier days</h2><div class="arch">' +
                "".join(f'<a href="/movers/{x}/">{short_date(x)}, {x[:4]}</a>' for x in past) + "</div></section>")
    if archive:
        arch = f'<p class="note"><a href="/movers/">See today\'s movers →</a></p>' + arch
    NC = movers_cfg().get("niche_list", {})
    nich_sec, jump = "", ""
    if D.get("niches"):
        nw, nfrm = int(meta["niche_window_days"]), meta["niche_from_date"]
        mins, share = meta.get("niche_min_shops") or NC.get("min_shops", 10), round(100 * (meta.get("niche_max_top_shop_share") or NC.get("max_top_shop_share", 0.5)))
        if tr:
            nwin = (M["win_1"] if nw == 1 else M["win_n"]).format(n=nw, frm=short_date(nfrm, "tr", T), to=sd)
            nh2, nsub, jl = M["h2_niches"], M["sub_niches"].format(n=nw, min=mins, share=share), M["niche_jump"]
        else:
            nwin = (f"Sales added in 24 hours, {short_date(nfrm)} → {sd}" if nw == 1 else f"Sales added in {nw} days, {short_date(nfrm)} → {sd}")
            nh2, jl = "Fastest-growing niches", "Fastest-growing niches ↓"
            nsub = (f"Each niche is an Etsy category. Sales added = what the shops in it added over the same "
                    f"{'24 hours' if nw == 1 else f'{nw} days'}, summed. A niche needs at least {mins} shops with clean reads, "
                    f"and no single shop can be more than {share}% of its total.")
        jump = f'<a class="jump" href="#niches">{E(jl)}</a>'
        nich_sec = (f'<section id="niches"><div class="dmwin">{E(nwin)}</div><h2>{E(nh2)}</h2><p class="sub">{E(nsub)}</p>'
                    f'{dm_niche_rows(D["niches"], lang, T)}</section>')
        method += " " + (M["niche_method"] if tr else
                         "Niches: the same clean counter pairs, summed by the shop's Etsy category and ranked by total sales added. "
                         "Shops without a known category are not counted. These are the niches we read, not all of Etsy.")
    pct_sec = (f'<section><h2>{h2b}</h2><p class="sub">{E(subb)}</p>{dm_rows(D["pct"], "pct_added", lang, T)}</section>'
               if D["pct"] else "")
    og = SITE_URL + "og.png?v=" + ctx["cut"]
    body = f"""<section><div class="dmwin">{E(win)}</div>{jump}<h2>{h2a}</h2><p class="sub">{E(suba)}</p>
{dm_rows(D["movers"], "sales_added", lang, T)}</section>
{nich_sec}
{dm_tagline(lang, T, price, beacon)}
{pct_sec}
{arch}
<section class="method"><h3>{M["method_h"] if tr else "How we count"}</h3><p>{E(method)}</p></section>"""
    foot = (f'<p>{T["footer_1"]}</p><p>{E(T["footer_2"].format(cut=date_tr(ctx["cut"], T), snap=date_tr(day, T)))}</p>' if tr else
            '<p><b>Etsy Pulse</b> is published by publicrecords, and the data comes from our own tools: the publicrecords Etsy Shop Sales Tracker panel '
            '(public shop sales counters). We built them and we sell them, so weigh the links accordingly.</p>'
            f'<p>Counters read through {E(nice_date(day))}. Not affiliated with, endorsed by, or sponsored by Etsy, Inc. Etsy is a trademark of Etsy, Inc.</p>')
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": h1, "description": desc, "url": url,
          "dateModified": day, "temporalCoverage": f"{frm}/{day}", "creator": {"@type": "Organization", "name": "publicrecords"},
          "isAccessibleForFree": True, "license": "https://creativecommons.org/licenses/by/4.0/"}
    html_ = f"""<!doctype html>
<html lang="{lang}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{url}">
{alt}
<meta name="theme-color" content="{ORANGE}">
<link rel="icon" href="/assets/favicon.ico" sizes="any"><link rel="icon" type="image/png" sizes="32x32" href="/assets/favicon-32.png">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<meta property="og:type" content="website"><meta property="og:site_name" content="Etsy Pulse">{f'<meta property="og:locale" content="{T["og_locale"]}">' if tr else ""}
<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}">
<meta property="og:url" content="{url}"><meta property="og:image" content="{og}">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:site" content="@EtsyPulse">
<meta name="twitter:title" content="{E(title)}"><meta name="twitter:description" content="{E(desc)}">
<meta name="twitter:image" content="{og}">
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
<style>{CSS}{DM_CSS}</style>
<link rel="stylesheet" href="/assets/builder.css?v={ctx['cut']}-b1">
</head><body>
<header class="top"><div class="wrap"><a class="brand" href="{'/tr/' if tr else '/'}"><img src="/assets/logo-96.png" alt="" width="30" height="30">Etsy Pulse</a>
<a class="x" href="{X_URL}" rel="noopener">{E(T['follow']) if tr else '<span class="fw">Follow </span>@EtsyPulse'}</a>{lsw}</div></header>
<nav class="tabs" aria-label="Reports"><div class="wrap">{nav}</div></nav>
<div class="hero">{PULSE_SVG}<div class="wrap" style="padding-bottom:30px"><div class="eyebrow">{E(eyebrow)}</div>
<h1>{E(h1)}</h1><p class="lede">{E(lede)}</p></div></div>
<main class="wrap">
{body}
</main>
<footer><div class="wrap">{foot}</div></footer>
{view_js(beacon)}
</body></html>
"""
    p = os.path.join(out_dir, path)
    os.makedirs(p, exist_ok=True)
    open(os.path.join(p, "index.html"), "w", encoding="utf-8").write(html_)
    return path


def lang_switch_to(cur, en_href, tr_href):
    if cur == "en":
        return f'<span class="lang" aria-label="Language"><b>EN</b> · <a href="{tr_href}" hreflang="tr" lang="tr">TR</a></span>'
    return f'<span class="lang" aria-label="Dil"><a href="{en_href}" hreflang="en" lang="en">EN</a> · <b>TR</b></span>'


def build_daily_movers(out_dir, ctx):
    days = dm_days()
    if not days:
        return []
    paths = []
    for dday in days:
        paths.append(dm_page(out_dir, dm_load(dday), days, ctx, "en", archive=True))
    D = dm_load(days[-1])
    paths.insert(0, dm_page(out_dir, D, days, ctx, "en"))
    paths.insert(1, dm_page(out_dir, D, days, ctx, "tr"))
    # public CSVs (top 10 each, dated + latest)
    for k in ("movers", "pct", "niches"):
        rows_ = D[k]
        if rows_:
            for nm in (f"daily-{k}-{days[-1]}.csv", f"daily-{k}-latest.csv"):
                write_public_csv(os.path.join(out_dir, "data", nm), rows_)
    return paths


def check_movers(out_dir, en_cta_html):
    """DAILY MOVERS guards on top of check_public (which already scans every .html for banned copy)."""
    if not dm_days():
        return
    C = movers_cfg()
    bad = []
    ok_desc = _re.compile(r"\d[\d,.]*\s+(?:etsy\s+)?shops\b|shops (?:tracked|measured|read)|in our panel|mağaza", _re.I)
    for root, _, fs in os.walk(out_dir):
        for f in fs:
            p = os.path.join(root, f)
            rel = os.path.relpath(p, out_dir)
            if f != "index.html" or "movers" not in rel:
                continue
            raw = open(p, encoding="utf-8").read()
            tr = rel.startswith("tr" + os.sep)
            if raw.count(VIEW_BEACON + "?p=") != 1 or "credentials:'omit'" not in raw:
                bad.append(f"{rel}: needs exactly one cookieless page-view beacon")
            tag = C["tagline"]["tr" if tr else "en"]
            if E(tag) not in raw:
                bad.append(f"{rel}: CTA tagline from config/movers.json missing")
            for k in ("browser", "claude"):
                if f'href="{C["cta_links"][k]}' not in raw:
                    bad.append(f"{rel}: CTA link {C['cta_links'][k]} missing")
            for dsc in DESC_RX.findall(raw):
                dsc = html.unescape(dsc)
                if ok_desc.search(dsc) or COVERAGE_DESC.search(dsc):
                    bad.append(f"{rel}: coverage count in meta/og '{dsc[:80]}'")
            vt = visible_text(raw)
            if _re.search(r"\b\d[\d,.]*\s+(?:measured\s+|tracked\s+)?shops\b(?!\s+(?:that|with))", vt, _re.I) and not tr:
                bad.append(f"{rel}: shop-coverage count in visible text")
            if tr:
                for mt in TR_BANNED.finditer(vt):
                    bad.append(f"{rel}: banned Turkish copy '{mt.group(0)}'")
                for mt in TR_COVERAGE.finditer(vt):
                    bad.append(f"{rel}: Turkish coverage count '{mt.group(0)}'")
            dm = _re.search(r'<div class="disc">(.*?)</div>', raw, _re.S)
            em = _re.search(r'<div class="disc">(.*?)</div>', en_cta_html, _re.S)
            if not dm or money_tokens(dm.group(1)) != money_tokens(em.group(1)):
                bad.append(f"{rel}: price line amounts differ from the EN home CTA")
            if not f'<link rel="canonical" href="{SITE_URL}' in raw:
                bad.append(f"{rel}: canonical missing")
    for need in ("movers/index.html", os.path.join("tr", "movers", "index.html")):
        if not os.path.exists(os.path.join(out_dir, need)):
            bad.append(f"{need} missing")
        elif dm_load(dm_days()[-1])["niches"]:
            raw = open(os.path.join(out_dir, need), encoding="utf-8").read()
            if raw.count('id="niches"') != 1 or raw.count('href="#niches"') != 1:
                bad.append(f"{need}: niche section (#niches) or its jump link missing")
    if bad:
        raise SystemExit("movers check failed:\n  " + "\n  ".join(bad))
    print("movers check ok:", len(dm_days()), "day(s), tagline + CTA links + beacons + price line")


# ---------------------------------------------------------------- build
def build(out_dir):
    pc = cuts("panel")
    if not pc:
        raise SystemExit("no data/panel/<cut>/ — run scripts/export_panel_cut.py")
    P = load_panel(pc[-1])
    # DAILY-1: cuts are daily now. Breakouts compare with the newest cut at least 7 days older (a week-on-week view);
    # until one exists, with the previous cut. The page names the date it compares with.
    _cur = dt.date.fromisoformat(pc[-1])
    _wk = [x for x in pc[:-1] if (_cur - dt.date.fromisoformat(x)).days >= 7]
    prev = load_panel(_wk[-1] if _wk else pc[-2]) if len(pc) >= 2 else None
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

    S = load_ai_sample()
    if S:
        kwslug = re.sub(r"[^a-z0-9]+", "-", S["meta"]["queries"][0].lower()).strip("-")
        nm = f"ai-sample-{kwslug}-{S['meta']['run_id']}.csv"
        shutil.copyfile(os.path.join(AI_SAMPLE_DIR, "listings.csv"), os.path.join(out_dir, "data", nm))
        files["ai_sample"], files["ai_sample_csv"] = S, f"data/{nm}"

    # panel coverage for the report builder (numbers come from meta.json written at publish time)
    _c = cov_of(meta)
    with open(os.path.join(out_dir, "data", "coverage.json"), "w", encoding="utf-8") as fh:
        json.dump({"snapshot_date": snap, "as_of": nice_date((_c.get("series") or [{"date": snap}])[-1]["date"]),
                   "panel_shops": _c.get("panel_shops"), "shops_read_once": _c.get("shops_read_once"),
                   "shops_measured": _c.get("shops_measured"), "shops_measured_7d_span": _c.get("shops_measured_7d_span"),
                   "series": _c.get("series") or []}, fh)
    pages = ["index.html", "ai.html", BUILDER, "categories.html", "rising.html"]   # MOVERS-2: movers.html folded into /movers/
    if prev:
        pages.append("breakouts.html")
    if N and any((r.get("listings") or 0) >= 20 for r in N["rows"]):
        pages.append("niche.html")
    if dm_days():
        pages.insert(1, "movers/")
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": "Etsy Pulse: Etsy shop movers by 7-day sales gain",
          "description": "Etsy shops and categories with the biggest 7-day sales gains among the shops publicrecords measures, from public shop sales counters. Updated daily.",
          "url": SITE_URL, "dateModified": snap, "temporalCoverage": f"{(dt.date.fromisoformat(snap) - dt.timedelta(days=7)).isoformat()}/{snap}",
          "creator": {"@type": "Organization", "name": "publicrecords"},
          "isAccessibleForFree": True, "license": "https://creativecommons.org/licenses/by/4.0/"}
    ctx = {"pages": pages, "cut": cut, "snap": snap, "ld": ld}
    og_ok = og_image(out_dir, P)
    m, c, r = P["movers"], P["categories"], P["rising"]

    cv = cov_of(meta)
    meas = cv.get("shops_measured")
    # t619u: no shop-coverage counts (panel size / measured / read once) anywhere in public copy.
    src_line = (f'<p class="note">Source: publicrecords Velocity panel, cut {E(cut)}, counters read through {E(snap)}. '
                f'Ranked: shops with ≥{meta["min_lifetime_sales"]} lifetime sales whose sales counter went up.</p>')

    mi, ci, ri = movers_insights(P), category_insights(P), rising_insights(P)
    ni = niche_insights(N) if "niche.html" in pages else []

    # ---- overview
    top = m[0]
    kpis = f"""<div class="kpis">
<div class="kpi"><div class="v">{plus(top['sales_7d_delta'])}</div><div class="l">#1 of the measured shops this week: {E(top['shop_name'])}</div></div>
<div class="kpi"><div class="v">{E(leaf(c[0]['category']))}</div><div class="l">Top category among measured shops, {plus(c[0]['total_7d_delta'])} across {c[0]['shops_moving']} shops</div></div>
<div class="kpi"><div class="v">{plus(meta['total_7d_delta_ge_min'])}</div><div class="l">7-day gain across gaining shops with {meta['min_lifetime_sales']}+ lifetime sales</div></div>
<div class="kpi"><div class="v">{len(c)}</div><div class="l">categories with measured shops gaining</div></div>
</div>"""
    hero = f"""<div class="hero">{PULSE_SVG}<div class="wrap">
<div class="eyebrow">Etsy Pulse · Updated daily · Counters read through {nice_date(snap)}</div>
<h1>Etsy shops on the move this week</h1>
<p class="lede">The biggest 7-day sales jumps among the Etsy shops we measure, read from public Etsy sales counters.</p>
{hero_cta()}
<div class="chips"><span>{E(GROWTH_LINE)}</span></div>
</div></div>"""

    def mini(rows, f_name, f_val, k=3):
        return "<ul class=mini>" + "".join(
            f'<li><span class="nm">{E(f_name(x))}</span><b>{f_val(x)}</b></li>' for x in rows[:k]) + "</ul>"

    CL = custom_links(meta)
    cards = [
        ("categories.html", "Hot Categories", f"{len(c)}", "Where the gains are piling up, by category.",
         mini(c, lambda x: leaf(x["category"]), lambda x: plus(x["total_7d_delta"]))),
        ("rising.html", "Rising Shops", f"{len(r)}", "Fastest measured shops with under 1,000 lifetime sales.",
         mini(r, lambda x: x["shop_name"], lambda x: plus(x["sales_7d_delta"]))),
    ]
    if "movers/" in pages:
        _D = dm_load(dm_days()[-1])
        cards.insert(0, ("movers/", "⚡ Daily Movers", short_date(_D["day"]), "Today's top 10 Etsy shops by sales added. New list every day.",
                         mini(_D["movers"], lambda x: x["shop_name"], lambda x: plus(x["sales_added"]))))
    if "niche.html" in pages:
        nr = [x for x in N["rows"] if (x.get("listings") or 0) >= 20]
        cards.append(("niche.html", "Niche Prices", f"{len(nr)}", f"What top sellers charge, and their badges, in the niches of the top movers on {nice_date(N['cut'])}.",
                      mini(nr, lambda x: x["keyword"], lambda x: f"typical {money(x['price_median'])}")))
    if prev:
        new, _ = breakout_rows(P, prev)
        cards.append(("breakouts.html", "Breakouts", f"{len(new)}", f"New to the top {len(m)} since {prev['cut']}.",
                      mini(new, lambda x: x["shop_name"], lambda x: f"#{x['rank']}")))
    else:
        cards.append(("#breakouts", "Breakouts", "soon", "Shops new to the top list vs the last cut.",
                      '<ul class=mini><li><span class="nm">Starts with the next daily cut: we need two cuts to compare.</span></li></ul>'))
    cards_html = "".join(f'<a class="rcard" href="{h}"><div class="t">{t}<span>{k}</span></div><div class="d">{d}</div>{mn}</a>'
                         for h, t, k, d, mn in cards)
    over_ins = mi[:3] + ci[1:2] + (ni[:1] if ni else [])
    body = f"""{fresh_box(nice_date(snap), f"{len(m)} movers · {len(c)} categories · {len(r)} rising", cut)}
{kpis}
<section>{insights_block(over_ins, "This week's takeaways")}</section>
<section id="reports"><h2>Reports</h2><p class="sub">Each report has its own page, a plain-English read and a CSV.</p>
<div class="grid">{cards_html}</div></section>
<section><h2>Top 10 movers</h2><p class="sub">Biggest 7-day gain in sales. Bar = size vs #1.</p>
{shop_rows(m[:PUBLIC_N], m[0]['sales_7d_delta'], None)}
{more50(CL["movers"]["url"], " movers", CL["movers"]["ready"], "site-home")}</section>
<section class="method" id="method"><h2>How we measure</h2>
<h3>Sales gains</h3><p>{E(meta['method'])} Lifetime sales and the gain come from the public sales counter on each Etsy shop page.
"Week vs lifetime" = the 7-day gain as a share of everything the shop has sold.</p>
<h3>Coverage</h3><p>A shop's sales gain can only be computed once its counter has been read on two different days. {coverage_line(meta)}
This cut ranks shops with at least {meta['min_lifetime_sales']} lifetime sales whose counter went up.
These are not all of Etsy: they are the shops we could measure this week. Categories come from each shop's listings; shops with no category are left out of Hot Categories.</p>
{"<h3>Niche prices</h3><p>The top results of an Etsy search (US shopper, Etsy's best-match order, first results page) for keywords taken from the categories of the leading movers on " + nice_date(N['cut']) + ", captured " + E((N['meta'].get('captured_at') or '')[:10]) + " with our Etsy Search Scraper (Apify run " + E(N['meta']['run_id']) + "). Typical price is the middle price of those results; most charge = the middle 50% of prices.</p>" if "niche.html" in pages else ""}
<h3>Free top {PUBLIC_N}, your own top {CUSTOM_N}</h3><p>Free reports show the top {PUBLIC_N}. For the top {CUSTOM_N}, or any other niche or category, run your own report: the button under each report opens the builder already set up.</p>
<p id="breakouts">Breakouts appear once there are two cuts to compare.</p></section>"""
    # DAILY-1: no shop-coverage count in the description (X shows it under posts; check_public enforces it).
    desc_home = (f"This week's Etsy movers: {top['shop_name']} {plus(top['sales_7d_delta'])} sales in 7 days; "
                 f"{leaf(c[0]['category'])} lead categories ({plus(c[0]['total_7d_delta'])}). From public Etsy sales counters.")
    w = lambda name, html_: open(os.path.join(out_dir, name), "w", encoding="utf-8").write(html_)
    w("index.html", page("index.html", f"Etsy Pulse: Etsy shops on the move this week ({nice_date(snap)})", desc_home, body, ctx, hero))

    def simple_hero(eyebrow, h1, lede):
        return (f'<div class="hero">{PULSE_SVG}<div class="wrap" style="padding-bottom:30px"><div class="eyebrow">{eyebrow}</div>'
                f'<h1>{h1}</h1><p class="lede">{lede}</p>{hero_cta()}<div class="chips"><span>Week to {nice_date(snap)}</span>'
                + '</div></div></div>')

    # ---- MOVERS-2 (Mark t619u): the old 7-day Top Movers page is folded into Daily Movers. movers.html stays only as a
    # redirect (GitHub Pages has no 301: canonical + meta refresh + location.replace, query string kept) and is not in nav/sitemap.
    w("movers.html", redirect_page("movers/"))

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
                                 f"Etsy shops new to the top 10 movers since {prev['cut']}.", body, ctx,
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
        body = f"""{fresh_box(nice_date((N['meta'].get('captured_at') or N['cut'])[:10]), f"{N['meta']['rows']['listings']} listings · {len(nr)} niches", cut, "niche")}<section>{insights_block(ni)}{report_btn("site-niche", "Etsy Search Scraper", "Get this price breakdown for your own keyword: the top results as a spreadsheet.")}</section>
<section><h2>What top sellers charge in the niches of the top movers</h2><p class="sub">Keywords are the categories of the leading 7-day movers on {nice_date(N['cut'])}. Prices are what Etsy shows US shoppers in the top search results (Etsy's best-match order).</p>
<div class="niche">{''.join(cards)}</div>
{more50(niche_link(src="site-niche-top50-any"), " results", True)}
{dl(files['niche_summary'], f"Download summary CSV ({len(N['rows'])} keywords)")} {dl(files['niche_listings'], f"Download listings CSV (top {PUBLIC_N} per keyword, {files['niche_listings_rows']} rows)")}
<p class="note">Source: publicrecords Etsy Search Scraper, Apify run {E(N['meta']['run_id'])}{(' + ' + ', '.join(E(x) for x in N['meta'].get('extra_run_ids', []))) if N['meta'].get('extra_run_ids') else ''}, captured {E((N['meta'].get('captured_at') or '')[:16].replace('T', ' '))} UTC, {N['meta']['rows']['listings']} listings.{E(miss_note)}</p></section>"""
        w("niche.html", page("niche.html", f"Etsy niche prices: {', '.join(x['keyword'] for x in nr)} | Etsy Pulse",
                             f"What top Etsy sellers charge, how prices spread and how many have a Bestseller badge, in the niches of the top movers on {nice_date(N['cut'])}.",
                             body, ctx, simple_hero("Report · Niche Prices", "Niche Prices", f"What top Etsy sellers charge in the niches of the top movers on {nice_date(N['cut'])}.")))

    # ---- report builder (run.html): Sign in with Apify, run our Actors on the visitor's account, report in-page
    builder_hero = (f'<div class="hero">{PULSE_SVG}<div class="wrap" style="padding-bottom:52px"><div class="eyebrow">Etsy Pulse · Custom report</div>'
                    '<h1>Build your own Etsy report</h1><p class="lede">Pick a report, type a niche or a few shops, press Run. '
                    'Charts, plain-English takeaways and a spreadsheet in a few minutes. No code, no API keys.</p></div></div>')
    body = """<div id="builder" class="bld"><noscript><div class="berr">The report builder needs JavaScript. You can still run our tools directly on Apify:
<a href="https://publicrecords-redirect.publicrecords.workers.dev/r/site-store-search">Etsy Search Scraper</a> · <a href="https://publicrecords-redirect.publicrecords.workers.dev/r/site-store-tracker">Etsy Shop Sales Tracker</a>.</div></noscript></div>
<div id="progress" hidden></div>
<div id="report" hidden></div>
<section class="how-sec"><h2>How it works</h2><p class="sub">Three steps. Your results and your spend stay in your own Apify account.</p>
<div class="how">
<div><b>Sign in with Apify (free)</b><p>Apify is the platform our tools run on. New accounts are free, no credit card, and the free plan includes $5 of usage every month.</p></div>
<div><b>Press Run</b><p>The report runs on your account. Keyword reports: $6 per 1,000 listings + 0.5¢ per run, Apify platform usage included. If Etsy blocks a search, you get the most recent cached results, clearly dated, at the same rate; if there's nothing cached, you pay nothing. Shop reports: $0.005 per run + $0.003 per shop ($3 per 1,000 shops), Apify platform usage included. The price updates as you change options, and you see “about $X, at most $Y” for the exact number of listings you ask for before you start.</p></div>
<div><b>Read it, download it</b><p>Takeaways, charts and a sortable table appear right here. Download the spreadsheet (CSV), or print / save as PDF. Your runs and data also stay in your Apify account.</p></div>
</div>
<p class="note">Sign-in uses Apify's own OAuth screen; we never see your password. Apify offers one permission level (full account access): this page uses it only to start the report you asked for and read its results. The key stays in this browser tab and is gone when you close it. Remove the approval any time in Apify Console → Settings → API &amp; Integrations.</p></section>"""
    w(BUILDER, page(BUILDER, "Build your own Etsy report: prices, bestsellers, top shops, shop sales | Etsy Pulse",
                    "Type a niche or a few Etsy shops and get a live report: price bands, Bestseller share, top shops, sales pace, CSV. Free Apify sign-in, no code.",
                    body, ctx, builder_hero, scripts=f'<script src="assets/builder.js?v={cut}-b7" defer></script>'))

    # ---- AI page
    w("ai.html", ai_page(ctx, files))

    # ---- TR-1: Turkish home
    os.makedirs(os.path.join(out_dir, "tr"), exist_ok=True)
    w(os.path.join("tr", "index.html"), tr_home(ctx, P))

    # ---- DAILY MOVERS (t613u)
    dm_paths = build_daily_movers(out_dir, ctx)

    # ---- seo files
    with open(os.path.join(out_dir, "robots.txt"), "w") as fh:
        fh.write(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}sitemap.xml\n")
    with open(os.path.join(out_dir, "sitemap.xml"), "w") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for p in pages:
            fh.write(f"  <url><loc>{SITE_URL}{'' if p == 'index.html' else p}</loc><lastmod>{snap}</lastmod></url>\n")
        fh.write(f"  <url><loc>{SITE_URL}{TR_PATH}</loc><lastmod>{snap}</lastmod></url>\n")
        for p in dm_paths:
            if p != "movers/":
                fh.write(f"  <url><loc>{SITE_URL}{p}</loc><lastmod>{p.strip('/').split('/')[-1] if p[-11:-1].count('-') == 2 else dm_days()[-1]}</lastmod></url>\n")
        fh.write("</urlset>\n")
    open(os.path.join(out_dir, ".nojekyll"), "w").close()
    report = {"cut": cut, "snapshot": snap, "pages": pages, "locales": {"tr": TR_PATH + "index.html"}, "og": og_ok,
              "rows": {"movers": len(m), "categories": len(c), "rising": len(r),
                       "niche_keywords": len([x for x in (N["rows"] if N else []) if (x.get("listings") or 0) >= 20])},
              "breakouts": bool(prev), "public_max_rows": PUBLIC_N, "daily_movers": dm_paths,
              "custom_links": {"movers": unesc_link(CL["movers"]), "rising": unesc_link(CL["rising"]),
                               "categories": {k: unesc_link(v) for k, v in CL["categories"].items()},
                               "niche": {x["keyword"]: html.unescape(niche_link(x["keyword"], "site-niche-top50")) for x in (N["rows"] if N else [])
                                         if (x.get("listings") or 0) >= 20}}}
    with open(os.path.join(out_dir, "build.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    check_public(out_dir, meta)
    check_tr(out_dir, cta(ctx), P)
    check_movers(out_dir, cta(ctx))
    print(json.dumps(report))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "_site"))
    build(ap.parse_args().out)
