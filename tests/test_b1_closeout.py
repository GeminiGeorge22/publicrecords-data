"""B-1: held niche leaders stay out of previews; stale Niche Prices do not publish."""
import datetime as dt
import html
import glob
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_footer_date import _repo_copy_with_next_day_cut  # noqa: E402
from test_niche_line_age import _set_niche_age  # noqa: E402

CLAUSES = {
    "en": "Aprons lead the niches (+1,478)",
    "fr": "Tabliers mène les niches (+1 478)",
    "tr": "nişlerde Önlükler önde (+1.478)",
}


def _fresh_balanced_niches(repo, snap):
    days = sorted(d for d in glob.glob(os.path.join(repo, "data", "daily-movers", "20*")) if os.path.isdir(d))
    new = os.path.join(repo, "data", "daily-movers", snap.isoformat())
    if not os.path.isdir(new):
        shutil.copytree(days[-1], new)
    path = os.path.join(new, "meta.json")
    meta = json.load(open(path))
    meta.update(snapshot_date=snap.isoformat(), to_date=snap.isoformat(),
                from_date=(snap - dt.timedelta(days=1)).isoformat(),
                niche_from_date=(snap - dt.timedelta(days=1)).isoformat(), window_days=1)
    json.dump(meta, open(path, "w"), indent=2)


def _build(tmp, niche_age=None, balanced=False):
    repo, snap, _ = _repo_copy_with_next_day_cut(str(tmp))
    if balanced:
        _fresh_balanced_niches(repo, snap)
    if niche_age is not None:
        _set_niche_age(repo, snap, niche_age)
    out = os.path.join(str(tmp), "site")
    result = subprocess.run([sys.executable, os.path.join(repo, "scripts", "build_site.py"), "--out", out],
                            cwd=repo, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, (result.stderr or result.stdout)[-2000:]
    return out


def _preview_descriptions(raw):
    return [html.unescape(x).replace("\u00a0", " ") for x in re.findall(r'<meta (?:name="description"|property="og:description"|name="twitter:description") content="([^"]*)"', raw)]


@pytest.mark.parametrize("lang,prefix", [("en", ""), ("fr", "fr/"), ("tr", "tr/")])
def test_held_niche_clause_is_absent_from_all_home_previews(tmp_path, lang, prefix):
    out = _build(tmp_path, balanced=False)
    raw = open(os.path.join(out, prefix, "index.html"), encoding="utf-8").read()
    descriptions = _preview_descriptions(raw)
    assert len(descriptions) == 3
    assert all(CLAUSES[lang] not in desc for desc in descriptions)
    assert all("mène les niches" not in desc and "nişlerde" not in desc for desc in descriptions)
    assert all("()" not in desc for desc in descriptions)


@pytest.mark.parametrize("lang,prefix", [("en", ""), ("fr", "fr/"), ("tr", "tr/")])
def test_balanced_niche_clause_remains_in_all_home_previews(tmp_path, lang, prefix):
    out = _build(tmp_path, balanced=True)
    raw = open(os.path.join(out, prefix, "index.html"), encoding="utf-8").read()
    descriptions = _preview_descriptions(raw)
    assert len(descriptions) == 3
    assert all(CLAUSES[lang] in desc for desc in descriptions)


def _all_html(out):
    return {os.path.relpath(path, out): open(path, encoding="utf-8").read()
            for path in glob.glob(os.path.join(out, "**", "*.html"), recursive=True)}


def test_stale_niche_prices_are_not_published_or_linked(tmp_path):
    out = _build(tmp_path, niche_age=16)  # Oct 19 capture, Nov 4 snapshot fixture
    pages = _all_html(out)
    for name in ("niche.html", "fr/niche.html", "tr/niche.html"):
        assert name not in pages
    for name, raw in pages.items():
        assert not re.search(r'href="[^"]*niche\.html', raw), name
        assert not re.search(r"Niche Prices|Prix par niche|Niş fiyatları", raw, re.I), name
    sitemap = open(os.path.join(out, "sitemap.xml"), encoding="utf-8").read()
    assert "niche.html" not in sitemap


def test_fresh_niche_prices_still_publish_and_link(tmp_path):
    out = _build(tmp_path, niche_age=7)
    pages = _all_html(out)
    for name in ("niche.html", "fr/niche.html", "tr/niche.html"):
        assert name in pages
    assert 'href="niche.html"' in pages["index.html"]
    assert "Niche Prices" in pages["index.html"]
    assert "Niche prices" in pages["index.html"]  # method paragraph
    sitemap = open(os.path.join(out, "sitemap.xml"), encoding="utf-8").read()
    assert "niche.html" in sitemap
