#!/usr/bin/env python3
"""Box-side data jobs for Etsy Pulse (no credentials in GitHub).

  python scripts/box_refresh.py poll               # one poll now: internal export + public publish if a newer complete snapshot exists
  python scripts/box_refresh.py publish [--force]  # public site from the newest snapshot (--force: publish even if not newer)
  python scripts/box_refresh.py niche [--force]    # weekly niche price snapshot (paid Apify run) on the latest published cut
  python scripts/box_refresh.py internal           # box-only panel export + X post images (no push)
  python scripts/box_refresh.py loop               # scheduler (config/publish.json)

DAILY-1 (Mark 2026-10-08 11:29 ET): the public site publishes every day, as soon as a newer Velocity snapshot exists than
the one live on the site. The loop polls Hugging Face latest.json every poll_minutes inside poll_window_et (ET), so a late
snapshot still publishes the same day. A snapshot is published only when complete (see completeness()); an incomplete one
is logged once and skipped. Before any push the site is built locally and build_site.py's check_public must pass; the push
happens with a pull --rebase, all under /tmp/etsypulse-refresh.lock. Daily internal exports are written to
/workspace/x-etsypulse/internal/panel/<date>/ and never pushed. The niche snapshot (paid) stays weekly.

Tokens: HF_READ_TOKEN from the environment; Apify token read from APIFY_TOKEN_FILE.
Every attempt appends one status line to /workspace/x-etsypulse/data-refresh.log (repeats of the same state are not re-logged).
"""
from __future__ import annotations

import datetime as dt
import fcntl
import glob
import json
import os
import shutil
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
STATE = os.environ.get("REFRESH_STATE", "/workspace/x-etsypulse/refresh-state.json")
INTERNAL = os.environ.get("INTERNAL_PANEL", "/workspace/x-etsypulse/internal/panel")
APIFY_TOKEN_FILE = os.environ.get("APIFY_TOKEN_FILE", "/home/box/apify-marketer/secrets/apify-publicrecords-api-token.txt")
CHECK_OUT = "/tmp/etsypulse-site-check"
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


def state():
    try:
        return json.load(open(STATE))
    except (FileNotFoundError, ValueError):
        return {}


def save_state(**kw):
    s = state()
    s.update(kw)
    tmp = STATE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(s, fh, indent=1)
    os.replace(tmp, STATE)


def log_once(key, job, status, **kw):
    """Log a line only when (status, kw) differs from the last line logged under key (no 34 identical lines a day)."""
    sig = json.dumps([status, kw], sort_keys=True)
    if state().get("last_" + key) != sig:
        log(job, status, **kw)
        save_state(**{"last_" + key: sig})


def sh(*cmd, env=None, check=True):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])}... rc={r.returncode}: {(r.stderr or r.stdout)[-400:]}")
    return r


def git_sync():
    sh("git", "fetch", "-q", "origin", "main")
    sh("git", "checkout", "-q", "main")
    sh("git", "pull", "-q", "--rebase", "--autostash", "origin", "main")


def commit_push(paths, msg):
    sh("git", "add", "-A", *paths)
    if not sh("git", "diff", "--cached", "--name-only").stdout.strip():
        return None
    sh("git", "-c", "user.name=publicrecords", "-c", "user.email=publicrecords@users.noreply.github.com",
       "commit", "-q", "-m", msg)
    for i in range(3):
        sh("git", "pull", "-q", "--rebase", "--autostash", "origin", "main")
        if sh("git", "push", "-q", "origin", "main", check=(i == 2)).returncode == 0:
            break
        time.sleep(5)
    return sh("git", "rev-parse", "--short", "HEAD").stdout.strip()


def panel_cuts():
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "data", "panel", "20*")) if os.path.isdir(p))


def published_meta():
    pc = panel_cuts()
    return json.load(open(os.path.join(ROOT, "data", "panel", pc[-1], "meta.json"))) if pc else None


