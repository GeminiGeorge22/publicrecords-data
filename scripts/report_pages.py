"""REPORTS-1 (Mark t778u): search-friendly, dated English report pages.

  * etsy-prices-<slug>.html  "Typical Etsy prices for <product type>" from data/price-pages/<cut>.json (aggregates of one
    dated Etsy Search read per keyword; >= min_listings listings or no page)
  * etsy-prices.html          the product types side by side (same read)
  * reports.html              index of every niche report page
  * how-we-measure.html       methods page (sales counters, exact pairs, balance gate, search reads)

English only for now: these pages carry <meta name="ep-lang" content="en-only">, no hreflang/redirect script, and a language
button that opens the other languages' home (lang_menu key=None). check_lang skips them; check_reports below checks them.
Called from build_site.build() with build_site's globals (H) so the shared page shell, CSS, nav and footer stay one copy."""
import json
import os
import re

EN_ONLY = '<meta name="ep-lang" content="en-only">'
TABLE_CSS = ("<style>.rp table{border-collapse:collapse;width:100%;margin:12px 0 20px;font-size:15px}"
             ".rp th,.rp td{border-bottom:1px solid #eee;padding:8px 6px;text-align:left;vertical-align:top}"
             ".rp td.r,.rp th.r{text-align:right;font-variant-numeric:tabular-nums}.rp .asof{display:inline-block;background:#fff3eb;"
             "border:1px solid #fd5e02;border-radius:6px;padding:4px 10px;font-weight:600;margin:6px 0 14px}"
             ".rp h2{margin-top:28px}.rp .cov{background:#fafafa;border-left:4px solid #fd5e02;padding:10px 14px;margin:16px 0}</style>")


def slug(kw):
    return re.sub(r"[^a-z0-9]+", "-", kw.lower()).strip("-")


def nice(iso):
    import datetime as dt
    d = dt.date.fromisoformat(iso)
    return d.strftime("%b ") + str(d.day) + d.strftime(", %Y")


def latest_price_cut(root):
    d = os.path.join(root, "data", "price-pages")
    if not os.path.isdir(d):
        return None
    fs = sorted(f for f in os.listdir(d) if f.endswith(".json"))
    return json.load(open(os.path.join(d, fs[-1]), encoding="utf-8")) if fs else None


def shell(H, name, title, desc, h1, lede, body, ctx):
    """build_site.page() with the English-only head and language button."""
    E = H["E"]
    hero = (f'<div class="hero">{H["PULSE_SVG"]}<div class="wrap" style="padding-bottom:30px"><div class="eyebrow">Etsy Pulse report</div>'
            f'<h1>{E(h1)}</h1><p class="lede">{lede}</p></div></div>')
    out = H["page"](name, title, desc, TABLE_CSS + f'<div class="rp">{body}</div>', ctx, hero)
    out = out.replace(H["hreflang_links"](name) + H["lang_redirect_js"]("en", name), EN_ONLY)
    out = out.replace(H["lang_menu"]("en", name), H["lang_menu"]("en", None, "/" + name))
    return out


def money(v):
    return f"${v:,.2f}"


