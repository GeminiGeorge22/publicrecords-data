"""READ-ORDER-2: the sweep feed publishes only when the snapshot manifest says balanced=true."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import box_refresh as br


def test_gate_requires_balanced_true():
    assert br.velocity_verdict({"balanced": True}) == "balanced"
    assert br.velocity_verdict({"balanced": False}) == "held_unbalanced"
    assert br.velocity_verdict({"snapshot_date": "2026-10-15"}) == "held_unbalanced"   # old manifest without the field: held
    assert br.velocity_verdict({"balanced": "true"}) == "held_unbalanced"
    assert br.velocity_verdict(None) == "held_unbalanced"


def test_publish_skips_movers_export_when_unbalanced(monkeypatch):
    calls = []
    monkeypatch.setattr(br, "daily_movers_export", lambda: calls.append("export") or "ok")
    src = open(br.__file__).read()
    assert 'if velocity_verdict(latest) == "balanced":\n            movers_status = daily_movers_export()' in src
    assert 'movers_status = "held_unbalanced"' in src
    # cards/posts only run on movers_status == "ok"
    assert 'if sha and movers_status == "ok":' in src
