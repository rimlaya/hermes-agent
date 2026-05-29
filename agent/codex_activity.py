"""Summarize recent Codex CLI sessions without exposing transcript content."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class CodexActivity:
    path: str
    mtime: float
    started_at: str
    cwd: str
    model: str
    tool_calls: int
    last_command: str


def _codex_sessions_root() -> Path:
    override = os.getenv("HERMES_CODEX_ACTIVITY_ROOT")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".codex" / "sessions"


def _iter_recent_rollouts(root: Path, *, max_files: int) -> Iterable[Path]:
    if not root.exists():
        return []
    try:
        files = [
            path
            for path in root.rglob("rollout-*.jsonl")
            if path.is_file()
        ]
    except OSError:
        return []
    files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return files[:max_files]


def _clip(value: str, limit: int) -> str:
    value = " ".join(str(value or "").split())
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."


_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|PASS|AUTH)[A-Z0-9_]*=)([^\s]+)"
)
_BEARER_RE = re.compile(r"(?i)\b(Bearer\s+)([A-Za-z0-9._~+/=-]+)")


def _redact_command(command: str) -> str:
    command = _SECRET_ASSIGNMENT_RE.sub(r"\1[redacted]", command)
    return _BEARER_RE.sub(r"\1[redacted]", command)


def _read_activity(path: Path) -> CodexActivity | None:
    started_at = ""
    cwd = ""
    model = ""
    tool_calls = 0
    last_command = ""

    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                try:
                    entry: dict[str, Any] = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                payload = entry.get("payload") or {}
                if entry.get("type") == "turn_context":
                    started_at = started_at or str(entry.get("timestamp") or "")
                    cwd = cwd or str(payload.get("cwd") or "")
                    model = model or str(payload.get("model") or "")
                    continue
                if entry.get("type") != "response_item":
                    continue
                item_type = payload.get("type")
                if item_type != "function_call":
                    continue
                name = str(payload.get("name") or "")
                arguments = payload.get("arguments")
                if name:
                    tool_calls += 1
                if name == "exec_command" and isinstance(arguments, str):
                    try:
                        args_obj = json.loads(arguments)
                    except json.JSONDecodeError:
                        args_obj = {}
                    cmd = args_obj.get("cmd")
                    if isinstance(cmd, str) and cmd.strip():
                        last_command = _clip(_redact_command(cmd), 120)
    except OSError:
        return None

    if not started_at and not cwd and not model and tool_calls == 0:
        return None

    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0

    return CodexActivity(
        path=str(path),
        mtime=mtime,
        started_at=started_at,
        cwd=_clip(cwd, 96),
        model=_clip(model, 64),
        tool_calls=tool_calls,
        last_command=last_command,
    )


def list_recent_codex_activity(
    *,
    limit: int = 5,
    max_age_seconds: int = 6 * 60 * 60,
    max_files: int = 40,
) -> list[CodexActivity]:
    """Return recent Codex rollout metadata for control-plane visibility.

    This deliberately avoids reading or returning user/assistant transcript
    bodies.  It exposes only session path, timestamps, cwd, model, tool-call
    count, and the last shell command preview.
    """
    root = _codex_sessions_root()
    now = time.time()
    rows: list[CodexActivity] = []
    for path in _iter_recent_rollouts(root, max_files=max_files):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if max_age_seconds > 0 and now - mtime > max_age_seconds:
            continue
        activity = _read_activity(path)
        if activity is not None:
            rows.append(activity)
        if len(rows) >= limit:
            break
    return rows


def format_age_short(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h"
    return f"{hours // 24}d"
