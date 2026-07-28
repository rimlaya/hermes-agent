"""Small control plane for user-managed autonomous work."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home


@dataclass(frozen=True)
class AutonomyState:
    paused: bool
    reason: str
    updated_at: str
    path: str


def _control_dir() -> Path:
    override = os.getenv("HERMES_AUTONOMY_CONTROL_DIR")
    if override:
        return Path(override).expanduser()
    return get_hermes_home() / "control"


def _state_path() -> Path:
    return _control_dir() / "autonomy_pause.json"


def _audit_path() -> Path:
    return _control_dir() / "autonomy_audit.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clip(value: Any, limit: int = 500) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def get_autonomy_state() -> AutonomyState:
    path = _state_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    paused = bool(data.get("paused"))
    return AutonomyState(
        paused=paused,
        reason=str(data.get("reason") or ""),
        updated_at=str(data.get("updated_at") or ""),
        path=str(path),
    )


def pause_autonomy(reason: str = "") -> AutonomyState:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "paused": True,
        "reason": _clip(reason, 240) or "paused by user",
        "updated_at": _now_iso(),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log_autonomy_event("pause", reason=data["reason"])
    return get_autonomy_state()


def resume_autonomy() -> AutonomyState:
    path = _state_path()
    previous = get_autonomy_state()
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    log_autonomy_event("resume", previous_reason=previous.reason)
    return get_autonomy_state()


def clear_autonomy() -> AutonomyState:
    return resume_autonomy()


def log_autonomy_event(event: str, **fields: Any) -> None:
    path = _audit_path()
    row = {
        "ts": _now_iso(),
        "event": _clip(event, 80),
        **{key: _clip(value) for key, value in fields.items() if value is not None},
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        return


def format_autonomy_state(state: AutonomyState | None = None) -> str:
    state = state or get_autonomy_state()
    if not state.paused:
        return "running"
    suffix = f" ({state.reason})" if state.reason else ""
    return f"paused{suffix}"
