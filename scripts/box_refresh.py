#!/usr/bin/env python3
"""Box-side data refresh for Etsy Pulse (no credentials in GitHub).

  python scripts/box_refresh.py panel     # export a new panel cut if HF has a newer snapshot
  python scripts/box_refresh.py niche     # weekly niche snapshot (Apify, capped by --max-usd)
  python scripts/box_refresh.py loop      # scheduler: panel daily 07:30 ET, niche Mon 07:45 ET

Tokens come from the environment (HF_READ_TOKEN) and from the APIFY_TOKEN_FILE path
(default /home/box/apify-marketer/secrets/apify-publicrecords-api-token.txt).
Commits + pushes data/ to main only when files changed; Actions rebuilds the site.
Every attempt appends one status line to /workspace/x-etsypulse/data-refresh.log.
After a successful panel refresh it re-renders the X post images (make_posts.py) if present.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import glob
import json
import os
import subprocess
import sys
import time
import traceback
import urllib.request
from zoneinfo import ZoneInfo

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ET = ZoneInfo("America/Toronto")
LOG = os.environ.get("REFRESH_LOG", "/workspace/x-etsypulse/data-refresh.log")
LOCK = os.environ.get("REFRESH_LOCK", "/tmp/etsypulse-refresh.lock")
APIFY_TOKEN_FILE = os.environ.get("APIFY_TOKEN_FILE", "/home/box/apify-marketer/secrets/apify-publicrecords-api-token.txt")
POSTS = "/workspace/x-etsypulse/make_posts.py"
PANEL_AT = (7, 30)
NICHE_AT = (7, 45)  # Mondays


def now():
    return dt.datetime.now(ET)


def log(job, status, **kw):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    extra = " ".join(f"{k}={v}" for k, v in kw.items())
    line = f"{now().strftime('%Y-%m-%d %H:%M:%S %Z')} job={job} status={status} {extra}".rstrip()
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line, flush=True)


def sh(*cmd, env=None, check=True):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])}... rc={r.returncode}: {(r.stderr or r.stdout)[-400:]}")
    return r


def git_sync():
    sh("git", "fetch", "-q", "origin", "main")
    sh("git", "checkout", "-q", "main")
    sh("git", "pull", "-q", "--ff-only", "origin", "main")


def commit_push(paths, msg):
    sh("git", "add", *paths)
    if not sh("git", "status", "--porcelain", *paths).stdout.strip():
        return None
    sh("git", "-c", "user.name=publicrecords", "-c", "user.email=publicrecords@users.noreply.github.com",
       "commit", "-q", "-m", msg)
    sh("git", "push", "-q", "origin", "main")
    return sh("git", "rev-parse", "--short", "HEAD").stdout.strip()


def newest_panel_snapshot():
    metas = sorted(glob.glob(os.path.join(ROOT, "data", "panel", "*", "meta.json")))
    return json.load(open(metas[-1]))["snapshot_date"] if metas else None


def hf_latest():
    tok = (os.environ.get("HF_READ_TOKEN") or os.environ.get("HF_TOKEN") or "").strip()
    req = urllib.request.Request(
        "https://huggingface.co/datasets/Publicrecords/etsy-shop-velocity/resolve/main/latest.json",
        headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def do_panel(force=False):
    git_sync()
    latest = hf_latest()
    have = newest_panel_snapshot()
    if not force and have == latest["snapshot_date"]:
        log("panel", "no_new_snapshot", hf_snapshot=latest["snapshot_date"], have=have)
        return False
    cut = now().date().isoformat()
    sh(sys.executable, "scripts/export_panel_cut.py", "--cut-date", cut)
    meta = json.load(open(os.path.join(ROOT, "data", "panel", cut, "meta.json")))
    sha = commit_push(["data/panel"], f"panel cut {cut} (snapshot {meta['snapshot_date']}, box refresh)")
    log("panel", "ok" if sha else "unchanged", cut=cut, snapshot=meta["snapshot_date"],
        movers=meta["rows"]["movers"], categories=meta["rows"]["categories"], rising=meta["rows"]["rising"],
        shops=meta["shops_with_gain_ge_min"], commit=sha or "-")
    posts()
    return True


def do_niche(max_usd=0.45):
    git_sync()
    env = dict(os.environ, APIFY_TOKEN=open(APIFY_TOKEN_FILE).read().strip())
    cut = sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "data", "panel", "20*")))[-1]
    out = sh(sys.executable, "scripts/niche_snapshot.py", "run", "--cut-date", cut, "--max-usd", str(max_usd), env=env)
    meta = json.load(open(os.path.join(ROOT, "data", "niche", cut, "meta.json")))
    sha = commit_push(["data/niche"], f"niche snapshot {cut} (runs {meta['run_id']} {' '.join(meta.get('extra_run_ids', []))}, ${meta['usage_usd']})")
    log("niche", "ok" if sha else "unchanged", cut=cut, runs=",".join([meta["run_id"]] + meta.get("extra_run_ids", [])),
        usd=meta["usage_usd"], listings=meta["rows"]["listings"], keywords=meta["rows"]["keywords"], commit=sha or "-")
    posts()


def posts():
    if os.path.exists(POSTS):
        r = subprocess.run([sys.executable, POSTS], capture_output=True, text=True)
        log("posts", "ok" if r.returncode == 0 else f"error_rc{r.returncode}",
            out=(r.stdout.strip().splitlines() or ["-"])[-1][:160].replace(" ", "_"))


def locked(fn, *a):
    with open(LOCK, "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log(fn.__name__, "skipped_locked")
            return
        try:
            fn(*a)
        except Exception as e:
            log(fn.__name__.replace("do_", ""), "error", err=str(e)[-300:].replace("\n", " "))
            traceback.print_exc()


def next_times(t):
    def at(day, hm):
        return day.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
    p = at(t, PANEL_AT)
    if p <= t:
        p = at(t + dt.timedelta(days=1), PANEL_AT)
    n = at(t, NICHE_AT)
    while n <= t or n.weekday() != 0:
        n = at(n + dt.timedelta(days=1), NICHE_AT)
    return p, n


def loop():
    me = "/tmp/etsypulse-refresh-loop.pid"
    with open("/tmp/etsypulse-refresh-loop.lock", "w") as lf:
        try:
            fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("loop already running")
            return
        open(me, "w").write(str(os.getpid()))
        p, nn = next_times(now())
        log("loop", "started", pid=os.getpid(), next_panel=p.isoformat(timespec="minutes"),
            next_niche=nn.isoformat(timespec="minutes"))
        while True:
            t = now()
            if t >= p:
                locked(do_panel)
                p = next_times(now())[0]
                log("loop", "scheduled", next_panel=p.isoformat(timespec="minutes"))
            if t >= nn:
                locked(do_niche)
                nn = next_times(now())[1]
                log("loop", "scheduled", next_niche=nn.isoformat(timespec="minutes"))
            time.sleep(60)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "loop"
    if mode == "panel":
        locked(do_panel, "--force" in sys.argv)
    elif mode == "niche":
        locked(do_niche)
    elif mode == "loop":
        loop()
    else:
        raise SystemExit(__doc__)
