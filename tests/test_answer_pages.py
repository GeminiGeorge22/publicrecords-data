"""ANSWER-1 (MEMO-1h row 2, 2026-11-03): seller-question answer pages.

The first page answers "How many sales does an Etsy shop make?". Every number on it comes from the newest published
daily-movers day (data/daily-movers/<day>/), the same rows the live Movers / Rising pages show. It carries the report
builder prefilled for the question (type=velocity + shops from its own table + from=<page id>) and one tracked Store link
through the redirect worker (/r/answer-shop-sales). No prices on the page (the shared price CTA is left off)."""
import csv, glob, os, re, subprocess, sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PAGE = "how-many-sales-does-an-etsy-shop-make.html"
SLUG = "answer-shop-sales"


def _site(tmp):
    out = os.path.join(tmp, "site")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build_site.py"), "--out", out],
                       cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    return out


def _day():
    d = sorted(p for p in glob.glob(os.path.join(ROOT, "data", "daily-movers", "20*")) if os.path.exists(os.path.join(p, "movers.csv")))[-1]
    rd = lambda f: list(csv.DictReader(open(os.path.join(d, f), encoding="utf-8")))
    return os.path.basename(d), rd("movers.csv"), rd("rising.csv")


def _visible(raw):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))


def test_answer_page_built_linked_and_tracked(tmp_path):
    out = _site(str(tmp_path))
    p = os.path.join(out, PAGE)
    assert os.path.exists(p), "answer page not built"
    raw = open(p, encoding="utf-8").read()
    assert "<h1>How many sales does an Etsy shop make?</h1>" in raw
    assert f"workers.dev/r/{SLUG}" in raw, "tracked Store link missing"
    assert re.search(r'href="run\.html\?type=velocity&amp;shops=[^"&]+&amp;from=answer-shop-sales"', raw), "prefilled builder link missing"
    assert f"https://www.etsypulse.ca/{PAGE}</loc>" in open(os.path.join(out, "sitemap.xml")).read()
    assert f'href="{PAGE}"' in open(os.path.join(out, "reports.html")).read()
    assert "Data as of" in raw


def test_answer_page_numbers_come_from_published_day(tmp_path):
    out = _site(str(tmp_path))
    raw = open(os.path.join(out, PAGE), encoding="utf-8").read()
    vis = _visible(raw)
    day, movers, rising = _day()
    for r in movers[:5] + rising[:5]:
        assert r["shop_name"] in vis and f"+{int(r['sales_added']):,}" in vis, r["shop_name"]
    shops = re.search(r"type=velocity&amp;shops=([^\"&]+)", raw).group(1).split(",")
    assert shops[0] == rising[0]["shop_name"] and shops[1] == movers[0]["shop_name"]


def test_answer_page_has_no_prices(tmp_path):
    out = _site(str(tmp_path))
    vis = _visible(open(os.path.join(out, PAGE), encoding="utf-8").read())
    assert not re.search(r"[$¢]|\bcents?\b|free plan", vis), re.findall(r".{40}(?:[$¢]|cents?|free plan).{40}", vis)


# ANSWER-2 (MEMO-1h row 2, 2026-11-04): "How to track a competitor's Etsy sales" (Etsy competitor research).
PAGE2 = "how-to-track-a-competitors-etsy-sales.html"
SLUG2 = "answer-competitor-sales"


def test_competitor_page_built_linked_and_tracked(tmp_path):
    out = _site(str(tmp_path))
    p = os.path.join(out, PAGE2)
    assert os.path.exists(p), "competitor answer page not built"
    raw = open(p, encoding="utf-8").read()
    assert "<h1>How to track a competitor's Etsy sales</h1>" in raw or "<h1>How to track a competitor&#x27;s Etsy sales</h1>" in raw
    assert f"workers.dev/r/{SLUG2}" in raw, "tracked Store link missing"
    assert f"workers.dev/r/{SLUG}" not in raw, "page 2 must carry its own link id"
    assert re.search(r'href="run\.html\?type=velocity&amp;shops=[^"&]+&amp;from=answer-competitor-sales"', raw), "prefilled builder link missing"
    assert f"https://www.etsypulse.ca/{PAGE2}</loc>" in open(os.path.join(out, "sitemap.xml")).read()
    idx = open(os.path.join(out, "reports.html")).read()
    assert f'href="{PAGE2}"' in idx and f'href="{PAGE}"' in idx
    assert "Data as of" in raw
    assert 'href="how-many-sales-does-an-etsy-shop-make.html"' in raw, "links back to answer page 1"


