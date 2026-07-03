#!/usr/bin/env bash
# Install or refresh the Life Tracker LaunchAgent (survives reboot; starts after login / FileVault unlock).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.pranav.lifetracker"
PLIST_SRC="$ROOT/com.pranav.lifetracker.plist"
PLIST_DST="$HOME/Library/LaunchAgents/${LABEL}.plist"
GUI_DOMAIN="gui/$(id -u)"

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Missing venv. Run: cd $ROOT && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$PLIST_DST"
echo "Installed $PLIST_DST"

launchctl bootout "$GUI_DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$GUI_DOMAIN" "$PLIST_DST"
launchctl enable "$GUI_DOMAIN/$LABEL" 2>/dev/null || true
launchctl kickstart -k "$GUI_DOMAIN/$LABEL" 2>/dev/null || launchctl start "$LABEL" 2>/dev/null || true

echo "Life Tracker should be running. Check:"
echo "  launchctl print $GUI_DOMAIN/$LABEL"
echo "  tail -f $ROOT/launchd_stdout.log"
