"""Current balanced movers have no held-mode UI; genuinely stale movers keep it."""
import datetime as dt, os, subprocess, sys
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import held_check  # noqa: E402


def test_current_movers_have_no_held_banner_all_locales(tmp_path):
    out = str(tmp_path / "site")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build_site.py"), "--out", out],
                       cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, (r.stdout + "\n" + r.stderr)[-5000:]
    for lg, lp in held_check.LANGS.items():
        for page in ("", "movers/", "rising.html"):
            rel = lp + page
            raw = open(os.path.join(out, rel + ("index.html" if not page or page.endswith("/") else "")), encoding="utf-8").read()
            assert 'class="heldbar"' not in raw, rel
            assert held_check.check_page(rel or "/", raw, lg, dt.date(2026, 11, 4)) == []
