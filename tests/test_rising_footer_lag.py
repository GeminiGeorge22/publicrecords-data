"""SITE-PUBLISH-1 (Claude t840u): when daily-movers trails the panel snapshot by 1 day (HF snapshot unbalanced /
held_unbalanced — rising needs a balanced pair), rising + home footers must use the rising data's own day (or say Held),
and held_check must pass with R3 still strict.

Red on old code: page()/loc_page footers printed ctx['snap'] while the body newest day is D['day'], and held_mode only
fired when lag > 1, so a 1-day trail failed R3 (and R1/R2 on the window from_date).
"""
import datetime as dt, glob, json, os, re, shutil, subprocess, sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import held_check  # noqa: E402


def _lag_fixture(tmp):
    """Panel snap = newest daily-movers day + 1; do NOT mint movers for the new snap (today's held_unbalanced state)."""
    dst = os.path.join(tmp, "repo")
    shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(".git", "_site", "__pycache__", ".pytest_cache"))
    cuts = sorted(glob.glob(os.path.join(dst, "data", "panel", "20*", "meta.json")))
    meta = json.load(open(cuts[-1]))
    day = os.path.basename(sorted(d for d in glob.glob(os.path.join(dst, "data", "daily-movers", "20*")) if os.path.isdir(d))[-1])
    snap = dt.date.fromisoformat(day) + dt.timedelta(days=1)
    cut = (snap + dt.timedelta(days=1)).isoformat()
    new = os.path.join(dst, "data", "panel", cut)
    if not os.path.isdir(new):
        shutil.copytree(os.path.dirname(cuts[-1]), new)
    meta["cut_date"] = cut
    meta["snapshot_date"] = snap.isoformat()
    json.dump(meta, open(os.path.join(new, "meta.json"), "w"), indent=2)
    return dst, snap, day, cut


def test_rising_footer_uses_data_day_when_movers_trail_snapshot(tmp_path):
    repo, snap, day, cut = _lag_fixture(str(tmp_path))
    out = os.path.join(str(tmp_path), "site")
    r = subprocess.run([sys.executable, os.path.join(repo, "scripts", "build_site.py"), "--out", out],
                       cwd=repo, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, (r.stdout + "\n" + r.stderr)[-2000:]
    day_d = dt.date.fromisoformat(day)
    bad, seen = [], 0
    for lg, lp in held_check.LANGS.items():
        for p in ("", "rising.html"):  # home + rising (the pages that read D['day'] into the body)
            f = os.path.join(out, lp + p + ("index.html" if p == "" else ""))
            if not os.path.exists(f):
                continue
            raw = open(f, encoding="utf-8").read()
            url = lp + p or "/"
            findings = held_check.check_page(url, raw, lg, snap)
            bad += findings
            _, foot = held_check.vis(raw)
            ds = held_check.dates(foot)
            seen += 1
            held_word = re.search(held_check.HELD[lg], foot, re.I)
            # Footer names the rising/home data day, or says Held (R3 allows either).
            assert held_word or (ds and all(d == day_d for _, _, d, _ in ds)), (
                f"{url}: footer must equal data day {day} or say Held; foot={foot.strip()[-180:]!r}"
            )
    assert seen >= 4, f"only {seen} home/rising pages built"
    assert not bad, "held_check findings on lag fixture:\n" + "\n".join(bad)
