#!/usr/bin/env bash
# Start the Etsy Pulse refresh loop if it is not already running (idempotent; safe to call from any agent, any shell,
# after a box restart). The loop inherits HF_READ_TOKEN from this shell's environment.
#   --restart   stop a running loop first (use after changing scripts/box_refresh.py)
set -euo pipefail
cd "$(dirname "$0")/.."
PIDF=/tmp/etsypulse-refresh-loop.pid
if [ "${1:-}" = "--restart" ] && [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
  kill "$(cat "$PIDF")"; sleep 2
fi
if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
  echo "running pid $(cat "$PIDF")"; exit 0
fi
if [ -z "${HF_READ_TOKEN:-}${HF_TOKEN:-}" ]; then
  echo "HF_READ_TOKEN missing in this shell: loop not started" >&2; exit 1
fi
setsid nohup python3 scripts/box_refresh.py loop >> /tmp/etsypulse-refresh-loop.out 2>&1 < /dev/null &
sleep 2; echo "started pid $(cat "$PIDF")"
