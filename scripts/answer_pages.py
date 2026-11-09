"""ANSWER-1 (MEMO-1h row 2, 2026-11-03): seller-question answer pages, one question per page, English only.

Each page answers one question sellers search for, uses only numbers the site already publishes (the newest
data/daily-movers/<day>/ rows, the same ones /movers/ and /rising.html show), opens the report builder prefilled for that
question (run.html?...&from=<page id>, counted by the builder-view beacon) and carries one tracked Store link through the
redirect worker (/r/<page id>, registered in the worker's TARGETS). No prices here: the shared price CTA is left off.
Called from report_pages.build(), so it gets the same en-only shell, sitemap entry, reports.html link and check_reports."""
from urllib.parse import quote

PAGES = []   # (file name, title) of pages built, for reports.html


def _shop_cell(H, r):
    E = H["E"]
    return f'<a href="{E(r["shop_url"])}" rel="nofollow noopener">{E(r["shop_name"])}</a>'


def shop_sales(H, ctx, report_pages):
    """Q1: How many sales does an Etsy shop make?"""
    E = H["E"]
    D = H["dm_load"](H["dm_days"]()[-1])
    mv, rs = D["movers"][:5], D["rising"][:5]
    if not mv or not rs:
        return None
    pid = "answer-shop-sales"
    name = "how-many-sales-does-an-etsy-shop-make.html"
    day = report_pages.nice(D["day"])
    win = H["dm_win"](D)                      # e.g. "Sales added in 24 hours, Oct 31 → Nov 1"
    span = H["dm_span"](D)                    # "in 24 hours" / "in 2 days"
    shops = [rs[0]["shop_name"], mv[0]["shop_name"]]
    builder = f'{H["BUILDER"]}?type=velocity&amp;shops={",".join(quote(s, safe="") for s in shops)}&amp;from={pid}'
    store = f'{H["R"]}{pid}'
    n = lambda x: f"{x:,}"
    title = "How many sales does an Etsy shop make? Read any shop's real count"
    desc = ("There is no typical number: Etsy shows each shop's lifetime sales, and the sales it makes in a day or a week are "
            "the difference between two reads of that count. Real examples, dated, and how to check any shop.")
    lede = ("There is no typical number. Every Etsy shop page shows a lifetime sales count, and the only honest way to know how many "
            "sales a shop makes in a day or a week is to read that count twice and subtract. Here is what that looked like for real shops.")

    def rows(rr):
        return "".join(f"<tr><td>{_shop_cell(H, r)}</td><td class=r>{n(r['sales_before'])}</td><td class=r>{n(r['sales_total'])}</td>"
                       f"<td class=r><b>+{n(r['sales_added'])}</b></td></tr>" for r in rr)
    head = "<tr><th>Shop</th><th class=r>Count before</th><th class=r>Count after</th><th class=r>Sales added</th></tr>"
    big, small = mv[0], rs[0]
    cap = n(int(D["meta"].get("rising_max_total_sales", 999)) + 1)
    body = f"""<p class="asof">Data as of {day} · {E(win)} · not live</p>
<h2>The short answer</h2>
<p>On the newest day we published, the shop that added the most sales,
{_shop_cell(H, big)}, went from {n(big['sales_before'])} to {n(big['sales_total'])} lifetime sales: <b>+{n(big['sales_added'])} {E(span)}</b>.
Among shops with under {cap} lifetime sales, the fastest, {_shop_cell(H, small)}, added <b>+{n(small['sales_added'])}</b> {E(span)}.
These are the top of the list; most shops add fewer. A shop's own count is the number to watch, not an average.</p>

<h2>Shops that added the most sales</h2>
<table>{head}{rows(mv)}</table>
<h2>Small shops (under {cap} lifetime sales) that added the most</h2>
<table>{head}{rows(rs)}</table>
<p>Full lists: <a href="movers/">Daily Movers</a> · <a href="rising.html">Rising Shops</a>.</p>

<h2>How to check any Etsy shop's sales yourself</h2>
<ol>
<li>Open the shop on Etsy (etsy.com/shop/ShopName). The shop page shows its lifetime sales count.</li>
<li>Write that number down with today's date.</li>
<li>Read it again a day or a week later. The difference is how many sales the shop made in between.</li>
</ol>
<p>Some large shops show a rounded count, so small changes don't show up, and the count says nothing about which listings sold or for how much.
It is a count of sales, not money.</p>

<div class="cov"><h2 style="margin-top:0">Count sales for shops you choose</h2>
<p>Reading counts by hand works for one or two shops. Our Etsy Shop Sales Tracker reads them for every shop you name and gives you
the sales added between reads, in a spreadsheet. The report below opens with {E(shops[0])} and {E(shops[1])} filled in: swap in
your own competitors and press Run.</p>
<p><a class="btn" href="{builder}">Count sales for these shops →</a></p>
<p>Runs on your own Apify account after a free sign-in. No code. Prefer Apify's own page?
<a href="{store}" rel="noopener">Open the Etsy Shop Sales Tracker on Apify</a>.</p></div>

<div class="cov"><h2 style="margin-top:0">Coverage: where these numbers come from</h2>
<p>Sales added is a shop's public Etsy sales count at the end of the window minus the same count at the start, each read on its own date.
No scaling or estimates. Shops without both reads, with a rounded count, a count that went down, or an implausible jump are left out.
The shops above are shops our tracker reads, not every shop on Etsy.</p>
<p><a href="how-we-measure.html">How we measure</a> · <a href="reports.html">All reports</a></p></div>"""
    out = report_pages.shell(H, name, title, desc, "How many sales does an Etsy shop make?", lede, body, ctx)
    out = out.replace(H["cta"](ctx), "")      # no prices on answer pages
    return name, title, out


