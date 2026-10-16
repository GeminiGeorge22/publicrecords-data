"""READ-ORDER-2: the sweep feed publishes only when the snapshot manifest says balanced=true."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import box_refresh as br


def test_gate_requires_balanced_true():
    assert br.sweep_balanced({"balanced": True})
    assert not br.sweep_balanced({"balanced": False})
    assert not br.sweep_balanced({"snapshot_date": "2026-10-15"})   # old manifest without the field: held
    assert not br.sweep_balanced({"balanced": "true"})
    assert not br.sweep_balanced(None)


def test_publish_skips_movers_export_when_unbalanced(monkeypatch):
    calls = []
    monkeypatch.setattr(br, "daily_movers_export", lambda: calls.append("export") or "ok")
    src = open(br.__file__).read()
    assert "if sweep_balanced(latest):\n            movers_status = daily_movers_export()" in src
    assert 'movers_status = "held_unbalanced"' in src
    # cards/posts only run on movers_status == "ok"
    assert 'if sha and movers_status == "ok":' in src