def price_page(H, P, r, ctx):
    E = H["E"]
    kw, n = r["keyword"], r["listings"]
    name = f"etsy-prices-{slug(kw)}.html"
    rd = nice(P["read_date"])
    title = f"Typical Etsy prices for {kw} ({rd})"
    desc = (f"What {kw} sell for on Etsy: typical price {money(r['price_typical'])}, half of listings between "
            f"{money(r['price_p25'])} and {money(r['price_p75'])}. Read {rd} from {n} Etsy search results.")
    lede = (f"The typical price on the first page of Etsy search results for “{E(kw)}” was <b>{money(r['price_typical'])}</b>. "
            f"Half of the {n} listings were priced between {money(r['price_p25'])} and {money(r['price_p75'])}.")
    bands = "".join(f"<tr><td>{E(b)}</td><td class=r>{c}</td><td class=r>{round(100*c/n)}%</td></tr>" for b, c in r["bands"])
    hist = P.get("history", {}).get(kw, [])
    hist_html = ""
    if hist:
        rows = "".join(f"<tr><td>{nice(h['read_date'])}</td><td class=r>{h['listings']}</td><td class=r>{money(h['price_typical'])}</td>"
                       f"<td class=r>{money(h['price_p25'])} – {money(h['price_p75'])}</td></tr>" for h in hist)
        rows += (f"<tr><td><b>{rd}</b> (this page)</td><td class=r>{n}</td><td class=r><b>{money(r['price_typical'])}</b></td>"
                 f"<td class=r>{money(r['price_p25'])} – {money(r['price_p75'])}</td></tr>")
        hist_html = (f"<h2>Earlier reads of the same search</h2><p>Each row is a separate read of the first results page. Etsy reshuffles "
                     f"which listings appear there, so a change between reads shows a different mix of listings, not shops changing their prices.</p>"
                     f"<table><tr><th>Read on</th><th class=r>Listings</th><th class=r>Typical price</th><th class=r>Half of listings between</th></tr>{rows}</table>")
    body = f"""<p class="asof">Data as of {rd} · one read of Etsy search results · not live</p>
<h2>Prices at a glance</h2>
<table>
<tr><th>Measure</th><th class=r>{E(kw)}, read {rd}</th></tr>
<tr><td>Typical price (half of listings cost less, half more)</td><td class=r><b>{money(r['price_typical'])}</b></td></tr>
<tr><td>Half of listings priced between</td><td class=r>{money(r['price_p25'])} – {money(r['price_p75'])}</td></tr>
<tr><td>Cheapest / priciest listing seen</td><td class=r>{money(r['price_min'])} / {money(r['price_max'])}</td></tr>
<tr><td>Listings with free shipping</td><td class=r>{r['free_shipping']} of {n}</td></tr>
<tr><td>Listings with a Bestseller badge</td><td class=r>{r['bestseller']} of {n}</td></tr>
<tr><td>Listings from Star Sellers</td><td class=r>{r['star_seller']} of {n}</td></tr>
<tr><td>Different shops among the listings</td><td class=r>{r['shops']}</td></tr>
</table>
<h2>Price bands</h2>
<table><tr><th>Price</th><th class=r>Listings</th><th class=r>Share</th></tr>{bands}</table>
{hist_html}
<div class="cov"><h2 style="margin-top:0">Coverage: what this is and isn't</h2>
<p>We searched Etsy for “{E(kw)}” on {rd} (US results, Etsy's default relevance order) with the publicrecords Etsy Search Scraper
and recorded the {n} listings on the first results page, with their listed price in US dollars. Etsy reported
{r['etsy_total_results']:,} results for that search, so this is a snapshot of what a shopper sees first, not every listing.
{"The keyword came from the Etsy category “" + E(r['from_category']) + "”, picked from the Etsy categories of the top shops in our movers list that week." if r.get('from_category') else ""}
Prices are the listed price shown in the search results at the time of the read. We publish a product type
only when one read has at least {P['min_listings']} priced listings. Our own shops are excluded. Read ID: Apify run {E(P['run_id'])}.</p>
<p><a href="how-we-measure.html">How we measure</a> · <a href="etsy-prices.html">Compare product types</a> · <a href="reports.html">All niche reports</a></p></div>
<h2>Check your own niche</h2><p>This page is one dated read. To read today's results for your own keyword, <a href="{H['BUILDER']}?type=niche&amp;q={E(kw)}&amp;from=price-{slug(kw)}">run a niche report</a>.</p>"""
    return name, title, shell(H, name, title, desc, f"Typical Etsy prices for {kw}", lede, body, ctx)


