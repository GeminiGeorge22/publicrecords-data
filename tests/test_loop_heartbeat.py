"""LOOP-HB-1 (Claude t793u item 2): the refresh loop writes a heartbeat; a checker pages (RED file + exit 1) when it is
silent > 30 min or missing, and clears to GREEN on a fresh heartbeat from a live pid."""
import datetime as dt, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import loop_heartbeat_check as hb
import box_refresh as br


def _hb(path, minutes_ago, pid):
    at = dt.datetime.now(br.ET) - dt.timedelta(minutes=minutes_ago)
    json.dump({"at": at.isoformat(timespec="seconds"), "pid": pid}, open(path, "w"))


def test_stale_heartbeat_pages_red(tmp_path):
    f, alerts = tmp_path / "hb.json", tmp_path / "alerts"
    _hb(f, 31, os.getpid())
    rc, line = hb.check(str(f), str(alerts), max_silent_min=30)
    assert rc == 1 and line.startswith("RED") and (alerts / "site-loop-heartbeat.RED").exists()


def test_missing_heartbeat_pages_red(tmp_path):
    rc, line = hb.check(str(tmp_path / "none.json"), str(tmp_path / "alerts"), max_silent_min=30)
    assert rc == 1 and "missing" in line


def test_dead_pid_pages_red_even_if_recent(tmp_path):
    f = tmp_path / "hb.json"
    _hb(f, 1, 999999999)
    rc, line = hb.check(str(f), str(tmp_path / "alerts"), max_silent_min=30)
    assert rc == 1 and "not running" in line


def test_fresh_heartbeat_is_green_and_clears_red(tmp_path):
    f, alerts = tmp_path / "hb.json", tmp_path / "alerts"
    _hb(f, 31, os.getpid()); hb.check(str(f), str(alerts), max_silent_min=30)
    _hb(f, 0, os.getpid())
    rc, line = hb.check(str(f), str(alerts), max_silent_min=30)
    assert rc == 0 and line.startswith("GREEN") and not (alerts / "site-loop-heartbeat.RED").exists()


def test_loop_writes_heartbeat(tmp_path, monkeypatch):
    monkeypatch.setattr(br, "HEARTBEAT", str(tmp_path / "hb.json"))
    br.heartbeat(next_poll=dt.datetime.now(br.ET))
    d = json.load(open(tmp_path / "hb.json"))
    assert d["pid"] == os.getpid() and dt.datetime.fromisoformat(d["at"]).tzinfo is not None
