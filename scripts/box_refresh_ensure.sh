#!/usr/bin/env bash
# Start the Etsy Pulse refresh loop if it is not already running (idempotent; safe to call from any agent).
# The loop inherits HF_READ_TOKEN from this shell's environment.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -f /tmp/etsypulse-refresh-loop.pid ] && kill -0 "$(cat /tmp/etsypulse-refresh-loop.pid)" 2>/dev/null; then
  echo "running pid $(cat /tmp/etsypulse-refresh-loop.pid)"; exit 0
fi
setsid nohup python3 scripts/box_refresh.py loop >> /tmp/etsypulse-refresh-loop.out 2>&1 < /dev/null &
sleep 2; echo "started pid $(cat /tmp/etsypulse-refresh-loop.pid)"