def competitor_sales(H, ctx, report_pages):
    """Q2 (2026-11-04): How to track a competitor's Etsy sales (searched as 'etsy competitor research / analysis')."""
    E = H["E"]
    D = H["dm_load"](H["dm_days"]()[-1])
    pc = D["pct"][:5]
    if len(pc) < 3:
        return None
    pid = "answer-competitor-sales"
    name = "how-to-track-a-competitors-etsy-sales.html"
    day = report_pages.nice(D["day"])
    win = H["dm_win"](D)
    span = H["dm_span"](D)
    shops = [r["shop_name"] for r in pc[:3]]
    builder = f'{H["BUILDER"]}?type=velocity&amp;shops={",".join(quote(s, safe="") for s in shops)}&amp;from={pid}'
    store = f'{H["R"]}{pid}'
    n = lambda x: f"{x:,}"
    base = n(int(D["meta"].get("pct_min_base_sales") or 1000))
    title = "How to track a competitor's Etsy sales: Etsy competitor research with real counts"
    desc = ("Etsy competitor research starts with one public number: every shop's lifetime sales count. Read it on a schedule and "
            "subtract to see how many sales a competitor makes. Dated examples and a step-by-step method.")
    lede = ("Etsy doesn't tell you how many sales a competitor made lately, but every shop page shows a lifetime sales count. "
            "Read that count on a schedule, subtract, and you have the competitor's sales for each day or week. Here is what that looks like for real shops.")
    top = pc[0]
    rows = "".join(f"<tr><td>{_shop_cell(H, r)}</td><td class=r>{n(r['sales_before'])}</td><td class=r>{n(r['sales_total'])}</td>"
                   f"<td class=r><b>+{n(r['sales_added'])}</b></td><td class=r>+{r['pct_added']:.1f}%</td></tr>" for r in pc)
    head = "<tr><th>Shop</th><th class=r>Count before</th><th class=r>Count after</th><th class=r>Sales added</th><th class=r>Growth</th></tr>"
    body = f"""<p class="asof">Data as of {day} · {E(win)} · not live</p>
<h2>The short answer</h2>
<p>Write down the competitor's lifetime sales count from their Etsy shop page, read it again later, and subtract.
On the newest day we published, {_shop_cell(H, top)} went from {n(top['sales_before'])} to {n(top['sales_total'])} lifetime sales:
<b>+{n(top['sales_added'])} {E(span)}</b>, +{top['pct_added']:.1f}% on what it had sold before. That difference is the whole method.</p>

<h2>Shops with {base}+ sales that grew fastest for their size</h2>
<table>{head}{rows}</table>
<p>Growth is sales added as a share of the count before. Full list: <a href="movers/">Daily Movers</a>.</p>

<h2>How to track a competitor's Etsy sales by hand</h2>
<ol>
<li>List the competitors you care about: shops selling what you sell, at a similar size.</li>
<li>Open each shop on Etsy (etsy.com/shop/ShopName) and copy its lifetime sales count into a spreadsheet with the date.</li>
<li>Read the same shops again at the same time each day or each week.</li>
<li>Subtract the old count from the new one. That is how many sales the shop made in between.</li>
<li>Compare shops by growth, not just size: sales added divided by the count before shows who is pulling ahead.</li>
</ol>
<p>The count has limits. Some large shops show a rounded number, so small changes are hidden. It doesn't say which listings sold
or for how much. It is a count of sales, not money.
For what a shop's count looks like in practice, see <a href="how-many-sales-does-an-etsy-shop-make.html">How many sales does an Etsy shop make?</a></p>

<div class="cov"><h2 style="margin-top:0">Track your competitors' sales automatically</h2>
<p>Copying counts by hand works for a few shops. Our Etsy Shop Sales Tracker reads the count for every shop you name and gives you
the sales added between reads, in a spreadsheet. The report below opens with {E(shops[0])}, {E(shops[1])} and {E(shops[2])} filled in:
swap in your competitors and press Run.</p>
<p><a class="btn" href="{builder}">Track these shops' sales →</a></p>
<p>Runs on your own Apify account after a free sign-in. No code. Prefer Apify's own page?
<a href="{store}" rel="noopener">Open the Etsy Shop Sales Tracker on Apify</a>.</p></div>

<div class="cov"><h2 style="margin-top:0">Coverage: where these numbers come from</h2>
<p>Sales added is a shop's public Etsy sales count at the end of the window minus the same count at the start, each read on its own date.
No scaling or estimates. Shops without both reads, with a rounded count, a count that went down, or an implausible jump are left out.
The shops above are shops our tracker reads, not every shop on Etsy.</p>
<p><a href="how-we-measure.html">How we measure</a> · <a href="reports.html">All reports</a></p></div>"""
    out = report_pages.shell(H, name, title, desc, "How to track a competitor's Etsy sales", lede, body, ctx)
    out = out.replace(H["cta"](ctx), "")      # no prices on answer pages
    return name, title, out


