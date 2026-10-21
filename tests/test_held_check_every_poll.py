import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import pytest
import box_refresh as br


def test_held_check_runs_when_hf_fetch_fails(monkeypatch):
    calls = []
    def boom():
        raise RuntimeError("HTTP Error 429: Too Many Requests")
    monkeypatch.setattr(br, "hf_latest", boom)
    monkeypatch.setattr(br, "do_held_check", lambda: calls.append("held"))
    with pytest.raises(RuntimeError):
        br.do_poll()
    assert calls == ["held"]


def test_held_check_logs_every_poll(monkeypatch, tmp_path):
    monkeypatch.setattr(br, "LOG", str(tmp_path / "log"))
    monkeypatch.setattr(br, "STATE", str(tmp_path / "state.json"))
    class R:
        returncode = 0
        stdout = "held_check PASS: 9 pages, 0 findings\n"
        stderr = ""
    monkeypatch.setattr(br.subprocess, "run", lambda *a, **k: R())
    br.do_held_check()
    br.do_held_check()
    lines = open(tmp_path / "log").read().splitlines()
    assert len(lines) == 2 and all("job=held_check status=pass" in l for l in lines)
