"""FOOTER-DATE-1 (2026-10-24): the footer's dates must equal the newest data date shown (the snapshot's data date), in en/fr/tr.

On 2026-10-24 06:00 ET the publish was skipped because the footer printed the cut date (the publish day, 2026-10-24) while the
newest data on the page was 2026-10-23 (held_check R3). This test builds the site from a copy of the repo with a cut dated one
day after its snapshot (what every morning publish looks like) and checks every footer date on /, /movers/ and /rising.html."""
import datetime as dt, glob, json, os, re, shutil, subprocess, sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import held_check  # noqa: E402


def _fresh_daily_movers(dst, snap):
    """A daily-movers day for the snapshot date itself (the balanced-morning state), copied from the newest committed day."""
    days = sorted(d for d in glob.glob(os.path.join(dst, "data", "daily-movers", "20*")) if os.path.isdir(d))
    new = os.path.join(dst, "data", "daily-movers", snap.isoformat())
    if days and not os.path.isdir(new):
        old = os.path.basename(days[-1])
        shutil.copytree(days[-1], new)
        mp = os.path.join(new, "meta.json")
        m = json.load(open(mp))
        frm = (snap - dt.timedelta(days=1)).isoformat()
        m.update(snapshot_date=snap.isoformat(), to_date=snap.isoformat(), from_date=frm, window_days=1)
        m["method"] = m.get("method", "").replace(old, snap.isoformat())
        json.dump(m, open(mp, "w"), indent=2)


def _repo_copy_with_next_day_cut(tmp):
    dst = os.path.join(tmp, "repo")
    shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(".git", "_site", "__pycache__", ".pytest_cache"))
    cuts = sorted(glob.glob(os.path.join(dst, "data", "panel", "20*", "meta.json")))
    meta = json.load(open(cuts[-1]))
    snap = dt.date.fromisoformat(meta["snapshot_date"])
    cut = (snap + dt.timedelta(days=1)).isoformat()
    new = os.path.join(dst, "data", "panel", cut)
    if not os.path.isdir(new):
        shutil.copytree(os.path.dirname(cuts[-1]), new)
        meta["cut_date"] = cut
        json.dump(meta, open(os.path.join(new, "meta.json"), "w"), indent=2)
    _fresh_daily_movers(dst, snap)
    return dst, snap, cut


def test_footer_dates_equal_snapshot_data_date_all_languages(tmp_path):
    repo, snap, cut = _repo_copy_with_next_day_cut(str(tmp_path))
    out = os.path.join(str(tmp_path), "site")
    subprocess.run([sys.executable, os.path.join(repo, "scripts", "build_site.py"), "--out", out],
                   cwd=repo, capture_output=True, text=True, timeout=600)
    bad, seen = [], 0
    for lg, lp in held_check.LANGS.items():
        for p in held_check.PAGES:
            f = os.path.join(out, lp + p + ("index.html" if p in ("", "movers/") else ""))
            if not os.path.exists(f):
                continue
            raw = open(f, encoding="utf-8").read()
            bad += [b for b in held_check.check_page(lp + p or "/", raw, lg, snap) if b.startswith("R3 ")]
            _, foot = held_check.vis(raw)
            ds = held_check.dates(foot)
            seen += 1
            assert ds, f"{lp + p or '/'}: no date in footer"
            bad += [f"{lp + p or '/'}: footer date {txt!r} ({d}) != snapshot data date {snap} (cut {cut})"
                    for _, _, d, txt in ds if d != snap]
    assert seen >= 6, f"only {seen} pages built"
    assert not bad, "\n".join(bad)