def _growth(x):
    return f"+{x:.1f}%" if x >= 0.1 else f"+{x:.2f}%"


def good_sales(H, ctx, report_pages):
    """Q3 (2026-11-05): How many sales on Etsy is good? (searched as 'how many sales on etsy is good')."""
    E = H["E"]
    D = H["dm_load"](H["dm_days"]()[-1])
    rs, pc, mv = D["rising"][:3], D["pct"][:3], D["movers"][:3]
    if len(rs) < 3 or len(pc) < 3 or len(mv) < 3:
        return None
    pid = "answer-good-sales"
    name = "how-many-sales-on-etsy-is-good.html"
    day = report_pages.nice(D["day"])
    win = H["dm_win"](D)
    span = H["dm_span"](D)
    shops = [rs[0]["shop_name"], pc[0]["shop_name"], mv[0]["shop_name"]]
    builder = f'{H["BUILDER"]}?type=velocity&amp;shops={",".join(quote(s, safe="") for s in shops)}&amp;from={pid}'
    store = f'{H["R"]}{pid}'
    n = lambda x: f"{x:,}"
    cap = n(int(D["meta"].get("rising_max_total_sales", 999)) + 1)
    base = n(int(D["meta"].get("pct_min_base_sales") or 1000))
    title = "How many sales on Etsy is good? Compare your shop with shops your size"
    desc = ("There is no single good number of Etsy sales. Good depends on how big your shop already is: compare the sales you add "
            "with your own count and with shops your size. Dated examples at three shop sizes and how to check yours.")
    lede = ("There is no single good number. A sale count that would be a great day for a new shop is a quiet day for a shop with "
            "hundreds of thousands of sales. Judge your sales against your own lifetime count and against shops your size. "
            "Here is what the fastest shops at three sizes did on one real day.")
    groups = [(f"Under {cap} lifetime sales", rs), (f"{base}+ sales, fastest for their size", pc), ("Most sales added, any size", mv)]
    rows = "".join(f"<tr><td>{E(g)}</td><td>{_shop_cell(H, r)}</td><td class=r>{n(r['sales_before'])}</td>"
                   f"<td class=r><b>+{n(r['sales_added'])}</b></td><td class=r>{_growth(r['pct_added'])}</td></tr>"
                   for g, rr in groups for r in rr)
    head = "<tr><th>Shop size</th><th>Shop</th><th class=r>Count before</th><th class=r>Sales added</th><th class=r>Growth</th></tr>"
    s, m, b = rs[0], pc[0], mv[0]
    body = f"""<p class="asof">Data as of {day} · {E(win)} · not live</p>
<h2>The short answer</h2>
<p>A good number of sales is one that grows your shop quickly for its size. Raw counts mislead: on the newest day we published,
the shop that added the most sales, {_shop_cell(H, b)}, added <b>+{n(b['sales_added'])}</b> {E(span)} on {n(b['sales_before'])} lifetime sales,
growth of {_growth(b['pct_added'])}. Among shops with under {cap} lifetime sales, {_shop_cell(H, s)} added <b>+{n(s['sales_added'])}</b>
on {n(s['sales_before'])}, growth of {_growth(s['pct_added'])}. Among shops with {base}+ sales, the fastest for its size, {_shop_cell(H, m)},
added <b>+{n(m['sales_added'])}</b> on {n(m['sales_before'])}, growth of {_growth(m['pct_added'])}.
These are the top of each list, not a typical day. Most shops add fewer.</p>

<h2>The fastest shops at three sizes</h2>
<table>{head}{rows}</table>
<p>Growth is sales added as a share of the count before. Full lists: <a href="movers/">Daily Movers</a> · <a href="rising.html">Rising Shops</a>.</p>

<h2>How to tell if your Etsy sales are good</h2>
<ol>
<li>Write down your shop's lifetime sales count from your shop page, with the date.</li>
<li>Read it again a week later and subtract. That is how many sales you made that week.</li>
<li>Divide the sales you made by the count you started with. That is your growth for the week.</li>
<li>Do the same for a few shops your size that sell what you sell. Compare growth, not just counts.</li>
<li>Repeat every week. Good sales are growth that holds up week after week, not one big day.</li>
</ol>
<p>The count has limits. Some large shops show a rounded number, so small changes are hidden. It doesn't say which listings sold
or for how much. It is a count of sales, not money.
More on reading counts: <a href="how-many-sales-does-an-etsy-shop-make.html">How many sales does an Etsy shop make?</a> ·
<a href="how-to-track-a-competitors-etsy-sales.html">How to track a competitor's Etsy sales</a></p>

<div class="cov"><h2 style="margin-top:0">Compare your shop with shops your size</h2>
<p>Reading counts by hand works for a few shops. Our Etsy Shop Sales Tracker reads the count for every shop you name and gives you
the sales added between reads, in a spreadsheet. The report below opens with {E(shops[0])}, {E(shops[1])} and {E(shops[2])} filled in:
put in your own shop and a few shops your size, and press Run.</p>
<p><a class="btn" href="{builder}">Compare these shops' sales →</a></p>
<p>Runs on your own Apify account after a free sign-in. No code. Prefer Apify's own page?
<a href="{store}" rel="noopener">Open the Etsy Shop Sales Tracker on Apify</a>.</p></div>

<div class="cov"><h2 style="margin-top:0">Coverage: where these numbers come from</h2>
<p>Sales added is a shop's public Etsy sales count at the end of the window minus the same count at the start, each read on its own date.
No scaling or estimates. Shops without both reads, with a rounded count, a count that went down, or an implausible jump are left out.
The shops above are shops our tracker reads, not every shop on Etsy.</p>
<p><a href="how-we-measure.html">How we measure</a> · <a href="reports.html">All reports</a></p></div>"""
    out = report_pages.shell(H, name, title, desc, "How many sales on Etsy is good?", lede, body, ctx)
    out = out.replace(H["cta"](ctx), "")      # no prices on answer pages
    return name, title, out




