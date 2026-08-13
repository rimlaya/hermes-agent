#!/bin/bash
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
WATCHDOG="$ROOT/scripts/yomi-auth-expiry-watchdog.sh"
TMP=$(mktemp -d "${TMPDIR:-/tmp}/yomi-auth-watchdog-test.XXXXXX")
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/notify.sh" <<'SH'
#!/bin/bash
printf '%s\n' "$1" >> "$YOMI_AUTH_WATCHDOG_TEST_ALERTS"
SH
chmod +x "$TMP/notify.sh"

run_watchdog() {
  YOMI_AUTH_WATCHDOG_CAPTURE_FILE="$TMP/pane.txt" \
  YOMI_AUTH_WATCHDOG_NOTIFY_CMD="$TMP/notify.sh" \
  YOMI_AUTH_WATCHDOG_TEST_ALERTS="$TMP/alerts.log" \
  YOMI_AUTH_WATCHDOG_STATE_DIR="$TMP/state" \
  YOMI_AUTH_WATCHDOG_LOG_FILE="$TMP/watchdog.log" \
  YOMI_AUTH_WATCHDOG_COOLDOWN_SECONDS="${1:-900}" \
    /bin/bash "$WATCHDOG"
}

printf 'Ready for work\n' > "$TMP/pane.txt"
run_watchdog
[ ! -f "$TMP/alerts.log" ] || [ ! -s "$TMP/alerts.log" ]

printf 'Login expired · Please run\n/login\n' > "$TMP/pane.txt"
run_watchdog
[ "$(wc -l < "$TMP/alerts.log" | tr -d ' ')" = 1 ]
grep -q "Yomi authentication expired" "$TMP/alerts.log"
grep -q "no recovery action" "$TMP/alerts.log"

# Persistent marker inside the cooldown must not alert twice.
run_watchdog
[ "$(wc -l < "$TMP/alerts.log" | tr -d ' ')" = 1 ]

# A zero cooldown simulates the periodic reminder after a prolonged outage.
run_watchdog 0
[ "$(wc -l < "$TMP/alerts.log" | tr -d ' ')" = 2 ]

printf 'PASS: marker detection, wrapped text, notification, and cooldown dedupe\n'