def compare_page(H, P, ctx):
    E = H["E"]
    rd = nice(P["read_date"])
    rows_ = sorted(P["pages"], key=lambda r: -r["price_typical"])
    rows = "".join(f"<tr><td><a href=\"etsy-prices-{slug(r['keyword'])}.html\">{E(r['keyword'])}</a></td><td class=r>{r['listings']}</td>"
                   f"<td class=r><b>{money(r['price_typical'])}</b></td><td class=r>{money(r['price_p25'])} – {money(r['price_p75'])}</td>"
                   f"<td class=r>{r['free_shipping']} of {r['listings']}</td><td class=r>{r['bestseller']} of {r['listings']}</td></tr>" for r in rows_)
    hi, lo = rows_[0], rows_[-1]
    name = "etsy-prices.html"
    title = f"Typical Etsy prices by product type, compared ({rd})"
    desc = f"Typical Etsy prices for {len(rows_)} product types side by side, from one dated read of Etsy search results on {rd}."
    lede = (f"From the same read on {rd}: the typical “{E(hi['keyword'])}” listing was {money(hi['price_typical'])}, "
            f"the typical “{E(lo['keyword'])}” listing {money(lo['price_typical'])}.")
    body = f"""<p class="asof">Data as of {rd} · one read per product type · not live</p>
<table><tr><th>Search</th><th class=r>Listings</th><th class=r>Typical price</th><th class=r>Half of listings between</th><th class=r>Free shipping</th><th class=r>Bestseller badge</th></tr>{rows}</table>
<div class="cov"><h2 style="margin-top:0">Coverage</h2><p>Each row is the first page of US Etsy search results for that keyword, read once on {rd}
(Apify run {E(P['run_id'])}), {sum(r['listings'] for r in rows_)} listings in total. Typical price = half of the listings cost less, half more.
A product type is listed only when its read has at least {P['min_listings']} priced listings. Product types we read but left out:
{", ".join(E(s['keyword']) + " (" + E(s['why']) + ")" for s in P['skipped']) or "none"}.</p>
<p><a href="how-we-measure.html">How we measure</a> · <a href="reports.html">All niche reports</a></p></div>"""
    return name, title, shell(H, name, title, desc, "Typical Etsy prices by product type", lede, body, ctx)


def index_page(H, P, items, ctx, sales_items=()):
    E = H["E"]
    lis = "".join(f'<li><a href="{n}">{E(t)}</a></li>' for n, t in items)
    name = "reports.html"
    title = "Etsy niche reports: prices and sales, dated"
    desc = "Every Etsy Pulse niche report in one place: typical Etsy prices by product type and shops gaining sales by niche, each dated."
    body = f"""<p>Each report is dated and says what it covers. Nothing here is live: every number comes from one dated read.</p>
<h2>Etsy shops gaining sales</h2><ul>{"".join(f'<li><a href="{n}">{E(t)}</a></li>' for n, t in sales_items)}</ul>
<h2>Typical Etsy prices</h2><ul>{lis}</ul>
<p><a href="how-we-measure.html">How we measure</a></p>"""
    return name, title, shell(H, name, title, desc, "Etsy niche reports", "Typical prices and sales movement by niche, each with its date and coverage.", body, ctx)