def _niche_cut(H):
    """Newest published data/niche/<cut>/ with summary.csv (same cut niche.html uses)."""
    import glob, os
    root = H["ROOT"]
    cuts = sorted(d for d in glob.glob(os.path.join(root, "data", "niche", "20*"))
                  if os.path.exists(os.path.join(d, "summary.csv")))
    if not cuts:
        return None
    cut = os.path.basename(cuts[-1])
    N = H["load_niche"](cut)
    if not N or not N.get("rows"):
        return None
    listings = H["read_csv"](os.path.join(cuts[-1], "listings.csv"))
    for r in listings:
        r["bestseller"] = r.get("bestseller") == "True"
        r["position"] = int(r.get("position") or 0)
    return N, listings


def bestseller_badge(H, ctx, report_pages):
    """Q4 (2026-11-06): How to get a Bestseller badge on Etsy? (searched as 'etsy bestseller badge')."""
    E = H["E"]
    loaded = _niche_cut(H)
    if not loaded:
        return None
    N, listings = loaded
    rows = sorted(N["rows"], key=lambda r: -float(r.get("bestseller_share") or 0))
    rows = [r for r in rows if (r.get("listings") or 0) >= 20]
    if len(rows) < 2:
        return None
    pid = "answer-bestseller-badge"
    name = "how-to-get-a-bestseller-badge.html"
    # Same calendar day niche.html / price pages date from this cut's capture
    day_iso = (N["meta"].get("captured_at") or N["cut"])[:10]
    day = report_pages.nice(day_iso)
    cut_day = report_pages.nice(N["cut"])
    hi = rows[0]
    kw = hi["keyword"]
    builder = H["niche_link"](kw, pid)
    store = f'{H["R"]}{pid}'
    pct = H["pct"]
    n = lambda x: f"{int(x):,}"

    def badge_count(r):
        return int(round(float(r["bestseller_share"]) * float(r["listings"])))

    table_rows = "".join(
        f"<tr><td>{E(r['keyword'])}</td><td class=r>{n(r['listings'])}</td>"
        f"<td class=r><b>{badge_count(r)} of {n(r['listings'])}</b></td>"
        f"<td class=r>{pct(r['bestseller_share'])}</td></tr>"
        for r in rows)
    head = ("<tr><th>Search</th><th class=r>Listings read</th>"
            "<th class=r>With a Bestseller badge</th><th class=r>Share</th></tr>")

    # Public top-10 sample: name a few listings that carry the badge (no prices)
    bs = [r for r in listings if r.get("bestseller")]
    # Prefer diversity across keywords, keep short
    seen_kw, examples = set(), []
    for r in sorted(bs, key=lambda x: (x["query"], x["position"])):
        if r["query"] in seen_kw and len(examples) >= 4:
            continue
        if r["query"] not in seen_kw or len(examples) < 6:
            if r["query"] not in seen_kw or sum(1 for e in examples if e["query"] == r["query"]) < 2:
                examples.append(r)
                seen_kw.add(r["query"])
        if len(examples) >= 6:
            break
    if len(examples) < 3:
        examples = bs[:6]

    def _listing_cell(r):
        title = (r.get("title") or "").strip()
        if len(title) > 72:
            title = title[:69].rstrip() + "…"
        shop = r.get("shop_name") or ""
        url = r.get("shop_url") or ""
        shop_html = (f'<a href="{E(url)}" rel="nofollow noopener">{E(shop)}</a>' if url and shop
                     else E(shop))
        return f"<tr><td>{E(r['query'])}</td><td>{E(title)}</td><td>{shop_html}</td></tr>"

    ex_rows = "".join(_listing_cell(r) for r in examples)
    ex_head = "<tr><th>Search</th><th>Listing</th><th>Shop</th></tr>"
    hi_n, hi_b = int(hi["listings"]), badge_count(hi)
    lo = rows[-1]
    lo_n, lo_b = int(lo["listings"]), badge_count(lo)

    title = "How to get a Bestseller badge on Etsy? What the badge looks like in real niches"
    desc = ("Etsy awards the Bestseller badge on listings that sell well lately relative to similar listings. "
            "See how many top results carry the badge in dated niche reads, and how to check your own keyword.")
    lede = ("Etsy puts a Bestseller badge on listings that sell well lately relative to similar listings. "
            "There is no public scorecard for every listing, but you can see how common the badge is in the niches you sell in: "
            "read the top search results for your keyword and count how many already have it. Here is what that looked like "
            "in real niches on one dated read.")

    body = f"""<p class="asof">Data as of {day} · niche read from {cut_day} · not live</p>
<h2>The short answer</h2>
<p>Watch which of your listings earn the badge, and compare your niche with others. On the newest niche read we published,
“{E(hi['keyword'])}” had a Bestseller badge on <b>{hi_b} of {n(hi_n)}</b> listings we counted ({pct(hi['bestseller_share'])}).
“{E(lo['keyword'])}” had the badge on <b>{lo_b} of {n(lo_n)}</b> ({pct(lo['bestseller_share'])}).
Fewer badges in a niche can mean the top spots are less crowded; more badges means shoppers already see many bestseller listings first.
The badge is awarded by Etsy on listings that sell well lately relative to similar listings — the counts below are what our dated search read shows, not Etsy's private score.</p>

<h2>Bestseller badges in the niches we read</h2>
<table>{head}{table_rows}</table>
<p>Share is listings with a Bestseller badge divided by listings in that read. Same dated niche read as
<a href="etsy-prices.html">Typical Etsy prices</a> · <a href="reports.html">All reports</a>.</p>

<h2>Listings that carry the badge (top results sample)</h2>
<p>From the public top results we publish for each keyword, these listings showed a Bestseller badge on that read:</p>
<table>{ex_head}{ex_rows}</table>

<h2>How to check the Bestseller badge in your niche</h2>
<ol>
<li>Search Etsy for the keyword you sell under, in the same region your shoppers use.</li>
<li>On the first results page, count how many listings show a Bestseller badge.</li>
<li>Note which of those are ads and which are organic results — the mix changes how hard the top spots look.</li>
<li>Open a few badge listings and a few without the badge in the same search. Compare how they title, photograph and price the offer (without copying).</li>
<li>Repeat for a second keyword you sell under. Niches differ: the table above is one dated read, not a rule for every category.</li>
</ol>
<p>The badge is a listing signal, not a shop-wide sales count. For shop sales counts, see
<a href="how-many-sales-does-an-etsy-shop-make.html">How many sales does an Etsy shop make?</a> ·
<a href="how-to-track-a-competitors-etsy-sales.html">How to track a competitor's Etsy sales</a> ·
<a href="how-many-sales-on-etsy-is-good.html">How many sales on Etsy is good?</a></p>

<div class="cov"><h2 style="margin-top:0">Read Bestseller badges for your own keyword</h2>
<p>Counting badges by hand works for one search. Our Etsy Search Scraper reads the top results for any keyword you name and flags
which listings carry a Bestseller badge, in a spreadsheet. The report below opens with “{E(kw)}” filled in: swap in your keyword and press Run.</p>
<p><a class="btn" href="{builder}">Read Bestseller badges for “{E(kw)}” →</a></p>
<p>Runs on your own Apify account after a free sign-in. No code. Prefer Apify's own page?
<a href="{store}" rel="noopener">Open the Etsy Search Scraper on Apify</a>.</p></div>

<div class="cov"><h2 style="margin-top:0">Coverage: where these numbers come from</h2>
<p>Each row is one dated read of US Etsy search results for that keyword (Etsy's default relevance order), captured with the
publicrecords Etsy Search Scraper. “Listings read” is how many priced results that run kept for the keyword; the badge count is how many
of those showed a Bestseller badge. Etsy may show far more total results for the same search, so this is a snapshot of what a shopper
sees near the top, not every listing. Keywords came from categories tied to top movers around {cut_day}. Our own shops are excluded.</p>
<p><a href="how-we-measure.html">How we measure</a> · <a href="reports.html">All reports</a></p></div>"""
    out = report_pages.shell(H, name, title, desc, "How to get a Bestseller badge on Etsy?", lede, body, ctx)
    out = out.replace(H["cta"](ctx), "")      # no prices on answer pages
    return name, title, out