def test_competitor_page_numbers_come_from_published_day(tmp_path):
    out = _site(str(tmp_path))
    raw = open(os.path.join(out, PAGE2), encoding="utf-8").read()
    vis = _visible(raw)
    d = sorted(p for p in glob.glob(os.path.join(ROOT, "data", "daily-movers", "20*")) if os.path.exists(os.path.join(p, "pct.csv")))[-1]
    pct = list(csv.DictReader(open(os.path.join(d, "pct.csv"), encoding="utf-8")))
    for r in pct[:5]:
        assert r["shop_name"] in vis, r["shop_name"]
        assert f"{int(r['sales_before']):,}" in vis and f"{int(r['sales_total']):,}" in vis and f"+{int(r['sales_added']):,}" in vis, r["shop_name"]
        assert f"+{float(r['pct_added']):.1f}%" in vis, r["shop_name"]
    shops = re.search(r"type=velocity&amp;shops=([^\"&]+)", raw).group(1).split(",")
    assert shops == [r["shop_name"] for r in pct[:3]]


def test_competitor_page_has_no_prices(tmp_path):
    out = _site(str(tmp_path))
    vis = _visible(open(os.path.join(out, PAGE2), encoding="utf-8").read())
    assert not re.search(r"[$¢]|\bcents?\b|free plan", vis), re.findall(r".{40}(?:[$¢]|cents?|free plan).{40}", vis)


# ANSWER-3 (2026-11-05): "How many sales on Etsy is good?" (Etsy autocomplete: "how many sales on etsy is good").
PAGE3 = "how-many-sales-on-etsy-is-good.html"
SLUG3 = "answer-good-sales"


def _day3():
    d = sorted(p for p in glob.glob(os.path.join(ROOT, "data", "daily-movers", "20*"))
               if all(os.path.exists(os.path.join(p, f)) for f in ("movers.csv", "rising.csv", "pct.csv")))[-1]
    rd = lambda f: list(csv.DictReader(open(os.path.join(d, f), encoding="utf-8")))
    return rd("rising.csv"), rd("pct.csv"), rd("movers.csv")


def test_good_sales_page_built_linked_and_tracked(tmp_path):
    out = _site(str(tmp_path))
    p = os.path.join(out, PAGE3)
    assert os.path.exists(p), "good-sales answer page not built"
    raw = open(p, encoding="utf-8").read()
    assert "<h1>How many sales on Etsy is good?</h1>" in raw
    assert f"workers.dev/r/{SLUG3}" in raw, "tracked Store link missing"
    assert f"workers.dev/r/{SLUG}" not in raw and f"workers.dev/r/{SLUG2}" not in raw, "page 3 must carry its own link id"
    assert re.search(r'href="run\.html\?type=velocity&amp;shops=[^"&]+&amp;from=answer-good-sales"', raw), "prefilled builder link missing"
    assert f"https://www.etsypulse.ca/{PAGE3}</loc>" in open(os.path.join(out, "sitemap.xml")).read()
    idx = open(os.path.join(out, "reports.html")).read()
    assert f'href="{PAGE3}"' in idx and f'href="{PAGE2}"' in idx and f'href="{PAGE}"' in idx
    assert "Data as of" in raw
    assert f'href="{PAGE}"' in raw and f'href="{PAGE2}"' in raw, "links to answer pages 1 and 2"


def test_good_sales_page_numbers_come_from_published_day(tmp_path):
    out = _site(str(tmp_path))
    raw = open(os.path.join(out, PAGE3), encoding="utf-8").read()
    vis = _visible(raw)
    rs, pc, mv = _day3()
    for r in rs[:3] + pc[:3] + mv[:3]:
        assert r["shop_name"] in vis, r["shop_name"]
        assert f"{int(r['sales_before']):,}" in vis and f"+{int(r['sales_added']):,}" in vis, r["shop_name"]
        g = float(r["pct_added"])
        assert (f"+{g:.1f}%" if g >= 0.1 else f"+{g:.2f}%") in vis, r["shop_name"]
    shops = re.search(r"type=velocity&amp;shops=([^\"&]+)", raw).group(1).split(",")
    assert shops == [rs[0]["shop_name"], pc[0]["shop_name"], mv[0]["shop_name"]]


