#!/bin/bash
set -eu

LABEL="com.mia.yomi-auth-expiry-watchdog"
DOMAIN="gui/$(id -u)"
ROOT=$(cd "$(dirname "$0")/.." && pwd)
SOURCE_SCRIPT="$ROOT/scripts/yomi-auth-expiry-watchdog.sh"
SOURCE_PLIST="$ROOT/ops/launchd/$LABEL.plist"
TARGET_SCRIPT="$HOME/.yomi/scripts/yomi-auth-expiry-watchdog.sh"
TARGET_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
STAMP=$(date -u '+%Y%m%dT%H%M%SZ')
BACKUP_DIR="$HOME/.yomi/backups/yomi-auth-expiry-watchdog-$STAMP"
WAS_LOADED=0
HAD_SCRIPT=0
HAD_PLIST=0

mkdir -p "$HOME/.yomi/scripts" "$HOME/.yomi/logs" "$HOME/.yomi/state" "$HOME/Library/LaunchAgents" "$BACKUP_DIR"
plutil -lint "$SOURCE_PLIST" >/dev/null
/bin/bash -n "$SOURCE_SCRIPT"

if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
  WAS_LOADED=1
fi
if [ -e "$TARGET_SCRIPT" ]; then HAD_SCRIPT=1; cp -p "$TARGET_SCRIPT" "$BACKUP_DIR/"; fi
if [ -e "$TARGET_PLIST" ]; then HAD_PLIST=1; cp -p "$TARGET_PLIST" "$BACKUP_DIR/"; fi

rollback() {
  launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
  if [ -f "$BACKUP_DIR/$(basename "$TARGET_SCRIPT")" ]; then
    cp -p "$BACKUP_DIR/$(basename "$TARGET_SCRIPT")" "$TARGET_SCRIPT"
  elif [ "$HAD_SCRIPT" = 0 ]; then
    rm -f "$TARGET_SCRIPT"
  fi
  if [ -f "$BACKUP_DIR/$(basename "$TARGET_PLIST")" ]; then
    cp -p "$BACKUP_DIR/$(basename "$TARGET_PLIST")" "$TARGET_PLIST"
    if [ "$WAS_LOADED" = 1 ]; then launchctl bootstrap "$DOMAIN" "$TARGET_PLIST" >/dev/null 2>&1 || true; fi
  elif [ "$HAD_PLIST" = 0 ]; then
    rm -f "$TARGET_PLIST"
  fi
}
trap rollback HUP INT TERM

# A loaded instance is stopped before replacement, so two pollers with the
# same label can never overlap or race on the Discord credential.
if [ "$WAS_LOADED" = 1 ]; then launchctl bootout "$DOMAIN/$LABEL"; fi
install -m 0755 "$SOURCE_SCRIPT" "$TARGET_SCRIPT"
install -m 0644 "$SOURCE_PLIST" "$TARGET_PLIST"
if ! launchctl bootstrap "$DOMAIN" "$TARGET_PLIST"; then
  rollback
  printf 'install failed; previous files restored from %s\n' "$BACKUP_DIR" >&2
  exit 1
fi
trap - HUP INT TERM

launchctl print "$DOMAIN/$LABEL" >/dev/null
printf 'installed label=%s script=%s plist=%s backup=%s\n' "$LABEL" "$TARGET_SCRIPT" "$TARGET_PLIST" "$BACKUP_DIR"
