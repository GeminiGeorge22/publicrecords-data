import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import box_refresh as br


def test_velocity_verdict_requires_explicit_true():
    assert br.velocity_verdict({'balanced': True}) == 'balanced'
    assert br.velocity_verdict({'balanced': False}) == 'held_unbalanced'
    assert br.velocity_verdict({'snapshot_date': '2026-11-03'}) == 'held_unbalanced'
    assert br.velocity_verdict(None) == 'held_unbalanced'


def test_one_verdict_is_the_gate_used_by_site():
    src = open(br.__file__).read()
    assert 'if velocity_verdict(latest) == "balanced":' in src
    assert 'def sweep_balanced(' not in src


def test_must_stay_red_unbalanced_and_missing_never_publish():
    for manifest in ({'balanced': False}, {'balanced': 'true'}, {}, None):
        assert br.velocity_verdict(manifest) != 'balanced'
