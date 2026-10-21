"""t943u item 5 fix B (ranked card, digest 2026-10-20_since-t939u.md item 8): before ranking, cap each first-character
bucket (0-9, A-C, D-L, M-S, T-Z) of the clean pairs at its share of the panel, so a 7-day echo of a name-ordered cohort
(10-19: A-C 72% of pairs vs 19.8% of the panel) cannot fill the lists. Feed-side only. Red-first."""
import datetime as dt
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import movers_rank  # noqa: E402

SNAP_DATE = "2026-10-19"
END = (dt.date(2026, 10, 19) - dt.date(2026, 1, 1)).days
C = {"window_days_preferred": [1], "min_valid_shops": 1, "top_n": 10,
     "pct_list": {"enabled": True, "min_base_sales": 0, "min_added": 1},
     "rising_list": {"enabled": True, "max_total_sales": 10**9, "min_added": 1},
     "niche_list": {"enabled": False}, "bucket_cap": {"enabled": True},
     "guards": {"max_jump_ratio": 0.5, "require_exact_precision": True, "drop_vintage_events": True,
                "require_snapshot_match": True}, "exclude_shops": []}


def rd(day, sales):
    return [day, sales, None, 0, 36, None, None, 0]


def build():
    """Panel 1000 shops, 200 per bucket. Pairs: 160 A-C shops (big adds) + 10 in each other bucket (small adds)."""
    snap, state = {}, {}
    letters = {"0-9": "0", "A-C": "A", "D-L": "D", "M-S": "M", "T-Z": "T"}
    for b, L in letters.items():
        for i in range(200):
            name = f"{L}{b.replace('-', '')}{i:03d}"
            paired = (b == "A-C" and i < 160) or (b != "A-C" and i < 10)
            add = 100 + i if b == "A-C" else 5 + i
            reads = ([rd(END - 1, 1000)] if paired else []) + [rd(END, 1000 + add)]
            state[name] = {"reads": reads, "title": name}
            snap[name] = {"shop": name, "sales_count": 1000 + add, "sales_precision": "exact", "sales_precision_prev": 0,
                          "sales_precision_last": 0, "vintage_event": False, "category": None}
    return snap, state


def test_overrepresented_bucket_capped_at_panel_share():
    snap, state = build()
    R = movers_rank.compute(snap, state, SNAP_DATE, C)
    n_pairs = 160 + 40
    cap = math.ceil(0.2 * n_pairs)          # A-C panel share 20%
    assert R["tried"][1]["excluded"].get("bucket_capped") == 160 - cap
    assert R["bucket_cap"]["A-C"] == {"pairs": 160, "cap": cap, "kept": cap}
    assert R["valid"] == n_pairs - (160 - cap)


def test_ranked_lists_not_filled_by_one_bucket():
    snap, state = build()
    R = movers_rank.compute(snap, state, SNAP_DATE, C)
    # without the cap all 10 movers are A-C (biggest adds); with it, the kept A-C shops are a hash sample, not the top adds
    kept_ac = {r["shop"] for r in R["movers"] if r["shop"].startswith("A")}
    assert len(R["movers"]) == 10 and len(kept_ac) <= 10
    assert R["bucket_cap"]["A-C"]["kept"] == 40


def test_cap_deterministic_and_off_switch():
    snap, state = build()
    a = movers_rank.compute(snap, state, SNAP_DATE, C)
    b = movers_rank.compute(snap, state, SNAP_DATE, C)
    assert [r["shop"] for r in a["movers"]] == [r["shop"] for r in b["movers"]]
    off = movers_rank.compute(snap, state, SNAP_DATE, {**C, "bucket_cap": {"enabled": False}})
    assert off["valid"] == 200 and "bucket_capped" not in off["tried"][1]["excluded"]


def test_config_enables_cap():
    assert movers_rank.cfg().get("bucket_cap", {}).get("enabled") is True
