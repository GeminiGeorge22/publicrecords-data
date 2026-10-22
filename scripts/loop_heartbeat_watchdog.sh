#!/usr/bin/env bash
# LOOP-HB-1 (Claude t793u item 2): box-side pager for the refresh loop. Every 5 min runs scripts/loop_heartbeat_check.py
# (RED file /home/box/apify-marketer/alerts/site-loop-heartbeat.RED + exit 1 when the loop is silent > 30 min). One copy only
# (flock). It never starts/stops the loop. A box restart kills this too, so the marketer's 15-min poll routine also runs the
# check directly: `python3 scripts/loop_heartbeat_check.py` (exit 1 = page).
cd "$(dirname "$0")/.."
exec 9>/tmp/etsypulse-loop-heartbeat-watchdog.lock; flock -n 9 || { echo "watchdog already running"; exit 0; }
while true; do python3 scripts/loop_heartbeat_check.py >> /tmp/etsypulse-loop-heartbeat-watchdog.out 2>&1; sleep 300; done
