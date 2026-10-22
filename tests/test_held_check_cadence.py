"""SITE-HELD-1d (Claude t793u item 1): an older date passes R1 only when its own sentence carries its cadence
("refreshed weekly") and it is within that cadence; an old date with no qualifier still fails."""
import datetime as dt, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import held_check as hc

NEWEST = dt.date(2026, 10, 21)
OLD = ("<main><p>The top results of an Etsy search for keywords taken from the top movers' categories, captured 2026-10-19 "
       "with our Etsy Search Scraper (Apify run vTDBxDixpNeG85Vkf). Typical price is the middle price.</p></main>")
NEW = ("<main><p>Niche keywords are refreshed weekly; this set was captured 2026-10-19 with our Etsy Search Scraper "
       "(next refresh Mon 10-26). Typical price is the middle price.</p></main>")


def r1(raw, newest=NEWEST):
    return [b for b in hc.check_page("/", raw, "en", newest) if b.startswith("R1")]


def test_old_date_without_qualifier_still_fails():
    assert len(r1(OLD)) == 1


def test_weekly_qualified_sentence_passes():
    assert r1(NEW) == []


def test_qualifier_in_another_sentence_does_not_excuse():
    raw = ("<main><p>Niche keywords are refreshed weekly. Shop counters were read 2026-10-19 for this page.</p></main>")
    assert len(r1(raw)) == 1


def test_qualified_date_older_than_its_cadence_fails():
    assert len(r1(NEW, newest=dt.date(2026, 10, 29))) == 1   # 10 days old: 'refreshed weekly' would be false


def test_qualifier_is_not_a_fresh_word():
    assert [b for b in hc.check_page("/", NEW, "en", NEWEST) if b.startswith("R2")] == []
