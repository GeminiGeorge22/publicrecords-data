"""FB-PACK: niches may intentionally use a longer exact counter window than shops."""
import os, subprocess, sys, tempfile
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def test_fb_pack_accepts_declared_separate_niche_window(tmp_path):
    with tempfile.TemporaryDirectory(dir=str(tmp_path)) as out:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "make_fb_pack.py"),
                            "--repo", ROOT, "--day", "2026-11-04", "--out-root", out],
                           cwd=ROOT, capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stdout + "\n" + r.stderr
        pack = open(os.path.join(out, "2026-11-04", "pack.md"), encoding="utf-8").read()
        assert "Which Etsy niches added the most sales in 2 days?" in pack
        assert "Nov 2 → Nov 4" in pack
