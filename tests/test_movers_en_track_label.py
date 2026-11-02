"""MEMO-1g row 2 (2026-11-02): the English movers page showed the Turkish label 'Bu mağazanın satışlarını izle' on every
shop row's track link (e.g. SABINOCrafts, WeddingsDecorStudio). dm_page loads the tr strings for en (months/labels it
needs), and track_shop_a took T['track_shop'] regardless of lang. Rule: an en page's track links say the en label only,
and no other locale's track label appears on any en page."""
import glob, html, os, subprocess, sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import build_site  # noqa: E402

EN = "Track this shop's sales"
OTHER = ["Bu mağazanın satışlarını izle", "Suivre les ventes de cette boutique"]


def test_track_shop_a_en_ignores_foreign_strings():
    for lg in ("tr", "fr"):
        a = html.unescape(build_site.track_shop_a("en", build_site.load_loc(lg), "SABINOCrafts"))
        assert EN in a, a
        assert not any(o in a for o in OTHER), a


def test_built_en_pages_have_no_foreign_track_label(tmp_path):
    out = os.path.join(str(tmp_path), "site")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build_site.py"), "--out", out],
                       cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, (r.stdout + "\n" + r.stderr)[-2500:]
    en = [f for f in glob.glob(os.path.join(out, "**", "*.html"), recursive=True)
          if not os.path.relpath(f, out).startswith(("fr" + os.sep, "tr" + os.sep))]
    assert any(os.path.relpath(f, out) == os.path.join("movers", "index.html") for f in en), "en movers page not built"
    bad = []
    for f in en:
        body = html.unescape(open(f, encoding="utf-8").read())
        for o in OTHER:
            if o in body:
                bad.append(f"{os.path.relpath(f, out)}: {o!r} x{body.count(o)}")
    assert not bad, "\n".join(bad)