def measure_page(H, meta, P, ctx):
    E = H["E"]
    tc = H["tracked_count"](meta)
    snap = nice(meta["snapshot_date"])
    name = "how-we-measure.html"
    title = "How Etsy Pulse measures Etsy sales and prices"
    desc = "How we read Etsy shop sales counters and search prices, what counts as sales added, and when we hold data back."
    body = f"""<h2>Shop sales: public sales counters</h2>
<p>Every Etsy shop page shows a public lifetime sales count. Our tool, the publicrecords Etsy Shop Sales Tracker, reads that counter
for each shop it tracks and stores the number with the date it was read. Tracking {tc:,} Etsy shops as of the {snap} snapshot.
The tracker does not see orders, revenue or private shop data: only the public counter.</p>
<h2>Sales added = two exact reads, two dates</h2>
<p>“Sales added” is the counter on one date minus the counter on an earlier date, for example Oct 16 → Oct 17. We only use a shop
when both reads are exact (Etsy shows rounded counts such as “10k” on big shops; those are left out), were taken on those exact dates,
and the counter did not go down. Jumps bigger than half the earlier count, and vintage-shop events, are dropped. Nothing is projected or estimated.</p>
<h2>When we hold data back</h2>
<p>The tracker reads shops in a rolling order. On some days the shops read on both dates lean toward part of the alphabet, which would
make a ranking lopsided. Each snapshot is checked: the shops with exact pairs must match the whole tracked set across five
name buckets (0-9, A-C, D-L, M-S, T-Z). If a snapshot fails that check, it is held: it is not used for new sales rankings, and every report shows the date
of the data it uses.</p>
<h2>Niches</h2>
<p>A niche is either the shop's Etsy category or, where a report says so, the words in the shop's own headline. Each niche report names its rule,
its date and how many shops it covers.</p>
<h2>Prices: Etsy search reads</h2>
<p>Price reports come from the publicrecords Etsy Search Scraper: one search on Etsy (US results, default relevance order), recording each
listing on the first results page with its listed price, badges and free-shipping flag. “Typical price” means half the listings cost less and half more.
“Half of listings between” is the range that holds the middle two quarters of listings by price. We publish a product type only when one read has at least
{P['min_listings'] if P else 50} priced listings.</p>
<h2>What we leave out</h2>
<p>Our own Etsy shop is excluded from the price reports. We are not affiliated with Etsy. We built and sell the tools that collect this data, so weigh our links accordingly.</p>
<p><a href="reports.html">All niche reports</a></p>"""
    return name, title, shell(H, name, title, desc, "How we measure", "Where every Etsy Pulse number comes from, and when we hold one back.", body, ctx)


def latest_sales_cut(root):
    d = os.path.join(root, "data", "sales-niches")
    if not os.path.isdir(d):
        return None
    fs = sorted(f for f in os.listdir(d) if f.endswith(".json"))
    for f in reversed(fs):
        S = json.load(open(os.path.join(d, f), encoding="utf-8"))
        if S.get("balanced") is True:   # held (unbalanced) snapshots never get a page
            return S
    return None