def hf_latest():
    tok = (os.environ.get("HF_READ_TOKEN") or os.environ.get("HF_TOKEN") or "").strip()
    req = urllib.request.Request(
        "https://huggingface.co/datasets/Publicrecords/etsy-shop-velocity/resolve/main/latest.json",
        headers={"Authorization": f"Bearer {tok}", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def completeness(m, prev):
    """None if snapshot manifest m is complete enough to publish over prev (the live cut's meta), else the reason.
    m may be latest.json (pre-check) or an exported meta.json (final check; the export itself verifies sha256 + row count)."""
    c = cfg()
    exported = "snapshot_rows" in m   # exported meta.json ("rows" there is the per-report row count) vs latest.json
    rows = m.get("snapshot_rows") if exported else m.get("rows")
    panel = m.get("panel_shops") if exported else m.get("panel")
    if not rows:
        return "no_row_count"
    if m.get("snapshot_rows_in_file") is not None and m["snapshot_rows_in_file"] != rows:
        return f"file_rows_{m['snapshot_rows_in_file']}_vs_manifest_{rows}"
    gates = m.get("gates") or {}
    if any(v is False for v in gates.values()):
        return "gates_" + ",".join(k for k, v in gates.items() if v is False) + "_false"
    if prev:
        pr, pp = prev.get("snapshot_rows"), prev.get("panel_shops")
        if pr and rows < c.get("min_rows_ratio", 0.95) * pr:
            return f"rows_{rows}_below_{c.get('min_rows_ratio', 0.95)}x_prev_{pr}"
        if pp and panel and panel < c.get("min_panel_ratio", 0.95) * pp:
            return f"panel_{panel}_below_{c.get('min_panel_ratio', 0.95)}x_prev_{pp}"
    mv = (m.get("rows_full") or {}).get("movers") if isinstance(m.get("rows_full"), dict) else None
    if mv is not None and mv < c.get("min_movers_rows", 10):
        return f"only_{mv}_movers"
    return None


def do_internal(latest=None):
    latest = latest or hf_latest()
    cut = now().date().isoformat()
    ds = sorted(glob.glob(os.path.join(INTERNAL, "20*", "meta.json")))
    if ds and json.load(open(ds[-1]))["snapshot_date"] >= latest["snapshot_date"]:
        return False
    os.makedirs(INTERNAL, exist_ok=True)
    sh(sys.executable, "scripts/export_panel_cut.py", "--cut-date", cut, "--out-root", INTERNAL)
    meta = json.load(open(os.path.join(INTERNAL, cut, "meta.json")))
    log("internal", "ok", cut=cut, snapshot=meta["snapshot_date"], movers=meta["rows"]["movers"],
        shops=meta["shops_with_gain_ge_min"], path=os.path.join(INTERNAL, cut), pushed="no")
    posts()
    return True


def build_check():
    """Build the whole site locally; build_site.py's check_public (banned copy, price lines, client names, row caps,
    domain) must pass before anything is pushed."""
    r = sh(sys.executable, "scripts/build_site.py", "--out", CHECK_OUT, check=False)
    if r.returncode != 0:
        return (r.stderr or r.stdout).strip()[-300:].replace("\n", " | ")
    return None


def do_publish(force=False, latest=None):
    git_sync()
    latest = latest or hf_latest()
    prev = published_meta()
    have = prev["snapshot_date"] if prev else None
    if not force and have and latest["snapshot_date"] <= have:
        log_once("publish", "publish", "no_new_snapshot", hf_snapshot=latest["snapshot_date"], live=have)
        return False
    why = completeness(latest, prev)
    if why and not force:
        log_once("publish", "publish", "skipped_incomplete", hf_snapshot=latest["snapshot_date"], reason=why)
        return False
    cut = now().date().isoformat()
    cut_dir = os.path.join(ROOT, "data", "panel", cut)
    existed = os.path.isdir(cut_dir)
    backup = None
    if existed:   # a newer snapshot landed later the same day: replace today's cut, keep a copy to restore on failure
        backup = f"/tmp/etsypulse-cut-{cut}-bak"
        shutil.rmtree(backup, ignore_errors=True)
        shutil.copytree(cut_dir, backup)
    try:
        sh(sys.executable, "scripts/export_panel_cut.py", "--cut-date", cut)
        meta = json.load(open(os.path.join(cut_dir, "meta.json")))
        why = completeness(meta, prev)   # prev = the cut live before this export (read before it ran)
        if why and not force:
            raise ValueError("incomplete_after_export:" + why)
        if not force and have and meta["snapshot_date"] <= have:
            raise ValueError("export_not_newer")
        err = build_check()
        if err:
            raise ValueError("site_check_failed:" + err)
    except Exception as e:
        shutil.rmtree(cut_dir, ignore_errors=True)
        if backup:
            shutil.copytree(backup, cut_dir)
        sh("git", "checkout", "-q", "--", "data/panel", check=False)
        log_once("publish", "publish", "skipped" if isinstance(e, ValueError) else "error",
                 hf_snapshot=latest["snapshot_date"], reason=str(e)[-300:].replace(" ", "_").replace("\n", "_"))
        return False
    sha = commit_push(["data/panel"], f"daily publish {cut} (snapshot {meta['snapshot_date']}, {meta['snapshot_rows']} rows)")
    log("publish", "ok" if sha else "unchanged", cut=cut, snapshot=meta["snapshot_date"], rows=meta["snapshot_rows"],
        prev_rows=(prev or {}).get("snapshot_rows"), movers=meta["rows"]["movers"], categories=meta["rows"]["categories"],
        rising=meta["rows"]["rising"], commit=sha or "-")
    save_state(published=sig_of(meta))
    return True


def sig_of(meta):
    return {"cut": meta["cut_date"], "snapshot": meta["snapshot_date"], "at": now().isoformat(timespec="seconds")}


def niche_due(t=None):
    c = cfg()
    t = t or now()
    if DAYS[t.weekday()] != c.get("niche_weekday", "Mon"):
        return False, "not_" + c.get("niche_weekday", "Mon")
    if t < t.replace(hour=hm(c.get("niche_time_et", "07:45"))[0], minute=hm(c.get("niche_time_et", "07:45"))[1], second=0):
        return False, "before_" + c.get("niche_time_et", "07:45")
    if state().get("niche_attempt") == t.date().isoformat():
        return False, "attempted_today"
    nc = sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "data", "niche", "20*")))
    if nc and (t.date() - dt.date.fromisoformat(nc[-1])).days < c.get("niche_cadence_days", 7) - 3:
        return False, f"last_niche_{nc[-1]}"
    return True, "due"