def bestselling_items(H, ctx, report_pages):
    """Q5 (2026-11-08): What are the best-selling items on Etsy? (searched as 'etsy best selling' / 'etsy best selling items')."""
    E = H["E"]
    loaded = _niche_cut(H)
    if not loaded:
        return None
    N, listings = loaded
    rows = sorted(N["rows"], key=lambda r: -float(r.get("bestseller_share") or 0))
    rows = [r for r in rows if (r.get("listings") or 0) >= 20]
    bs = [r for r in listings if r.get("bestseller")]
    if len(rows) < 2 or len(bs) < 3:
        return None
    pid = "answer-bestselling-items"
    name = "best-selling-items-on-etsy.html"
    day_iso = (N["meta"].get("captured_at") or N["cut"])[:10]
    day = report_pages.nice(day_iso)
    cut_day = report_pages.nice(N["cut"])
    pct = H["pct"]
    n = lambda x: f"{int(x):,}"

    def badge_count(r):
        return int(round(float(r["bestseller_share"]) * float(r["listings"])))

    # Prefill the keyword with the most named Bestseller listings in the public sample (ties: higher share)
    per_kw = {}
    for r in bs:
        per_kw[r["query"]] = per_kw.get(r["query"], 0) + 1
    kws = {r["keyword"] for r in rows}
    cand = [r for r in rows if r["keyword"] in per_kw] or rows
    top = max(cand, key=lambda r: (per_kw.get(r["keyword"], 0), float(r.get("bestseller_share") or 0)))
    kw = top["keyword"]
    builder = H["niche_link"](kw, pid)
    store = f'{H["R"]}{pid}'

    # Named Bestseller listings, round-robin across keywords (highest share first), top positions first, up to 12
    by_kw = {}
    for r in sorted(bs, key=lambda x: (x["query"], x["position"])):
        by_kw.setdefault(r["query"], []).append(r)
    order = [r["keyword"] for r in rows if r["keyword"] in by_kw] + sorted(k for k in by_kw if k not in kws)
    examples = []
    while len(examples) < 12 and any(by_kw.get(k) for k in order):
        for k in order:
            if by_kw.get(k) and len(examples) < 12:
                examples.append(by_kw[k].pop(0))

    def _listing_cell(r):
        title = (r.get("title") or "").strip()
        if len(title) > 72:
            title = title[:69].rstrip() + "…"
        shop = r.get("shop_name") or ""
        url = r.get("shop_url") or ""
        shop_html = (f'<a href="{E(url)}" rel="nofollow noopener">{E(shop)}</a>' if url and shop else E(shop))
        return f"<tr><td>{E(r['query'])}</td><td>{E(title)}</td><td>{shop_html}</td></tr>"

    ex_rows = "".join(_listing_cell(r) for r in examples)
    ex_head = "<tr><th>Search</th><th>Listing with a Bestseller badge</th><th>Shop</th></tr>"
    table_rows = "".join(
        f"<tr><td>{E(r['keyword'])}</td><td class=r>{n(r['listings'])}</td>"
        f"<td class=r><b>{badge_count(r)} of {n(r['listings'])}</b></td>"
        f"<td class=r>{pct(r['bestseller_share'])}</td></tr>"
        for r in rows)
    head = ("<tr><th>Search</th><th class=r>Listings read</th>"
            "<th class=r>With a Bestseller badge</th><th class=r>Share</th></tr>")
    hi, lo = rows[0], rows[-1]
    n_kw = len({r["query"] for r in examples})

    title = "What are the best-selling items on Etsy? Real Bestseller listings, by search"
    desc = ("Etsy doesn't publish one public list of best-selling items. What you can see is which listings carry a Bestseller badge "
            "in search results for a keyword. Named examples from a dated read, and how to check your own keyword.")
    lede = ("Etsy doesn't publish one marketplace-wide list of best-selling items. What it does show is a Bestseller badge on listings "
            "that sell well lately relative to similar listings, right in search results. So the useful question is: which items "
            "are best-selling in the search you sell under? Here is what that looked like on one dated read.")

    body = f"""<p class="asof">Data as of {day} · niche read from {cut_day} · not live</p>
<h2>The short answer</h2>
<p>There is no single public list. Best-selling items on Etsy are best seen one search at a time: search a keyword and look for the
Bestseller badge near the top. On the newest niche read we published, the listings below carried that badge across {n_kw} searches.
In “{E(hi['keyword'])}”, <b>{badge_count(hi)} of {n(hi['listings'])}</b> listings we counted had it ({pct(hi['bestseller_share'])});
in “{E(lo['keyword'])}”, <b>{badge_count(lo)} of {n(lo['listings'])}</b> ({pct(lo['bestseller_share'])}).
The badge is Etsy's own signal for a listing selling well lately; it is not a sales count, and Etsy doesn't say how many sales it takes.</p>

<h2>Best-selling listings in the searches we read</h2>
<p>From the public top results we publish for each keyword, these listings showed a Bestseller badge on that read:</p>
<table>{ex_head}{ex_rows}</table>

<h2>How many top results were best-sellers, by search</h2>
<table>{head}{table_rows}</table>
<p>Share is listings with a Bestseller badge divided by listings in that read. <a href="reports.html">All reports</a>.</p>

<h2>How to find the best-selling items in your own niche</h2>
<ol>
<li>Search Etsy for the keyword you sell under, in the same region your shoppers use.</li>
<li>On the first results page, note which listings show a Bestseller badge (or a Popular Now badge).</li>
<li>Open a few of them and compare how they title, photograph and present the offer with listings that don't have the badge (learn from them; don't copy).</li>
<li>Repeat for a second keyword you sell under. What sells best in one search says little about another.</li>
</ol>
<p>Limits: this is a snapshot of the top results for a few searches, not every listing on Etsy, and a badge on a listing is not a shop's
lifetime sales count. For shop sales counts, see
<a href="how-many-sales-does-an-etsy-shop-make.html">How many sales does an Etsy shop make?</a> ·
<a href="how-to-track-a-competitors-etsy-sales.html">How to track a competitor's Etsy sales</a> ·
<a href="how-many-sales-on-etsy-is-good.html">How many sales on Etsy is good?</a> ·
For the badge itself: <a href="how-to-get-a-bestseller-badge.html">How to get a Bestseller badge on Etsy?</a></p>

<div class="cov"><h2 style="margin-top:0">Read best-selling listings for your own keyword</h2>
<p>Checking one search by hand is quick; checking several every week is not. Our Etsy Search Scraper reads the top results for any keyword
you name and flags which listings carry a Bestseller badge, in a spreadsheet. The report below opens with “{E(kw)}” filled in: swap in your keyword and press Run.</p>
<p><a class="btn" href="{builder}">Read best-selling listings for “{E(kw)}” →</a></p>
<p>Runs on your own Apify account after a free sign-in. No code. Prefer Apify's own page?
<a href="{store}" rel="noopener">Open the Etsy Search Scraper on Apify</a>.</p></div>

<div class="cov"><h2 style="margin-top:0">Coverage: where these numbers come from</h2>
<p>Each row is one dated read of US Etsy search results for that keyword (Etsy's default relevance order), captured with the
publicrecords Etsy Search Scraper. “Listings read” is how many priced results that run kept for the keyword; the badge count is how many
of those showed a Bestseller badge. The named listings come from the public top results we publish for each keyword. Etsy may show far
more total results for the same search, so this is a snapshot of what a shopper sees near the top, not every listing. Keywords came from
categories tied to top movers around {cut_day}. Our own shops are excluded.</p>
<p><a href="how-we-measure.html">How we measure</a> · <a href="reports.html">All reports</a></p></div>"""
    out = report_pages.shell(H, name, title, desc, "What are the best-selling items on Etsy?", lede, body, ctx)
    out = out.replace(H["cta"](ctx), "")      # no prices on answer pages
    return name, title, out

