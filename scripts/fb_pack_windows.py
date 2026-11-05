"""Exact per-table window validation for the daily Facebook pack (standard library only)."""
import csv, json, os


def load_rows(repo, day):
    dd = os.path.join(repo, "data", "daily-movers", day)
    meta = json.load(open(os.path.join(dd, "meta.json")))
    rd = lambda f: list(csv.DictReader(open(os.path.join(dd, f), encoding="utf-8"))) if os.path.exists(os.path.join(dd, f)) else []
    D = {"meta": meta, "shops": rd("movers.csv"), "jumps": rd("pct.csv"), "niches": rd("niches.csv"), "rising": rd("rising.csv")}
    if meta.get("snapshot_date") != day:
        raise ValueError(f"{day}: meta snapshot_date {meta.get('snapshot_date')} != folder day: mismatched export")
    for k in ("shops", "jumps", "rising"):
        if len(D[k]) < 5:
            raise ValueError(f"{day}: {k} has {len(D[k])} rows (<5): incomplete export")
    if len(D["niches"]) < 5:
        D["niches"] = []
    for k in ("shops", "jumps", "niches", "rising"):
        prefix = "niche_" if k == "niches" else ""
        frm = meta[prefix + "from_date"] if k == "niches" else meta["from_date"]
        w = int(meta[prefix + "window_days"] if k == "niches" else meta["window_days"])
        for r in D[k]:
            if r["to_date"] != day or r["from_date"] != frm or int(r["window_days"]) != w:
                raise ValueError(f"{day}: {k} row {r.get('rank')} window {r['from_date']}->{r['to_date']} != declared {frm}->{day} ({w}d)")
    return D