def do_niche(force=False):
    git_sync()
    due, why = niche_due()
    if not (force or due):
        return False
    save_state(niche_attempt=now().date().isoformat())
    c = cfg()
    cut = panel_cuts()[-1]
    env = dict(os.environ, APIFY_TOKEN=open(APIFY_TOKEN_FILE).read().strip())
    try:
        sh(sys.executable, "scripts/niche_snapshot.py", "run", "--cut-date", cut,
           "--max-usd", str(c.get("niche_max_usd", 0.40)), env=env)
        nm = json.load(open(os.path.join(ROOT, "data", "niche", cut, "meta.json")))
        err = build_check()
        if err:
            raise ValueError("site_check_failed:" + err)
    except Exception as e:
        shutil.rmtree(os.path.join(ROOT, "data", "niche", cut), ignore_errors=True)
        sh("git", "checkout", "-q", "--", "data/niche", check=False)
        log("niche", "error", cut=cut, err=str(e)[-200:].replace(" ", "_").replace("\n", "_"))
        return False
    sha = commit_push(["data/niche"], f"weekly niche snapshot {cut} (runs {','.join([nm['run_id']] + nm.get('extra_run_ids', []))})")
    log("niche", "ok" if sha else "unchanged", cut=cut, runs=",".join([nm["run_id"]] + nm.get("extra_run_ids", [])),
        usd=nm.get("usage_usd"), commit=sha or "-")
    return True


def do_poll():
    """One poll: fetch latest.json once, then box-only internal export, public publish, weekly niche."""
    latest = hf_latest()
    try:
        do_internal(latest)
    except Exception as e:
        log("internal", "error", err=str(e)[-300:].replace("\n", " "))
    do_publish(latest=latest)
    do_niche()


def posts():
    if os.path.exists(POSTS):
        r = subprocess.run([sys.executable, POSTS], capture_output=True, text=True)
        log("posts", "ok" if r.returncode == 0 else f"error_rc{r.returncode}",
            out=(r.stdout.strip().splitlines() or r.stderr.strip().splitlines() or ["-"])[-1][:160].replace(" ", "_"))


def locked(fn, *a, **kw):
    with open(LOCK, "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log(fn.__name__.replace("do_", ""), "skipped_locked")
            return
        try:
            fn(*a, **kw)
        except Exception as e:
            log(fn.__name__.replace("do_", ""), "error", err=str(e)[-300:].replace("\n", " "))
            traceback.print_exc()


def in_window(t, c):
    lo, hi = (hm(x) for x in c.get("poll_window_et", ["06:00", "23:00"]))
    return (t.hour, t.minute) >= lo and (t.hour, t.minute) <= hi


def next_poll(t, c):
    """Next :00/:30 (poll_minutes grid) inside the ET poll window."""
    step = int(c.get("poll_minutes", 30))
    x = t.replace(second=0, microsecond=0) + dt.timedelta(minutes=step - t.minute % step)
    while not in_window(x, c):
        x += dt.timedelta(minutes=step)
    return x


def loop():
    with open("/tmp/etsypulse-refresh-loop.lock", "w") as lf:
        try:
            fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("loop already running")
            return
        open("/tmp/etsypulse-refresh-loop.pid", "w").write(str(os.getpid()))
        c = cfg()
        t = now()
        nxt = t if in_window(t, c) else next_poll(t, c)
        log("loop", "started", pid=os.getpid(), mode=c.get("publish"), poll_minutes=c.get("poll_minutes"),
            window="-".join(c.get("poll_window_et", [])), next_poll=nxt.isoformat(timespec="minutes"),
            niche=f"{c.get('niche_weekday')}@{c.get('niche_time_et')}")
        while True:
            if now() >= nxt:
                locked(do_poll)
                c = cfg()
                nxt = next_poll(now(), c)
            time.sleep(30)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "loop"
    force = "--force" in sys.argv
    if mode == "internal":
        locked(do_internal)
    elif mode == "publish":
        locked(do_publish, force)
    elif mode == "niche":
        locked(do_niche, force)
    elif mode == "poll":
        locked(do_poll)
    elif mode == "loop":
        loop()
    else:
        raise SystemExit(__doc__)
