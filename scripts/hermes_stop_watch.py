#!/usr/bin/env python3
"""Detect a stopped Hermes gateway and notify an operator command.

This script is intentionally passive: it reads Hermes runtime state, optionally
sends one notification, and never starts/stops/restarts the gateway.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gateway.status import is_gateway_running, read_runtime_status  # noqa: E402
from hermes_constants import get_hermes_home  # noqa: E402

DEFAULT_NOTIFY_COMMAND = (
    "/Users/miyaihisataka/.openclaw/workspace/scripts/notify-yomi.sh"
)


@dataclass(frozen=True)
class HealthCheck:
    ok: bool
    title: str
    body: str
    key: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_file() -> Path:
    return get_hermes_home() / "monitor" / "hermes_stop_watch.json"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)


def _exit_reason(status: dict[str, Any] | None) -> str:
    if not status:
        return "no runtime status file"
    reason = status.get("exit_reason")
    if isinstance(reason, str) and reason.strip():
        return reason.strip()
    state = status.get("gateway_state")
    if isinstance(state, str) and state.strip():
        return f"gateway_state={state.strip()}"
    return "unknown exit reason"


def check_gateway_health() -> HealthCheck:
    status = read_runtime_status()
    if is_gateway_running(cleanup_stale=False):
        state = status.get("gateway_state") if isinstance(status, dict) else None
        return HealthCheck(
            ok=True,
            title="Hermes gateway healthy",
            body=f"Gateway process is running. Runtime state: {state or 'unknown'}.",
            key="healthy",
        )

    reason = _exit_reason(status)
    updated_at = status.get("updated_at") if isinstance(status, dict) else None
    details = [
        "Hermes gateway is not running.",
        f"Reason: {reason}.",
    ]
    if updated_at:
        details.append(f"Last runtime update: {updated_at}.")
    details.append("No restart was attempted by hermes_stop_watch.py.")
    return HealthCheck(
        ok=False,
        title="Hermes gateway stopped",
        body="\n".join(details),
        key=f"stopped:{reason}:{updated_at or 'no-update'}",
    )


def should_notify(check: HealthCheck, state: dict[str, Any], *, notify_recovery: bool) -> bool:
    previous_key = state.get("last_problem_key")

    if check.ok:
        return bool(notify_recovery and previous_key)

    return previous_key != check.key


def update_state(check: HealthCheck, state_path: Path, *, notified: bool) -> None:
    payload = _load_json(state_path)
    payload["updated_at"] = _utc_now()
    payload["last_ok"] = check.ok

    if check.ok:
        payload.pop("last_problem_key", None)
        if notified:
            payload["last_recovery_notified_at"] = _utc_now()
    else:
        payload["last_problem_key"] = check.key
        payload["last_problem_title"] = check.title
        if notified:
            payload["last_problem_notified_at"] = _utc_now()

    _write_json(state_path, payload)


def send_notification(command: str, title: str, body: str) -> None:
    subprocess.run([command, title, body], check=True, timeout=20)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Notify once when the Hermes gateway is stopped."
    )
    parser.add_argument(
        "--notify-command",
        default=DEFAULT_NOTIFY_COMMAND,
        help="Executable notification command. It receives: title body.",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=_state_file(),
        help="JSON file used to suppress duplicate notifications.",
    )
    parser.add_argument(
        "--recovery",
        action="store_true",
        help="Notify once when the gateway recovers after a recorded stop.",
    )
    parser.add_argument(
        "--status-only",
        action="store_true",
        help="Print status and exit without sending notifications.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    check = check_gateway_health()
    state = _load_json(args.state_file)
    notify = should_notify(check, state, notify_recovery=args.recovery)

    print(check.title)
    print(check.body)

    notified = False
    if notify and not args.status_only:
        title = check.title if not check.ok else "Hermes gateway recovered"
        body = check.body if not check.ok else "Hermes gateway process is running again."
        send_notification(args.notify_command, title, body)
        notified = True

    if not args.status_only:
        update_state(check, args.state_file, notified=notified)

    return 0 if check.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
