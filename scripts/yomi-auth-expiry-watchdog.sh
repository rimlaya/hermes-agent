#!/bin/bash
# Read-only Yomi pane monitor. It alerts on auth-expiry text but never sends
# keystrokes, restarts a process, or attempts /login.
set -u

PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
STATE_DIR="${YOMI_AUTH_WATCHDOG_STATE_DIR:-$HOME/.yomi/state/yomi-auth-expiry-watchdog}"
LOG_FILE="${YOMI_AUTH_WATCHDOG_LOG_FILE:-$HOME/.yomi/logs/yomi-auth-expiry-watchdog.log}"
MUX_LIB="${YOMI_AUTH_WATCHDOG_MUX_LIB:-$HOME/.yomi/lib/mux-lib.sh}"
DISCORD_ENV="${YOMI_AUTH_WATCHDOG_DISCORD_ENV:-$HOME/.yomi/claude-channels/discord/.env}"
DISCORD_ENV_FALLBACK="${YOMI_AUTH_WATCHDOG_DISCORD_ENV_FALLBACK:-$HOME/.claude/channels/discord/.env}"
DISCORD_CHANNEL="${YOMI_AUTH_WATCHDOG_DISCORD_CHANNEL:-1495054874638024846}"
COOLDOWN_SECONDS="${YOMI_AUTH_WATCHDOG_COOLDOWN_SECONDS:-900}"
LOCK_DIR="$STATE_DIR/.lock"
ALERT_STATE="$STATE_DIR/last-alert.tsv"

mkdir -p "$STATE_DIR" "$(dirname "$LOG_FILE")"

log() {
  printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >> "$LOG_FILE"
}

# launchd should serialize StartInterval jobs, but this also protects manual
# smoke tests and future schedulers from producing duplicate alerts.
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  lock_pid=$(cat "$LOCK_DIR/pid" 2>/dev/null || true)
  if [ -n "$lock_pid" ] && kill -0 "$lock_pid" 2>/dev/null; then
    log "skip reason=already-running pid=$lock_pid"
    exit 0
  fi
  rm -rf "$LOCK_DIR"
  mkdir "$LOCK_DIR" 2>/dev/null || exit 0
fi
printf '%s\n' "$$" > "$LOCK_DIR/pid"
trap 'rm -rf "$LOCK_DIR"' EXIT HUP INT TERM

capture_pane() {
  if [ -n "${YOMI_AUTH_WATCHDOG_CAPTURE_FILE:-}" ]; then
    cat "$YOMI_AUTH_WATCHDOG_CAPTURE_FILE"
    return
  fi
  [ -r "$MUX_LIB" ] || return 1
  # shellcheck source=/dev/null
  . "$MUX_LIB"
  mux_capture_joined 240
}

read_env_value() {
  env_file="$1"
  key="$2"
  [ -f "$env_file" ] || return 1
  grep -E "^${key}=" "$env_file" | head -1 | cut -d= -f2- | sed "s/^['\"]//; s/['\"]$//"
}

notify_discord() {
  message="$1"
  if [ -n "${YOMI_AUTH_WATCHDOG_NOTIFY_CMD:-}" ]; then
    "$YOMI_AUTH_WATCHDOG_NOTIFY_CMD" "$message"
    return
  fi

  env_file="$DISCORD_ENV"
  [ -f "$env_file" ] || env_file="$DISCORD_ENV_FALLBACK"
  token=$(read_env_value "$env_file" DISCORD_BOT_TOKEN || true)
  [ -n "${token:-}" ] || return 1
  payload=$(/usr/bin/python3 -c 'import json,sys; print(json.dumps({"content":sys.argv[1]}))' "$message") || return 1
  status=$(curl -sS --max-time 15 -o /dev/null -w '%{http_code}' \
    -X POST "https://discord.com/api/v10/channels/${DISCORD_CHANNEL}/messages" \
    -H "Authorization: Bot ${token}" \
    -H 'Content-Type: application/json' \
    --data "$payload" 2>/dev/null || printf '000')
  printf '%s' "$status" | grep -qE '^2[0-9][0-9]$'
}

pane_text=$(capture_pane 2>/dev/null) || {
  log "probe_failed reason=pane-capture"
  exit 0
}
# Herdr visible output wraps narrow terminal text. Join whitespace so both
# "Login expired" and a line-wrapped "Please run /login" remain detectable.
normalized=$(printf '%s' "$pane_text" | tr '\r\n\t' '   ' | tr -s ' ')
marker=$(printf '%s' "$normalized" | grep -Eio 'Login[[:space:]]+expired|Please[[:space:]]+run[[:space:]]+/login|Not[[:space:]]+logged[[:space:]]+in' | head -1 || true)
[ -n "$marker" ] || {
  log "probe_ok auth_marker=absent"
  exit 0
}

now=$(date +%s)
last_epoch=0
last_marker=""
if [ -f "$ALERT_STATE" ]; then
  IFS=$'\t' read -r last_epoch last_marker < "$ALERT_STATE" || true
fi
case "$last_epoch" in ''|*[!0-9]*) last_epoch=0 ;; esac
age=$((now - last_epoch))
if [ "$last_marker" = "$marker" ] && [ "$age" -lt "$COOLDOWN_SECONDS" ]; then
  log "probe_ok auth_marker=present alert=suppressed cooldown_age=${age}"
  exit 0
fi

alert="🚨 Yomi authentication expired: pane marker '${marker}' detected. Yomi may be unable to respond. Manual diagnosis and /login approval required; watchdog performed no recovery action."
if notify_discord "$alert"; then
  printf '%s\t%s\n' "$now" "$marker" > "$ALERT_STATE.tmp.$$"
  mv "$ALERT_STATE.tmp.$$" "$ALERT_STATE"
  log "probe_ok auth_marker=present alert=sent channel=$DISCORD_CHANNEL"
else
  log "probe_ok auth_marker=present alert=failed channel=$DISCORD_CHANNEL"
  exit 1
fi
