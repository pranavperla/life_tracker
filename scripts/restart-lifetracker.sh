#!/usr/bin/env bash
# Restart Life Tracker (LaunchAgent if loaded, else manual start).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.pranav.lifetracker"
GUI_DOMAIN="gui/$(id -u)"

launchctl bootout "$GUI_DOMAIN/$LABEL" 2>/dev/null || true
pkill -f "$ROOT/main.py" 2>/dev/null || true
sleep 2
rm -f "$ROOT/data/.life_tracker.lock"

if [[ -f "$HOME/Library/LaunchAgents/${LABEL}.plist" ]]; then
  launchctl bootstrap "$GUI_DOMAIN" "$HOME/Library/LaunchAgents/${LABEL}.plist" 2>/dev/null || true
fi

if launchctl print "$GUI_DOMAIN/$LABEL" &>/dev/null; then
  echo "Restarting via launchd..."
  launchctl kickstart -k "$GUI_DOMAIN/$LABEL"
else
  echo "LaunchAgent not loaded. Starting manually (use install-launchagent.sh for auto-start)."
  cd "$ROOT"
  source .venv/bin/activate
  nohup python main.py >> launchd_stdout.log 2>> launchd_stderr.log &
  echo "PID $!"
fi