def sales_page(H, S, r, ctx):
    E = H["E"]
    fd, td = nice(S["from_date"]), nice(S["snapshot_date"])
    span = f"{fd[:-6]} → {td}"
    name = f"etsy-shops-gaining-sales-{r['slug']}.html"
    title = f"Etsy shops gaining sales in {r['niche']} ({span})"
    desc = (f"Which Etsy {r['niche']} shops added the most sales {span}, from exact public sales counter reads on both days. "
            f"Dated, with coverage and method.")
    t0 = r["top"][0]
    lede = (f"Between {fd[:-6]} and {td}, the {r['shops_gaining']:,} gaining shops in this group added <b>{r['sales_added']:,} sales</b>. "
            f"The biggest gain: {E(t0['shop'])}, +{t0['sales_added']:,}.")
    rows = "".join(f"<tr><td class=r>{t['rank']}</td><td><a href=\"{E(t['shop_url'])}\" rel=\"nofollow noopener\">{E(t['shop'])}</a>"
                   f"<br><small>{E(t['headline'])}</small></td><td class=r><b>+{t['sales_added']:,}</b></td><td class=r>{t['sales_total']:,}</td></tr>"
                   for t in r["top"])
    others = [x for x in S["pages"] if x["slug"] != r["slug"]]
    body = f"""<p class="asof">Data as of {td} · sales added {span} · not live</p>
<h2>Top {len(r['top'])} by sales added, {span}</h2>
<table><tr><th class=r>#</th><th>Shop (its Etsy headline)</th><th class=r>Sales added</th><th class=r>Lifetime sales on {td[:-6]}</th></tr>{rows}</table>
<h2>The group at a glance</h2>
<table>
<tr><td>Shops in this group with an exact read on both days</td><td class=r>{r['shops']:,}</td></tr>
<tr><td>…of which added at least one sale</td><td class=r>{r['shops_gaining']:,}</td></tr>
<tr><td>Sales added by the whole group, {span}</td><td class=r><b>{r['sales_added']:,}</b></td></tr>
<tr><td>Share of those sales from the top 10 above</td><td class=r>{round(100 * r['top10_share'])}%</td></tr>
<tr><td>Share from the single biggest gainer</td><td class=r>{round(100 * r['top_shop_share'], 1)}%</td></tr>
</table>
<div class="cov"><h2 style="margin-top:0">Coverage: which shops, and how we read them</h2>
<p><b>Who is in this group:</b> shops whose own Etsy shop headline contains {r['rule']}. We group by headline words because Etsy's
category is known for too few of the shops we read. A headline-word group is broader than an Etsy category: for example a supply
shop that mentions {E(r['niche'])} in its headline is included. A shop can be in more than one group.</p>
<p><b>How the sales were read:</b> the public lifetime sales counter on each shop's Etsy page, read on {fd} and again on {td}.
Sales added = the second count minus the first. Only shops with an exact count on both days are used (rounded counts, counters that went down,
jumps bigger than half the earlier count and vintage-shop events are left out). Nothing is projected or estimated.</p>
<p><b>Why this date:</b> {td} is the newest snapshot that passed our balance check (the shops read on both days match the whole tracked set
across name buckets). Later snapshots did not pass, so they are held and not used here. These {r['shops']:,} shops are the ones in this group
our tracker read on both days, not every {E(r['niche'])} shop on Etsy. We publish a group only when at least {S['min_shops']} shops qualify.
Our own shop is excluded.</p>
<p><a href="how-we-measure.html">How we measure</a> · <a href="reports.html">All niche reports</a></p></div>
<h2>Other groups, same dates</h2><ul>{"".join(f'<li><a href="etsy-shops-gaining-sales-{x["slug"]}.html">Etsy shops gaining sales in {E(x["niche"])}</a></li>' for x in others)}</ul>
<h2>Track your own shops</h2><p>This page is one dated read. To read today's counters for shops you name, <a href="{H['BUILDER']}?type=velocity&amp;from=sales-{r['slug']}">run a shop report</a>.</p>"""
    return name, title, shell(H, name, title, desc, f"Etsy shops gaining sales in {r['niche']}", lede, body, ctx)


def sales_overview(H, S, ctx):
    E = H["E"]
    fd, td = nice(S["from_date"]), nice(S["snapshot_date"])
    span = f"{fd[:-6]} → {td}"
    rs = sorted(S["pages"], key=lambda x: -x["sales_added"])
    rows = "".join(f"<tr><td><a href=\"etsy-shops-gaining-sales-{x['slug']}.html\">{E(x['niche'])}</a></td><td class=r>{x['shops']:,}</td>"
                   f"<td class=r>{x['shops_gaining']:,}</td><td class=r><b>{x['sales_added']:,}</b></td><td class=r>{E(x['top'][0]['shop'])} (+{x['top'][0]['sales_added']})</td></tr>" for x in rs)
    name = "etsy-shops-gaining-sales.html"
    title = f"Etsy shops gaining sales by niche ({span})"
    desc = f"Sales added by Etsy niche {span}, from exact public sales counter reads on both days. Dated, with coverage and method."
    lede = f"From exact sales counter reads on {fd[:-6]} and {td}: which niches added the most sales, and which shop led each one."
    body = f"""<p class="asof">Data as of {td} · sales added {span} · not live</p>
<table><tr><th>Niche (shop headline words)</th><th class=r>Shops read both days</th><th class=r>Shops gaining</th><th class=r>Sales added</th><th class=r>Biggest gainer</th></tr>{rows}</table>
<div class="cov"><h2 style="margin-top:0">Coverage</h2><p>{S['clean_pairs']:,} shops had an exact sales count on both {fd} and {td} in the newest
snapshot that passed our balance check. A niche here is a word rule on the shop's own Etsy headline (each page states its rule); a shop can be in more than one niche,
so the rows do not add up to a total. Niches need at least {S['min_shops']} shops with exact reads on both days. Niches we checked but left out:
{", ".join(E(x['niche']) + " (" + E(x['why']) + ")" for x in S['skipped'])}.</p>
<p><a href="how-we-measure.html">How we measure</a> · <a href="reports.html">All niche reports</a></p></div>"""
    return name, title, shell(H, name, title, desc, "Etsy shops gaining sales, by niche", lede, body, ctx)


