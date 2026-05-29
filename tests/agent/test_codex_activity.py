from __future__ import annotations

import json
import os
import time
from pathlib import Path

from agent.codex_activity import list_recent_codex_activity


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_list_recent_codex_activity_returns_metadata_only(tmp_path, monkeypatch):
    root = tmp_path / ".codex" / "sessions"
    rollout = root / "2026" / "05" / "20" / "rollout-test.jsonl"
    _write_jsonl(
        rollout,
        [
            {
                "timestamp": "2026-05-19T15:00:00.000Z",
                "type": "turn_context",
                "payload": {
                    "cwd": "/repo",
                    "model": "gpt-test",
                },
            },
            {
                "timestamp": "2026-05-19T15:01:00.000Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "secret transcript body"}],
                },
            },
            {
                "timestamp": "2026-05-19T15:02:00.000Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "arguments": json.dumps({"cmd": "OPENAI_API_KEY=sk-test curl -H 'Authorization: Bearer abc123' https://example.invalid"}),
                },
            },
        ],
    )
    now = time.time()
    os.utime(rollout, (now, now))
    monkeypatch.setenv("HERMES_CODEX_ACTIVITY_ROOT", str(root))

    rows = list_recent_codex_activity(limit=3)

    assert len(rows) == 1
    row = rows[0]
    assert row.cwd == "/repo"
    assert row.model == "gpt-test"
    assert row.tool_calls == 1
    assert row.last_command == "OPENAI_API_KEY=[redacted] curl -H 'Authorization: Bearer [redacted]' https://example.invalid"
    assert "secret transcript body" not in repr(row)
    assert "sk-test" not in row.last_command
    assert "abc123" not in row.last_command


def test_list_recent_codex_activity_ignores_old_sessions(tmp_path, monkeypatch):
    root = tmp_path / ".codex" / "sessions"
    rollout = root / "2026" / "05" / "20" / "rollout-old.jsonl"
    _write_jsonl(
        rollout,
        [
            {
                "timestamp": "2026-05-19T15:00:00.000Z",
                "type": "turn_context",
                "payload": {"cwd": "/repo", "model": "gpt-test"},
            }
        ],
    )

    now = time.time()
    old = now - 48 * 60 * 60
    os.utime(rollout, (old, old))
    monkeypatch.setenv("HERMES_CODEX_ACTIVITY_ROOT", str(root))

    assert list_recent_codex_activity(max_age_seconds=60) == []
