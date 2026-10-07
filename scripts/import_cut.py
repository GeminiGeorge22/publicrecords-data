#!/usr/bin/env python3
"""Import a Velocity top-movers cut into data/top-movers/ with public columns only.

Usage: python scripts/import_cut.py path/to/YYYY-MM-DD.csv [more.csv ...]

Keeps only section=top20_7d and the columns the public page shows
(rank, shop_name, shop_url, category, sales_7d_delta, cut_date).
Totals, method/span columns and the other sections are dropped on purpose.
Public files keep the top PUBLIC_N (10) rows only (t518u: free = top 10).
"""
import csv
import os
import re
import sys

PUBLIC_COLS = ["rank", "shop_name", "shop_url", "category", "sales_7d_delta", "cut_date"]
PUBLIC_N = 10
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "top-movers")


def import_one(path):
    name = os.path.basename(path)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}\.csv", name):
        raise SystemExit(f"skip {path}: expected YYYY-MM-DD.csv")
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if rows and "section" in rows[0]:
        rows = [r for r in rows if r.get("section") == "top20_7d"]
    if not rows:
        raise SystemExit(f"{path}: no top20_7d rows")
    for r in rows:
        r.setdefault("cut_date", name[:-4])
        if not r.get("cut_date"):
            r["cut_date"] = name[:-4]
    rows.sort(key=lambda r: int(r["rank"]))
    rows = rows[:PUBLIC_N]
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, name)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=PUBLIC_COLS, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {os.path.normpath(out)} ({len(rows)} rows)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    for p in sys.argv[1:]:
        import_one(p)
