"""SITE-R1 (STATUS-9 t991u item 3, C8): the en home 'Niche Prices' card states the niche snapshot's cadence in the same
sentence as its capture date, so held_check R1 (SITE-HELD-1d cadence rule) passes while that date is within cadence + 1 day.

On 2026-10-24 the morning publish built a next-day cut and held_check R1 refused en / for the card line
'... in the niches of the top movers, read Oct 19, 2026.' (no held word, no cadence). This test builds the same next-day
cut (the FOOTER-DATE-1 helper) and asserts that card carries 'refreshed weekly' and that the full held check (R1-R4, all
nine pages) the publish path runs has zero findings.

MEMO-1g row 2 (2026-11-02): since SITE-UNSTICK-1 (#17) the card's wording follows the capture's age. Within
niche_cadence_days + 1 (8) days of the newest snapshot it says 'refreshed weekly'; older it says 'held — refresh paused'
and must NOT say 'refreshed weekly'. The expected wording is computed from the repo's own niche capture date, so this
test stays strict in both states. The held check is unchanged; R1 must have zero findings either way."""
import datetime as dt, glob, json, os, re, subprocess, sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import held_check  # noqa: E402
from test_footer_date import _repo_copy_with_next_day_cut  # noqa: E402


def _build(tmp):
    repo, snap, cut = _repo_copy_with_next_day_cut(tmp)
    out = os.path.join(tmp, "site")
    r = subprocess.run([sys.executable, os.path.join(repo, "scripts", "build_site.py"), "--out", out],
                       cwd=repo, capture_output=True, text=True, timeout=600)
    return repo, out, snap, r


def _niche_age_days(repo, snap):
    nm = sorted(glob.glob(os.path.join(repo, "data", "niche", "20*", "meta.json")))[-1]
    m = json.load(open(nm))
    cap = dt.date.fromisoformat((m.get("captured_at") or m.get("cut"))[:10])
    cad = json.load(open(os.path.join(repo, "config", "publish.json"))).get("niche_cadence_days", 7) \
        if os.path.exists(os.path.join(repo, "config", "publish.json")) else 7
    return (snap - cap).days, cad


def test_home_niche_card_states_cadence_in_its_sentence(tmp_path):
    repo, out, snap, _ = _build(str(tmp_path))
    raw = open(os.path.join(out, "index.html"), encoding="utf-8").read()
    body, _ = held_check.vis(raw)
    m = re.search(r"in the niches of the top movers, captured [^.]*\.", body)
    age, cad = _niche_age_days(repo, snap)
    if age <= cad:
        assert m, "en home Niche Prices card sentence not found for fresh capture"
        assert re.search(held_check.CADENCE["en"], m.group(0)), f"no cadence in card sentence: {m.group(0)!r}"
    else:
        assert not m, f"aged {age}d capture still has a home Niche Prices card"
        assert "Niche Prices" not in body
    r1 = [b for b in held_check.check_page("/", raw, "en", snap) if b.startswith("R1 ")]
    assert not r1, "\n".join(r1)


def test_next_day_cut_passes_full_held_check_all_pages(tmp_path):
    _, out, snap, r = _build(str(tmp_path))
    bad, seen = [], 0
    for lg, lp in held_check.LANGS.items():
        for p in held_check.PAGES:
            f = os.path.join(out, lp + p + ("index.html" if p in ("", "movers/") else ""))
            if not os.path.exists(f):
                continue
            seen += 1
            bad += held_check.check_page(lp + p or "/", open(f, encoding="utf-8").read(), lg, snap)
    assert seen == 9, f"only {seen} of 9 pages built (build rc {r.returncode}: {(r.stderr or r.stdout)[-300:]})"
    assert not bad, "\n".join(bad)
    assert r.returncode == 0, (r.stderr or r.stdout)[-400:]
