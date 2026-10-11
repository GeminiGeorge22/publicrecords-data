"""Prior count 0 / missing is never rankable (Marketer report 2026-10-11: MelDan0282 0 -> 282 ranked #1 Rising)."""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import movers_rank  # noqa: E402
import export_panel_cut  # noqa: E402

SNAP_DATE = "2026-10-10"
END = (dt.date(2026, 10, 10) - dt.date(2026, 1, 1)).days

C = {"window_days_preferred": [1], "min_valid_shops": 1, "top_n": 10,
     "pct_list": {"enabled": True, "min_base_sales": 0, "min_added": 1},
     "rising_list": {"enabled": True, "max_total_sales": 999, "min_added": 1},
     "niche_list": {"enabled": False},
     "guards": {"max_jump_ratio": 0.5, "require_exact_precision": True, "drop_vintage_events": True,
                "require_snapshot_match": True},
     "exclude_shops": []}


def read(day, sales):
    return [day, sales, None, 0, 36, None, None, 0]


def shop(name, prev_sales, last_sales, prev=True):
    reads = ([read(END - 1, prev_sales)] if prev else []) + [read(END, last_sales)]
    st = {"reads": reads, "title": name}
    sn = {"shop": name, "sales_count": last_sales, "sales_precision": "exact", "sales_precision_prev": 0,
          "sales_precision_last": 0, "vintage_event": False, "category": None}
    return st, sn


def build(**shops):
    state, snap = {}, {}
    for name, (p, l, has_prev) in shops.items():
        state[name], snap[name] = shop(name, p, l, has_prev)
    return snap, state


def all_ranked(R):
    return {r["shop"] for k in ("movers", "pct", "rising") for r in R[k]}


def test_prior_zero_not_rankable():
    snap, state = build(MelDan0282=(0, 282, True), Good=(500, 520, True))
    R = movers_rank.compute(snap, state, SNAP_DATE, C)
    assert "MelDan0282" not in all_ranked(R)
    assert [r["shop"] for r in R["rising"]] == ["Good"]
    assert R["tried"][1]["excluded"].get("no_prior_count") == 1
    nr = {r["shop"]: r for r in R["not_rankable"]}
    assert nr["MelDan0282"]["sales_added"] is None
    assert nr["MelDan0282"]["pct_added"] is None
    assert nr["MelDan0282"]["reason"] == "no prior count"


def test_prior_missing_not_rankable():
    snap, state = build(NoPrev=(0, 282, False), Good=(500, 520, True))
    state["NullPrev"] = {"reads": [read(END - 1, None), read(END, 300)], "title": "NullPrev"}
    snap["NullPrev"] = shop("NullPrev", 1, 300)[1]
    R = movers_rank.compute(snap, state, SNAP_DATE, C)
    assert all_ranked(R) == {"Good"}
    assert R["tried"][1]["excluded"].get("no_read_1d_earlier") == 2
    for r in R["movers"] + R["pct"] + R["rising"]:
        assert r["pct_added"] is not None and r["sales_before"] > 0


def test_pct_list_never_sees_null_pct():
    snap, state = build(Zero=(0, 50, True), Good=(100, 130, True))
    R = movers_rank.compute(snap, state, SNAP_DATE, C)
    assert [r["shop"] for r in R["pct"]] == ["Good"]


def test_panel_movers_prior_zero_not_rankable():
    """export_panel_cut.movers_from (panel Top Movers / rising cut): a first read of 0 is no prior count."""
    snap, state = build(ZeroFirst=(0, 900, True), Good=(600, 700, True))
    m = export_panel_cut.movers_from(snap, state, 0)
    assert [x["shop"] for x in m] == ["Good"]
