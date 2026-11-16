"""SITE-HELD-1e (MKT-NOTE-3 F1): a 'refreshed weekly' niche-price date newer than the daily movers cut does not
set the footer's data date (R3); an unqualified newer date still does."""
import datetime as dt, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import held_check as hc

NEWEST = dt.date(2026, 11, 16)
FOOT = "<footer><p>Movers cut 2026-11-15 (counters read through 2026-11-15).</p></footer>"


def r3(body):
    return [b for b in hc.check_page("/", "<main>" + body + "</main>" + FOOT, "en", NEWEST) if b.startswith("R3")]


def test_weekly_niche_date_newer_than_movers_passes():
    assert r3("<p>Shops on the move, 2026-11-15.</p><p>Niche prices captured 2026-11-16, refreshed weekly.</p>") == []


def test_unqualified_newer_date_still_fails():
    assert len(r3("<p>Shops on the move, 2026-11-15.</p><p>Shop counters read 2026-11-16.</p>")) == 1