def test_good_sales_page_has_no_prices_or_internal_labels(tmp_path):
    out = _site(str(tmp_path))
    vis = _visible(open(os.path.join(out, PAGE3), encoding="utf-8").read())
    assert not re.search(r"[$¢]|\bcents?\b|free plan", vis), re.findall(r".{40}(?:[$¢]|cents?|free plan).{40}", vis)
    assert not re.search(r"MEMO|ANSWER-\d|\brow \d", vis)

# ANSWER-4 (2026-11-06): "How to get a Bestseller badge on Etsy?" (autocomplete: etsy bestseller badge).
PAGE4 = "how-to-get-a-bestseller-badge.html"
SLUG4 = "answer-bestseller-badge"


def _niche4():
    d = sorted(p for p in glob.glob(os.path.join(ROOT, "data", "niche", "20*"))
               if os.path.exists(os.path.join(p, "summary.csv")))[-1]
    summary = list(csv.DictReader(open(os.path.join(d, "summary.csv"), encoding="utf-8")))
    listings = list(csv.DictReader(open(os.path.join(d, "listings.csv"), encoding="utf-8")))
    return os.path.basename(d), summary, listings


def test_bestseller_badge_page_built_linked_and_tracked(tmp_path):
    out = _site(str(tmp_path))
    p = os.path.join(out, PAGE4)
    assert os.path.exists(p), "bestseller-badge answer page not built"
    raw = open(p, encoding="utf-8").read()
    assert "<h1>How to get a Bestseller badge on Etsy?</h1>" in raw
    assert f"workers.dev/r/{SLUG4}" in raw, "tracked Store link missing"
    assert f"workers.dev/r/{SLUG}" not in raw and f"workers.dev/r/{SLUG2}" not in raw and f"workers.dev/r/{SLUG3}" not in raw, \
        "page 4 must carry its own link id"
    assert re.search(r'href="run\.html\?type=niche(?:&amp;q=[^"&]+)?(?:&amp;[^"]*)?&amp;from=answer-bestseller-badge"', raw) or \
           re.search(r'href="run\.html\?type=niche&amp;q=[^"&]+&amp;[^"]*from=answer-bestseller-badge"', raw), \
        "prefilled niche builder link missing"
    assert f"from=answer-bestseller-badge" in raw
    assert f"https://www.etsypulse.ca/{PAGE4}</loc>" in open(os.path.join(out, "sitemap.xml")).read()
    idx = open(os.path.join(out, "reports.html")).read()
    assert f'href="{PAGE4}"' in idx and f'href="{PAGE3}"' in idx and f'href="{PAGE2}"' in idx and f'href="{PAGE}"' in idx
    assert "Data as of" in raw
    assert f'href="{PAGE}"' in raw and f'href="{PAGE2}"' in raw and f'href="{PAGE3}"' in raw, "links to answer pages 1–3"


def test_bestseller_badge_page_numbers_come_from_published_niche(tmp_path):
    out = _site(str(tmp_path))
    raw = open(os.path.join(out, PAGE4), encoding="utf-8").read()
    vis = _visible(raw)
    cut, summary, listings = _niche4()
    assert summary, "newest niche cut has no summary rows"
    for r in summary:
        assert r["keyword"] in vis, r["keyword"]
        n = int(float(r["listings"]))
        share = float(r["bestseller_share"])
        nb = int(round(share * n))
        assert f"{nb} of {n}" in vis or f"{nb} of {n:,}" in vis, (r["keyword"], nb, n)
        pct = f"{share * 100:.0f}%"
        assert pct in vis, (r["keyword"], pct)
    bs = [r for r in listings if r.get("bestseller") == "True"]
    assert bs, "newest niche cut has no public bestseller listings"
    # At least a few named bestseller shops from the public top-10 sample appear
    named = sum(1 for r in bs if r["shop_name"] in vis)
    assert named >= 3, f"expected bestseller shop names from listings.csv, got {named}"
    q = re.search(r"type=niche&amp;q=([^\"&]+)", raw)
    assert q, "builder niche q missing"
    from urllib.parse import unquote_plus
    assert unquote_plus(q.group(1)) in {r["keyword"] for r in summary}


