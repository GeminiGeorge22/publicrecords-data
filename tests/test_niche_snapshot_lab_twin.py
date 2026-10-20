"""SR-1 (t930u D-3): the owner-run niche snapshot starts the Etsy Search lab twin, never the public Actor."""
import re
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "scripts" / "niche_snapshot.py").read_text()


def test_niche_snapshot_runs_lab_twin():
    assert re.search(r"^ACTOR = \"kFQaVNjukfplrm1kf\"", SRC, re.M)


def test_niche_snapshot_never_starts_public_actor():
    for m in re.finditer(r"/acts/\{(\w+)\}/runs", SRC):
        assert m.group(1) == "ACTOR"
    assert "/acts/JbNpPvG1Z7YtM9onP" not in SRC
