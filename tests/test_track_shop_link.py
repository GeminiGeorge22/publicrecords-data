"""FIRST-USERS-ETSY (t840u): every public page links to Velocity Store with CLICKS-1 site UTM;
shop rows carry a localized 'track this shop's sales' link. R1/R2/R3 stay strict.
"""
import glob, os, re, shutil, subprocess, sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import build_site  # noqa: E402
import held_check  # noqa: E402

R_TRACK = "https://publicrecords-redirect.publicrecords.workers.dev/r/site-store-tracker"
UTM = "utm_source=site&utm_medium=web&utm_campaign=etsypulse&utm_content=track-shop"
MARKER = "utm_content=track-shop"
LABELS = {
    "en": "Track this shop's sales",
    "fr": "Suivre les ventes de cette boutique",
    "tr": "Bu mağazanın satışlarını izle",
}


def test_track_shop_href_utm():
    href = build_site.track_shop_href("StonehousePotteryOH")
    assert href.startswith(R_TRACK + "?")
    assert UTM in href
    assert "utm_term=StonehousePotteryOH" in href
    href_fr = build_site.track_shop_href("StonehousePotteryOH", "fr")
    assert "t=fr" in href_fr and MARKER in href_fr


def test_track_shop_labels_localized():
    import html as _html
    assert LABELS["en"] in _html.unescape(build_site.track_shop_a("en"))
    fr = build_site.load_loc("fr")
    tr = build_site.load_loc("tr")
    assert LABELS["fr"] in _html.unescape(build_site.track_shop_a("fr", fr))
    assert LABELS["tr"] in _html.unescape(build_site.track_shop_a("tr", tr))
    assert R_TRACK in build_site.track_shop_a("fr", fr)
    assert "t=fr" in build_site.track_shop_a("fr", fr)


def test_built_pages_carry_track_link_and_held_strict(tmp_path):
    out = os.path.join(str(tmp_path), "site")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build_site.py"), "--out", out],
                       cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, (r.stdout + "\n" + r.stderr)[-2500:]

    # Sample pages that must exist in every locale + EN rising/home
    samples = [
        ("en", "index.html"),
        ("en", "rising.html"),
        ("fr", "fr/index.html"),
        ("tr", "tr/index.html"),
        ("fr", "fr/rising.html"),
        ("tr", "tr/rising.html"),
    ]
    # also movers if present
    if os.path.isdir(os.path.join(out, "movers")):
        samples.append(("en", "movers/index.html"))
    if os.path.isdir(os.path.join(out, "fr", "movers")):
        samples.append(("fr", "fr/movers/index.html"))

    for lang, rel in samples:
        path = os.path.join(out, rel)
        assert os.path.exists(path), rel
        raw = open(path, encoding="utf-8").read()
        n = raw.count(MARKER)
        assert n >= 1, f"{rel}: expected >=1 {MARKER}, got {n}"
        assert "site-store-tracker" in raw, f"{rel}: missing /r/site-store-tracker hand-off"
        assert "https://apify.com/publicrecords/etsy-shop-velocity" not in raw, f"{rel}: direct Store href (BEACON-1)"
        import html as _html
        assert LABELS[lang] in _html.unescape(raw), f"{rel}: missing localized label {LABELS[lang]!r}"
        # shop tables: when present, per-row links include utm_term
        if 'class="nm"' in raw and "role=\"table\"" in raw:
            assert "utm_term=" in raw, f"{rel}: shop rows should carry utm_term"

    # R1/R2/R3 stay strict on home + rising for all langs (same as SITE-PUBLISH-1)
    snap = None
    cuts = sorted(glob.glob(os.path.join(ROOT, "data", "panel", "20*", "meta.json")))
    if cuts:
        import json
        snap = __import__("datetime").date.fromisoformat(json.load(open(cuts[-1]))["snapshot_date"])
    bad = []
    for lg, lp in held_check.LANGS.items():
        for p in ("", "rising.html"):
            f = os.path.join(out, lp + p + ("index.html" if p == "" else ""))
            if not os.path.exists(f) or snap is None:
                continue
            bad += held_check.check_page(lp + p or "/", open(f, encoding="utf-8").read(), lg, snap)
    assert not bad, "held_check R1/R2/R3 findings:\n" + "\n".join(bad)
