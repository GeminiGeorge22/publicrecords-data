"""VEL-STALE-1105: a balanced movers day can have a multi-day window while the
previous panel days were unbalanced. The held-day marker must not mislabel that
current window as stale. R1/R2/R3 remain enabled on the complete build."""
import datetime as dt, glob, json, os, shutil, subprocess, sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import held_check  # noqa: E402


def _balanced_two_day_fixture(tmp):
    repo = os.path.join(tmp, "repo")
    shutil.copytree(ROOT, repo, ignore=shutil.ignore_patterns(".git", "_site", "__pycache__", ".pytest_cache"))
    old = os.path.join(repo, "data", "daily-movers", "2026-11-01")
    # The real 2026-11-04 export may already exist. Build the synthetic day in a
    # temporary source directory, then atomically replace only the temp repo copy.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="balanced-movers-", dir=tmp) as td:
        staged = os.path.join(td, "2026-11-04")
        shutil.copytree(old, staged)
        new = os.path.join(repo, "data", "daily-movers", "2026-11-04")
        if os.path.isdir(new):
            shutil.rmtree(new)
        shutil.move(staged, new)
    meta = json.load(open(os.path.join(new, "meta.json")))
    meta.update(snapshot_date="2026-11-04", to_date="2026-11-04", from_date="2026-11-02", window_days=2,
                niche_from_date="2026-11-02", niche_window_days=2,
                method="Sales added = a shop's public Etsy sales counter on 2026-11-04 minus the same counter 2 day(s) earlier, both read exactly on those dates.")
    json.dump(meta, open(os.path.join(new, "meta.json"), "w"), indent=2)
    cuts = sorted(glob.glob(os.path.join(repo, "data", "panel", "20*", "meta.json")))
    cut = os.path.join(repo, "data", "panel", "2026-11-05")
    source_cut = os.path.dirname(cuts[-1])
    if os.path.abspath(source_cut) != os.path.abspath(cut):
        if os.path.isdir(cut):
            shutil.rmtree(cut)
        shutil.copytree(source_cut, cut)
    panel = json.load(open(os.path.join(cut, "meta.json")))
    panel.update(cut_date="2026-11-05", snapshot_date="2026-11-04")
    json.dump(panel, open(os.path.join(cut, "meta.json"), "w"), indent=2)
    return repo


def test_balanced_two_day_movers_window_is_not_held(tmp_path):
    repo = _balanced_two_day_fixture(str(tmp_path))
    out = os.path.join(str(tmp_path), "site")
    r = subprocess.run([sys.executable, os.path.join(repo, "scripts", "build_site.py"), "--out", out],
                       cwd=repo, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, (r.stdout + "\n" + r.stderr)[-5000:]
    for lg, lp in held_check.LANGS.items():
        for page in ("", "movers/", "rising.html"):
            rel = lp + page
            raw = open(os.path.join(out, rel + ("index.html" if not page or page.endswith("/") else "")), encoding="utf-8").read()
            assert 'class="heldbar"' not in raw, rel
            assert held_check.check_page(rel or "/", raw, lg, dt.date(2026, 11, 4)) == []
