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
