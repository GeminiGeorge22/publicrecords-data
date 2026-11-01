"""SITE-UNSTICK-1 (MEMO-1f row 1a, 2026-11-01): the niche line is computed from its capture date, and buyer pages carry
no Apify run IDs and no next-refresh dates.

On 2026-10-28..11-01 every publish was skipped: the 10-31 snapshot made the Oct 19 niche capture 12 days old, past the
held check's cadence + 1 day, and the home page still said 'refreshed weekly' with no held word (held_check R1). Rules:
  capture <= niche_cadence_days + 1 (8) days older than the newest snapshot: 'captured <date>, refreshed weekly'
  older: 'captured <date>, held — refresh paused', with no next-refresh date.
The held check itself (scripts/held_check.py, build_site.check_public) is unchanged; these tests run it as the publish does."""
import datetime as dt, glob, html, json, os, re, subprocess, sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import held_check  # noqa: E402
from test_footer_date import _repo_copy_with_next_day_cut  # noqa: E402


def _set_niche_age(repo, snap, days):
    """Move the newest niche capture to `days` days before the newest snapshot."""
    nm = sorted(glob.glob(os.path.join(repo, "data", "niche", "20*", "meta.json")))[-1]
    m = json.load(open(nm))
    cap = snap - dt.timedelta(days=days)
    m["captured_at"] = cap.isoformat() + "T12:04:46.477Z"
    json.dump(m, open(nm, "w"), indent=2)
    return cap


def _build(tmp, niche_age=None):
    repo, snap, cut = _repo_copy_with_next_day_cut(tmp)
    cap = _set_niche_age(repo, snap, niche_age) if niche_age is not None else None
    out = os.path.join(tmp, "site")
    r = subprocess.run([sys.executable, os.path.join(repo, "scripts", "build_site.py"), "--out", out],
                       cwd=repo, capture_output=True, text=True, timeout=600)
    return repo, out, snap, cap, r


def _held_findings(out, snap):
    bad, seen = [], 0
    for lg, lp in held_check.LANGS.items():
        for p in held_check.PAGES:
            f = os.path.join(out, lp + p + ("index.html" if p in ("", "movers/") else ""))
            if os.path.exists(f):
                seen += 1
                bad += held_check.check_page(lp + p or "/", open(f, encoding="utf-8").read(), lg, snap)
    return seen, bad


def _nice(d):
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def _home_body(out):
    return held_check.vis(open(os.path.join(out, "index.html"), encoding="utf-8").read())[0]


def test_9_day_old_niche_renders_held_and_passes_held_check(tmp_path):
    repo, out, snap, cap, r = _build(str(tmp_path), niche_age=9)
    body = _home_body(out)
    assert f"captured {_nice(cap)}, held — refresh paused" in body, "home niche line does not say held"
    assert not re.search(r"captured " + re.escape(_nice(cap)) + r", refreshed weekly", body)
    assert not re.search(r"next refresh", body, re.I)
    seen, bad = _held_findings(out, snap)
    assert seen == 9, f"only {seen} of 9 pages built (rc {r.returncode}: {(r.stderr or r.stdout)[-400:]})"
    assert not bad, "\n".join(bad)
    assert r.returncode == 0, (r.stderr or r.stdout)[-400:]


def test_8_day_old_niche_renders_refreshed_weekly(tmp_path):
    repo, out, snap, cap, r = _build(str(tmp_path), niche_age=8)
    body = _home_body(out)
    assert f"captured {_nice(cap)}, refreshed weekly" in body, "home niche line does not say refreshed weekly"
    assert "held — refresh paused" not in body
    seen, bad = _held_findings(out, snap)
    assert seen == 9 and not bad, "\n".join(bad)
    assert r.returncode == 0, (r.stderr or r.stdout)[-400:]


def _run_ids(repo):
    ids = set()
    for f in glob.glob(os.path.join(repo, "data", "**", "meta.json"), recursive=True):
        try:
            m = json.load(open(f))
        except ValueError:
            continue
        if isinstance(m, dict):
            for k in ("run_id", "dataset_id", "build_id"):
                if isinstance(m.get(k), str) and len(m[k]) >= 10:
                    ids.add(m[k])
            ids.update(x for x in (m.get("extra_run_ids") or []) if isinstance(x, str))
    return ids


def _buyer_text(raw):
    """What a buyer or a search engine reads: the page minus scripts/styles and minus href/src targets (file names)."""
    raw = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    raw = re.sub(r'\s(?:href|src)="[^"]*"', " ", raw)
    return html.unescape(raw)


def test_no_run_id_or_next_refresh_on_any_buyer_page(tmp_path):
    repo, out, snap, cap, r = _build(str(tmp_path), niche_age=9)
    ids = _run_ids(repo)
    assert ids, "no run IDs found in data/*/meta.json (fixture broken)"
    bad = []
    for f in glob.glob(os.path.join(out, "**", "*.html"), recursive=True):
        t = _buyer_text(open(f, encoding="utf-8").read())
        rel = os.path.relpath(f, out)
        bad += [f"{rel}: run ID {i}" for i in ids if i in t]
        if re.search(r"next refresh|prochaine mise à jour|sonraki yenileme", t, re.I):
            bad.append(f"{rel}: next-refresh date")
    assert not bad, "\n".join(sorted(bad)[:40])
