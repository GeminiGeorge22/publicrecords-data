"""Each window label belongs to its own section, not to the page as a whole.

A current balanced one-day movers window must not inherit held wording from
its longer niche window. A genuinely held main window must retain its warning.
"""
import datetime as dt
import os
import re
import sys

import pytest

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import held_mode  # noqa: E402


WORDS = {"en": "held", "fr": "retenue", "tr": "bekletiliyor"}
EYEBROWS = {
    "en": "Etsy Pulse · Daily movers",
    "fr": "Etsy Pulse · Palmarès du jour",
    "tr": "Etsy Pulse · Günlük yükselenler",
}


def _page(eyebrow, main, niche):
    return (f'<html><body><nav>navigation</nav><div class="eyebrow">{eyebrow}</div>'
            f'<main class="wrap"><div class="fresh"></div><section>'
            f'<div class="dmwin">{main}</div></section>'
            f'<section id="niches"><div class="dmwin">{niche}</div></section></main></body></html>')


def _render(tmp_path, main_from, niche_from, main_held):
    out = tmp_path / "site"
    out.mkdir()
    for lang, prefix in (("en", ""), ("fr", "fr/"), ("tr", "tr/")):
        target = out / prefix
        target.mkdir(exist_ok=True)
        (target / "index.html").write_text(_page(
            EYEBROWS[lang], f"Sales added in 24 hours, {main_from} → Nov 4",
            f"Sales added in 2 days, {niche_from} → Nov 4"), encoding="utf-8")
    # The producer verdict selects the mode; the start date selects which
    # section's local window label is being rendered.
    held_mode.apply(str(out), main_from if main_held else niche_from, "2026-11-04",
                    lambda iso, lang: dt.date.fromisoformat(iso).strftime("%b %-d"), lambda iso, lang: iso,
                    through_day="2026-11-04", stale=main_held)
    return out


@pytest.mark.parametrize("lang,prefix", (("en", ""), ("fr", "fr/"), ("tr", "tr/")))
def test_balanced_main_does_not_inherit_held_niche_label(tmp_path, lang, prefix):
    out = _render(tmp_path, "2026-11-03", "2026-11-02", main_held=False)
    raw = (out / prefix / "index.html").read_text(encoding="utf-8")
    eyebrow = re.search(r'<div class="eyebrow">(.*?)</div>', raw).group(1)
    assert eyebrow == EYEBROWS[lang]
    assert WORDS[lang] not in eyebrow
    assert WORDS[lang] in raw  # the niche section keeps its own warning


def test_held_main_window_must_say_held(tmp_path):
    out = _render(tmp_path, "2026-11-02", "2026-11-02", main_held=True)
    raw = (out / "index.html").read_text(encoding="utf-8")
    eyebrow = re.search(r'<div class="eyebrow">(.*?)</div>', raw).group(1)
    assert "Held since" in eyebrow
    assert 'class="heldbar"' in raw
