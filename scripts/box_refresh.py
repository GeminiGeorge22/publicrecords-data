#!/usr/bin/env python3
"""Box-side data jobs for Etsy Pulse (no credentials in GitHub).

  python scripts/box_refresh.py internal        # daily: panel export to a box-only folder + X post images
  python scripts/box_refresh.py publish [--force]  # public site: panel cut + niche snapshot -> commit + push
  python scripts/box_refresh.py loop            # scheduler (times/cadence from config/publish.json)

Cadence lives in config/publish.json (cadence_days, publish_weekday, publish_time_et). The public site is
published on publish_weekday when at least cadence_days-3 days have passed since the last published cut,
so cadence 7 = weekly Mondays, cadence 14 = every other Monday. Daily internal exports are written to
/workspace/x-etsypulse/internal/panel/<date>/ and never pushed. Free reports refresh slowly on purpose;
live data is the paid Actor.

Tokens: HF_READ_TOKEN from the environment; Apify token read from APIFY_TOKEN_FILE.
Every attempt appends one status line to /workspace/x-etsypulse/data-refresh.log.
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
INTERNAL = os.environ.get("INTERNAL_PANEL", "/workspace/x-etsypulse/internal/panel")
APIFY_TOKEN_FILE = os.environ.get("APIFY_TOKEN_FILE", "/home/box/apify-marketer/secrets/apify-publicrecords-api-token.txt")
POSTS = "/workspace/x-etsypulse/make_posts.py"
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def cfg():
    return json.load(open(os.path.join(ROOT, "config", "publish.json")))


def hm(s):
    h, m = s.split(":")
    return int(h), int(m)


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
    if not sh("git", "diff", "--cached", "--name-only").stdout.strip():
        return None
    sh("git", "-c", "user.name=publicrecords", "-c", "user.email=publicrecords@users.noreply.github.com",
       "commit", "-q", "-m", msg)
    sh("git", "push", "-q", "origin", "main")
    return sh("git", "rev-parse", "--short", "HEAD").stdout.strip()


def last_published():
    ds = sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "data", "panel", "20*")))
    return dt.date.fromisoformat(ds[-1]) if ds else None


def hf_latest():
    tok = (os.environ.get("HF_READ_TOKEN") or os.environ.get("HF_TOKEN") or "").strip()
    req = urllib.request.Request(
        "https://huggingface.co/datasets/Publicrecords/etsy-shop-velocity/resolve/main/latest.json",
        headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def publish_due(today=None):
    c = cfg()
    today = today or now().date()
    lp = last_published()
    if DAYS[today.weekday()] != c["publish_weekday"]:
        return False, f"not_{c['publish_weekday']}"
    if lp and (today - lp).days < c["cadence_days"] - 3:
        return False, f"last_publish_{lp}"
    return True, "due"


def do_internal():
    latest = hf_latest()
    cut = now().date().isoformat()
    ds = sorted(glob.glob(os.path.join(INTERNAL, "20*", "meta.json")))
    if ds and json.load(open(ds[-1]))["snapshot_date"] == latest["snapshot_date"]:
        log("internal", "no_new_snapshot", hf_snapshot=latest["snapshot_date"])
    else:
        os.makedirs(INTERNAL, exist_ok=True)
        sh(sys.executable, "scripts/export_panel_cut.py", "--cut-date", cut, "--out-root", INTERNAL)
        meta = json.load(open(os.path.join(INTERNAL, cut, "meta.json")))
        log("internal", "ok", cut=cut, snapshot=meta["snapshot_date"], movers=meta["rows"]["movers"],
            shops=meta["shops_with_gain_ge_min"], path=os.path.join(INTERNAL, cut), pushed="no")
    posts()


def do_publish(force=False):
    git_sync()
    due, why = publish_due()
    if not (force or due):
        log("publish", "not_due", reason=why)
        return
    c = cfg()
    cut = now().date().isoformat()
    sh(sys.executable, "scripts/export_panel_cut.py", "--cut-date", cut)
    meta = json.load(open(os.path.join(ROOT, "data", "panel", cut, "meta.json")))
    paths, note = ["data/panel"], ""
    if c.get("niche_with_publish"):
        env = dict(os.environ, APIFY_TOKEN=open(APIFY_TOKEN_FILE).read().strip())
        try:
            sh(sys.executable, "scripts/niche_snapshot.py", "run", "--cut-date", cut,
               "--max-usd", str(c.get("niche_max_usd", 0.45)), env=env)
            nm = json.load(open(os.path.join(ROOT, "data", "niche", cut, "meta.json")))
            paths.append("data/niche")
            note = f"niche_runs={','.join([nm['run_id']] + nm.get('extra_run_ids', []))} niche_usd={nm['usage_usd']}"
        except Exception as e:
            note = f"niche_error={str(e)[-160:].replace(' ', '_')}"
    sha = commit_push(paths, f"weekly publish {cut} (snapshot {meta['snapshot_date']})")
    log("publish", "ok" if sha else "unchanged", cut=cut, snapshot=meta["snapshot_date"],
        movers=meta["rows"]["movers"], categories=meta["rows"]["categories"], rising=meta["rows"]["rising"],
        commit=sha or "-", **dict(kv.split("=", 1) for kv in note.split() if "=" in kv))


def posts():
    if os.path.exists(POSTS):
        r = subprocess.run([sys.executable, POSTS], capture_output=True, text=True)
        log("posts", "ok" if r.returncode == 0 else f"error_rc{r.returncode}",
            out=(r.stdout.strip().splitlines() or r.stderr.strip().splitlines() or ["-"])[-1][:160].replace(" ", "_"))


def locked(fn, *a):
    with open(LOCK, "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log(fn.__name__.replace("do_", ""), "skipped_locked")
            return
        try:
            fn(*a)
        except Exception as e:
            log(fn.__name__.replace("do_", ""), "error", err=str(e)[-300:].replace("\n", " "))
            traceback.print_exc()


def next_at(t, hhmm):
    h, m = hm(hhmm)
    x = t.replace(hour=h, minute=m, second=0, microsecond=0)
    return x if x > t else x + dt.timedelta(days=1)


def loop():
    with open("/tmp/etsypulse-refresh-loop.lock", "w") as lf:
        try:
            fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("loop already running")
            return
        open("/tmp/etsypulse-refresh-loop.pid", "w").write(str(os.getpid()))
        c = cfg()
        ni, np_ = next_at(now(), c["internal_daily_time_et"]), next_at(now(), c["publish_time_et"])
        log("loop", "started", pid=os.getpid(), next_internal=ni.isoformat(timespec="minutes"),
            publish_check=np_.isoformat(timespec="minutes"), cadence_days=c["cadence_days"], weekday=c["publish_weekday"])
        while True:
            t = now()
            if t >= np_:   # publish check first (it is a no-op unless due)
                locked(do_publish)
                np_ = next_at(now(), cfg()["publish_time_et"])
            if t >= ni:
                locked(do_internal)
                ni = next_at(now(), cfg()["internal_daily_time_et"])
            time.sleep(60)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "loop"
    if mode == "internal":
        locked(do_internal)
    elif mode == "publish":
        locked(do_publish, "--force" in sys.argv)
    elif mode == "loop":
        loop()
    else:
        raise SystemExit(__doc__)