def build(out_dir, H, meta, ctx, root):
    P = latest_price_cut(root)
    S = latest_sales_cut(root)
    sales_items = []
    made = []
    items = []

    def w(name, html_):
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
            fh.write(html_)
        made.append(name)

    if P and P["pages"]:
        for r in sorted(P["pages"], key=lambda r: r["keyword"]):
            name, title, h = price_page(H, P, r, ctx)
            w(name, h); items.append((name, title))
        name, title, h = compare_page(H, P, ctx)
        w(name, h); items.insert(0, (name, title))
    if S and S["pages"]:
        for r in S["pages"]:
            name, title, h = sales_page(H, S, r, ctx)
            w(name, h); sales_items.append((name, title))
        name, title, h = sales_overview(H, S, ctx)
        w(name, h); sales_items.insert(0, (name, title))
    name, title, h = measure_page(H, meta, P, ctx)
    w(name, h)
    name, title, h = index_page(H, P, items, ctx, sales_items)
    w(name, h)
    lastmod = {n: (P["read_date"] if P and n.startswith("etsy-prices") else S["snapshot_date"] if S and n.startswith("etsy-shops-gaining")
                   else meta["snapshot_date"]) for n in made}
    return made, lastmod


def check_reports(out_dir, names, site_url):
    bad = []
    sm = open(os.path.join(out_dir, "sitemap.xml"), encoding="utf-8").read()
    idx = open(os.path.join(out_dir, "reports.html"), encoding="utf-8").read()
    for n in names:
        raw = open(os.path.join(out_dir, n), encoding="utf-8").read()
        for need, why in ((EN_ONLY, "en-only marker"), (f'<link rel="canonical" href="{site_url}{n}">', "canonical"),
                          ('<meta name="description"', "meta description"), ("<h1>", "h1")):
            if need not in raw:
                bad.append(f"{n}: missing {why}")
        if "hreflang=\"fr\" href" in raw or "localStorage.getItem('ep_lang')" in raw:
            bad.append(f"{n}: en-only page must not carry hreflang/redirect")
        if n.startswith("etsy-prices") or n == "how-we-measure.html":
            if n.startswith("etsy-prices") and "Data as of" not in raw:
                bad.append(f"{n}: no 'Data as of' line")
        if f"<loc>{site_url}{n}</loc>" not in sm:
            bad.append(f"{n}: not in sitemap")
        if n.startswith("etsy-shops-gaining") and "Data as of" not in raw:
            bad.append(f"{n}: no 'Data as of' line")
        if (n.startswith("etsy-prices") or n.startswith("etsy-shops-gaining")) and f'href="{n}"' not in idx:
            bad.append(f"{n}: not linked from reports.html")
    if bad:
        raise SystemExit("reports check failed:\n  " + "\n  ".join(bad))
    print(f"reports check ok: {len(names)} en-only report pages, canonical + description + h1 + sitemap + index")
