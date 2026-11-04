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


def build(H, ctx, report_pages):
    built = []
    for fn in (shop_sales, competitor_sales):
        r = fn(H, ctx, report_pages)
        if r:
            built.append(r)
    return built