def sales_history(H, ctx, report_pages):
    """Q6 (2026-11-09): Can you see an Etsy shop's sales history? (searched as 'etsy shop sales history')."""
    E = H["E"]
    D = H["dm_load"](H["dm_days"]()[-1])
    mv, pc = D["movers"][:3], D["pct"][:3]
    if len(mv) < 3 or len(pc) < 1:
        return None
    pid = "answer-sales-history"
    name = "can-you-see-an-etsy-shops-sales-history.html"
    day = report_pages.nice(D["day"])
    win = H["dm_win"](D)
    span = H["dm_span"](D)
    shops = [r["shop_name"] for r in mv[:3]]
    builder = f'{H["BUILDER"]}?type=velocity&amp;shops={",".join(quote(s, safe="") for s in shops)}&amp;from={pid}'
    store = f'{H["R"]}{pid}'
    n = lambda x: f"{x:,}"
    title = "Can you see an Etsy shop's sales history? What Etsy shows and how to build one"
    desc = ("Etsy shows a shop's lifetime sales count but not a day-by-day history. Read that count on a schedule and the "
            "differences become the shop's sales history. A dated example and a step-by-step method.")
    lede = ("Not directly. A shop page on Etsy shows one number, the shop's lifetime sales count, and no history behind it. "
            "But if you read that count on a schedule and keep each reading, the differences are the shop's sales history. "
            "Here is what a few days of history looks like for real shops.")
    rows = "".join(f"<tr><td>{_shop_cell(H, r)}</td><td class=r>{n(r['sales_before'])}</td><td class=r>{n(r['sales_total'])}</td>"
                   f"<td class=r><b>+{n(r['sales_added'])}</b></td></tr>" for r in mv)
    head = "<tr><th>Shop</th><th class=r>Count before</th><th class=r>Count after</th><th class=r>Sales added</th></tr>"
    top = mv[0]
    body = f"""<p class="asof">Data as of {day} · {E(win)} · not live</p>
<h2>The short answer</h2>
<p>Etsy shows each shop's lifetime sales count, not a history of when those sales happened. To see a shop's sales history you have to
build it: read the count, save it with the date, and read it again later. On the newest day we published, {_shop_cell(H, top)} went from
{n(top['sales_before'])} to {n(top['sales_total'])} lifetime sales: <b>+{n(top['sales_added'])} {E(span)}</b>. Line up enough of those readings
and you have a day-by-day history.</p>

<h2>One window of history for three shops</h2>
<table>{head}{rows}</table>
<p>Each row is one window: the count at the start, the count at the end, and the difference. Full list: <a href="movers/">Daily Movers</a>.</p>

<h2>How to build an Etsy shop's sales history</h2>
<ol>
<li>Open the shop on Etsy (etsy.com/shop/ShopName) and copy its lifetime sales count.</li>
<li>Save it in a spreadsheet next to today's date.</li>
<li>Read it again at the same time every day or week and add a new row each time.</li>
<li>Subtract each row from the one before it. Each difference is the sales the shop made in that window.</li>
</ol>
<p>Limits: history only starts from your first reading, so it can't go back in time. Some large shops show a rounded count, so small changes
don't show up, and the count says nothing about which listings sold or for how much. It is a count of sales, not money.
For how to compare shops this way, see <a href="how-to-track-a-competitors-etsy-sales.html">How to track a competitor's Etsy sales</a> ·
<a href="how-many-sales-does-an-etsy-shop-make.html">How many sales does an Etsy shop make?</a> ·
<a href="how-many-sales-on-etsy-is-good.html">How many sales on Etsy is good?</a></p>

<div class="cov"><h2 style="margin-top:0">Read the count for shops you choose</h2>
<p>Doing this by hand works for a couple of shops. Our Etsy Shop Sales Tracker reads the count for every shop you name and gives you
the sales added between reads, in a spreadsheet. The report below opens with {E(shops[0])}, {E(shops[1])} and {E(shops[2])} filled in:
swap in the shops you want and press Run.</p>
<p><a class="btn" href="{builder}">Read these shops' sales →</a></p>
<p>Runs on your own Apify account after a free sign-in. No code. Prefer Apify's own page?
<a href="{store}" rel="noopener">Open the Etsy Shop Sales Tracker on Apify</a>.</p></div>

<div class="cov"><h2 style="margin-top:0">Coverage: where these numbers come from</h2>
<p>Sales added is a shop's public Etsy sales count at the end of the window minus the same count at the start, each read on its own date.
No scaling or estimates. Shops without both reads, with a rounded count, a count that went down, or an implausible jump are left out.
The shops above are shops our tracker reads, not every shop on Etsy.</p>
<p><a href="how-we-measure.html">How we measure</a> · <a href="reports.html">All reports</a></p></div>"""
    out = report_pages.shell(H, name, title, desc, "Can you see an Etsy shop's sales history?", lede, body, ctx)
    out = out.replace(H["cta"](ctx), "")      # no prices on answer pages
    return name, title, out

def build(H, ctx, report_pages):
    built = []
    for fn in (shop_sales, competitor_sales, good_sales, bestseller_badge, bestselling_items, sales_history):
        r = fn(H, ctx, report_pages)
        if r:
            built.append(r)
    return built