def test_bestseller_badge_page_has_no_prices_or_internal_labels(tmp_path):
    out = _site(str(tmp_path))
    vis = _visible(open(os.path.join(out, PAGE4), encoding="utf-8").read())
    assert not re.search(r"[$¢]|\bcents?\b|free plan", vis), re.findall(r".{40}(?:[$¢]|cents?|free plan).{40}", vis)
    assert not re.search(r"MEMO|ANSWER-\d|\brow \d", vis)


# ANSWER-5 (2026-11-08): "What are the best-selling items on Etsy?" (autocomplete: etsy best selling / etsy best selling items).
PAGE5 = "best-selling-items-on-etsy.html"
SLUG5 = "answer-bestselling-items"


def test_bestselling_items_page_built_linked_and_tracked(tmp_path):
    out = _site(str(tmp_path))
    p = os.path.join(out, PAGE5)
    assert os.path.exists(p), "best-selling-items answer page not built"
    raw = open(p, encoding="utf-8").read()
    assert "<h1>What are the best-selling items on Etsy?</h1>" in raw
    assert f"workers.dev/r/{SLUG5}" in raw, "tracked Store link missing"
    for s in (SLUG, SLUG2, SLUG3, SLUG4):
        assert f"workers.dev/r/{s}\"" not in raw and f"workers.dev/r/{s}<" not in raw, f"page 5 must carry its own link id, found {s}"
    assert re.search(r'href="run\.html\?type=niche&amp;q=[^"&]+&amp;[^"]*from=answer-bestselling-items"', raw), \
        "prefilled niche builder link missing"
    assert f"https://www.etsypulse.ca/{PAGE5}</loc>" in open(os.path.join(out, "sitemap.xml")).read()
    idx = open(os.path.join(out, "reports.html")).read()
    for pg in (PAGE5, PAGE4, PAGE3, PAGE2, PAGE):
        assert f'href="{pg}"' in idx, pg
    assert "Data as of" in raw
    for pg in (PAGE, PAGE2, PAGE3, PAGE4):
        assert f'href="{pg}"' in raw, f"links to answer page {pg}"
    assert 'href="etsy-prices.html"' not in raw, "no price-page link on answer pages"


def test_bestselling_items_page_numbers_come_from_published_niche(tmp_path):
    out = _site(str(tmp_path))
    raw = open(os.path.join(out, PAGE5), encoding="utf-8").read()
    vis = _visible(raw)
    cut, summary, listings = _niche4()
    assert summary, "newest niche cut has no summary rows"
    for r in summary:
        assert r["keyword"] in vis, r["keyword"]
        n = int(float(r["listings"]))
        share = float(r["bestseller_share"])
        nb = int(round(share * n))
        assert f"{nb} of {n}" in vis or f"{nb} of {n:,}" in vis, (r["keyword"], nb, n)
        assert f"{share * 100:.0f}%" in vis, (r["keyword"], share)
    bs = [r for r in listings if r.get("bestseller") == "True"]
    assert bs, "newest niche cut has no public bestseller listings"
    named = sum(1 for r in bs if r["shop_name"] in vis)
    assert named >= min(8, len(bs)), f"expected bestseller shop names from listings.csv, got {named}"
    assert len({r["query"] for r in bs if r["shop_name"] in vis}) >= min(3, len({r["query"] for r in bs})), "examples span keywords"
    q = re.search(r"type=niche&amp;q=([^\"&]+)", raw)
    assert q, "builder niche q missing"
    from urllib.parse import unquote_plus
    assert unquote_plus(q.group(1)) in {r["keyword"] for r in summary}


def test_bestselling_items_page_has_no_prices_or_internal_labels(tmp_path):
    out = _site(str(tmp_path))
    vis = _visible(open(os.path.join(out, PAGE5), encoding="utf-8").read())
    assert not re.search(r"[$¢]|\bcents?\b|free plan", vis), re.findall(r".{40}(?:[$¢]|cents?|free plan).{40}", vis)
    assert not re.search(r"MEMO|ANSWER-\d|\brow \d", vis)


