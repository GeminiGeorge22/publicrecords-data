#!/usr/bin/env python3
"""LOOP-HB-1 (Claude t793u item 2): page when the Etsy Pulse refresh loop (scripts/box_refresh.py loop) goes silent.

  python scripts/loop_heartbeat_check.py [--heartbeat FILE] [--alerts DIR] [--max-silent-min 30]

The loop rewrites its heartbeat file every 30 s (also outside the 06:00-23:00 poll window). RED when the file is missing,
older than --max-silent-min, or names a pid that is not running: writes <alerts>/site-loop-heartbeat.RED (timestamp + reason),
prints 'RED ...' and exits 1. GREEN: removes the .RED file, writes site-loop-heartbeat.GREEN, prints 'GREEN ...', exits 0.
Every state change also appends one line to the refresh log. Read-only towards the loop: it never starts or stops it."""
import argparse, datetime as dt, json, os, sys
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/Toronto")
HEARTBEAT = os.environ.get("REFRESH_HEARTBEAT", "/workspace/x-etsypulse/loop-heartbeat.json")
ALERTS = os.environ.get("MARKETER_ALERTS", "/home/box/apify-marketer/alerts")
LOG = os.environ.get("REFRESH_LOG", "/workspace/x-etsypulse/data-refresh.log")
NAME = "site-loop-heartbeat"


def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def check(hb_path=HEARTBEAT, alerts=ALERTS, max_silent_min=30, log_path=None):
    now = dt.datetime.now(ET)
    stamp = now.strftime("%Y-%m-%d %H:%M:%S %Z")
    try:
        d = json.load(open(hb_path))
        at = dt.datetime.fromisoformat(d["at"])
        age = (now - at).total_seconds() / 60
        if age > max_silent_min:
            why = f"heartbeat silent {age:.0f} min (> {max_silent_min}); last {d['at']} pid {d.get('pid')}"
        elif not alive(d.get("pid")):
            why = f"loop pid {d.get('pid')} not running (last heartbeat {d['at']}, {age:.0f} min ago)"
        else:
            why = None
    except (FileNotFoundError, ValueError, KeyError) as e:
        why, d, age = f"heartbeat missing or unreadable at {hb_path} ({type(e).__name__})", {}, None
    os.makedirs(alerts, exist_ok=True)
    red, green = os.path.join(alerts, NAME + ".RED"), os.path.join(alerts, NAME + ".GREEN")
    was_red = os.path.exists(red)
    if why:
        line = f"RED {NAME} at={stamp} {why}"
        open(red, "w").write(line + "\n")
        if os.path.exists(green):
            os.remove(green)
        rc = 1
    else:
        line = f"GREEN {NAME} at={stamp} last_heartbeat={d['at']} age_min={age:.1f} pid={d.get('pid')} next_poll={d.get('next_poll')}"
        if was_red:
            os.remove(red)
        open(green, "w").write(line + "\n")
        rc = 0
    if log_path and (bool(why) != was_red):   # state change only: no 96 identical lines a day
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(f"{stamp} job=heartbeat status={'RED' if why else 'green'} out={line.replace(' ', '_')[:240]}\n")
    return rc, line


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--heartbeat", default=HEARTBEAT)
    ap.add_argument("--alerts", default=ALERTS)
    ap.add_argument("--max-silent-min", type=float, default=30)
    ap.add_argument("--log", default=LOG, help="refresh log for state-change lines ('' = none)")
    a = ap.parse_args()
    rc, line = check(a.heartbeat, a.alerts, a.max_silent_min, a.log or None)
    print(line)
    sys.exit(rc)
