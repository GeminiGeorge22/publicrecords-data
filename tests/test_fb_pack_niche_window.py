"""FB-PACK: niches may intentionally use a longer exact counter window than shops."""
import csv, importlib.util, json, os, sys
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def _module():
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import fb_pack_windows
    return fb_pack_windows


def test_niche_window_validation_uses_its_declared_metadata(tmp_path):
    mod = _module()
    dd = tmp_path / "data" / "daily-movers" / "2026-11-04"
    dd.mkdir(parents=True)
    meta = {"snapshot_date": "2026-11-04", "from_date": "2026-11-03", "to_date": "2026-11-04", "window_days": 1,
            "niche_from_date": "2026-11-02", "niche_window_days": 2}
    (dd / "meta.json").write_text(json.dumps(meta))
    fields = ["rank", "from_date", "to_date", "window_days"]
    for fn in ("movers.csv", "pct.csv", "rising.csv"):
        with open(dd / fn, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
            for i in range(5): w.writerow({"rank": i + 1, "from_date": "2026-11-03", "to_date": "2026-11-04", "window_days": 1})
    with open(dd / "niches.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for i in range(5): w.writerow({"rank": i + 1, "from_date": "2026-11-02", "to_date": "2026-11-04", "window_days": 2})
    D = mod.load_rows(str(tmp_path), "2026-11-04")
    assert len(D["niches"]) == 5
    # A niches row incorrectly forced into the main one-day window remains red.
    rows = list(csv.DictReader(open(dd / "niches.csv")))
    rows[0]["from_date"] = "2026-11-03"
    with open(dd / "niches.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    try:
        mod.load_rows(str(tmp_path), "2026-11-04")
    except ValueError as e:
        assert "niches row 1" in str(e)
    else:
        raise AssertionError("mismatched niche row was not rejected")