def test_check_reports_requires_data_as_of_on_non_how_answer_page(tmp_path):
    """The reports check must cover best-selling-items-on-etsy.html even though its name doesn't start with 'how-'."""
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import pytest
    import report_pages
    site = "https://www.etsypulse.ca/"
    d = str(tmp_path)
    page = (f'{report_pages.EN_ONLY}<link rel="canonical" href="{site}{PAGE5}"><meta name="description" content="x"><h1>x</h1>')
    open(os.path.join(d, PAGE5), "w", encoding="utf-8").write(page)
    open(os.path.join(d, "sitemap.xml"), "w").write(f"<loc>{site}{PAGE5}</loc>")
    open(os.path.join(d, "reports.html"), "w").write(f'<a href="{PAGE5}">x</a>')
    with pytest.raises(SystemExit, match="answer page needs a 'Data as of' line"):
        report_pages.check_reports(d, [PAGE5], site)
    open(os.path.join(d, PAGE5), "w", encoding="utf-8").write(page + "Data as of Oct 17")
    open(os.path.join(d, "reports.html"), "w").write("")
    with pytest.raises(SystemExit, match="answer page needs a 'Data as of' line and a reports.html link"):
        report_pages.check_reports(d, [PAGE5], site)


# ANSWER-6 (2026-11-09): "Can you see an Etsy shop's sales history?" (autocomplete: etsy shop sales history).
PAGE6 = "can-you-see-an-etsy-shops-sales-history.html"
SLUG6 = "answer-sales-history"


def test_sales_history_page_built_linked_and_tracked(tmp_path):
    out = _site(str(tmp_path))
    p = os.path.join(out, PAGE6)
    assert os.path.exists(p), "sales-history answer page not built"
    raw = open(p, encoding="utf-8").read()
    assert re.search(r"<h1>Can you see an Etsy shop(?:&#x27;|')s sales history\?</h1>", raw)
    assert f"workers.dev/r/{SLUG6}" in raw, "tracked Store link missing"
    for s in (SLUG, SLUG2, SLUG3, SLUG4, SLUG5):
        assert f"workers.dev/r/{s}\"" not in raw and f"workers.dev/r/{s}<" not in raw, f"page 6 must carry its own link id, found {s}"
    assert re.search(r'href="run\.html\?type=velocity&amp;shops=[^"&]+&amp;from=answer-sales-history"', raw), "prefilled builder link missing"
    assert f"https://www.etsypulse.ca/{PAGE6}</loc>" in open(os.path.join(out, "sitemap.xml")).read()
    idx = open(os.path.join(out, "reports.html")).read()
    for pg in (PAGE6, PAGE5, PAGE):
        assert f'href="{pg}"' in idx, pg
    assert "Data as of" in raw
    for pg in (PAGE, PAGE2, PAGE3):
        assert f'href="{pg}"' in raw, f"links to answer page {pg}"
    assert 'href="etsy-prices.html"' not in raw, "no price-page link on answer pages"


def test_sales_history_page_numbers_come_from_published_day(tmp_path):
    out = _site(str(tmp_path))
    raw = open(os.path.join(out, PAGE6), encoding="utf-8").read()
    vis = _visible(raw)
    day, movers, rising = _day()
    for r in movers[:3]:
        assert r["shop_name"] in vis and f"+{int(r['sales_added']):,}" in vis, r["shop_name"]
        assert f"{int(r['sales_before']):,}" in vis and f"{int(r['sales_total']):,}" in vis, r["shop_name"]
    shops = re.search(r"type=velocity&amp;shops=([^\"&]+)", raw).group(1).split(",")
    assert shops[0] == movers[0]["shop_name"]


def test_sales_history_page_has_no_prices_or_internal_labels(tmp_path):
    out = _site(str(tmp_path))
    vis = _visible(open(os.path.join(out, PAGE6), encoding="utf-8").read())
    assert not re.search(r"[$¢]|\bcents?\b|free plan", vis), re.findall(r".{40}(?:[$¢]|cents?|free plan).{40}", vis)
    assert not re.search(r"MEMO|ANSWER-\d|\brow \d", vis)


def test_check_reports_requires_data_as_of_on_sales_history_page(tmp_path):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import pytest
    import report_pages
    site = "https://www.etsypulse.ca/"
    d = str(tmp_path)
    page = (f'{report_pages.EN_ONLY}<link rel="canonical" href="{site}{PAGE6}"><meta name="description" content="x"><h1>x</h1>')
    open(os.path.join(d, PAGE6), "w", encoding="utf-8").write(page)
    open(os.path.join(d, "sitemap.xml"), "w").write(f"<loc>{site}{PAGE6}</loc>")
    open(os.path.join(d, "reports.html"), "w").write(f'<a href="{PAGE6}">x</a>')
    with pytest.raises(SystemExit, match="answer page needs a 'Data as of' line"):
        report_pages.check_reports(d, [PAGE6], site)
