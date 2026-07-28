from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from agent.autonomy_control import (
    clear_autonomy,
    format_autonomy_state,
    get_autonomy_state,
    log_autonomy_event,
    pause_autonomy,
    resume_autonomy,
)


def test_pause_resume_and_clear_use_control_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_AUTONOMY_CONTROL_DIR", str(tmp_path))

    assert get_autonomy_state().paused is False

    paused = pause_autonomy("phase gate")
    assert paused.paused is True
    assert paused.reason == "phase gate"
    assert "phase gate" in format_autonomy_state(paused)

    resumed = resume_autonomy()
    assert resumed.paused is False
    assert format_autonomy_state(resumed) == "running"

    pause_autonomy("again")
    cleared = clear_autonomy()
    assert cleared.paused is False


def test_audit_log_clips_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_AUTONOMY_CONTROL_DIR", str(tmp_path))

    log_autonomy_event("background_start", objective="x" * 700, task_id="bg_1")

    rows = [
        json.loads(line)
        for line in (tmp_path / "autonomy_audit.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["event"] == "background_start"
    assert rows[0]["task_id"] == "bg_1"
    assert rows[0]["objective"].endswith("...")
    assert len(rows[0]["objective"]) == 500


@pytest.mark.asyncio
async def test_gateway_background_command_writes_autonomy_audit(tmp_path, monkeypatch):
    """The gateway /background launch path must remain auditable."""
    from gateway.config import Platform
    from gateway.platforms.base import MessageEvent
    from gateway.run import GatewayRunner
    from gateway.session import SessionSource

    monkeypatch.setenv("HERMES_AUTONOMY_CONTROL_DIR", str(tmp_path))
    runner = object.__new__(GatewayRunner)
    runner._background_tasks = set()
    runner._run_background_task = MagicMock()
    event = MessageEvent(
        text="/background inspect the queue",
        source=SessionSource(
            platform=Platform.DISCORD,
            user_id="user-1",
            chat_id="channel-1",
        ),
    )

    def capture_task(coro, *args, **kwargs):
        coro.close()
        return MagicMock()

    with patch("gateway.run.asyncio.create_task", side_effect=capture_task):
        result = await runner._handle_background_command(event)

    row = json.loads(
        (tmp_path / "autonomy_audit.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert "Background task started" in result
    assert row["event"] == "background_start"
    assert row["surface"] == "gateway"
    assert row["objective"] == "inspect the queue"
    assert row["autonomy_state"] == "running"
    assert row["stop_condition"] == "/stop"
    assert row["session_id"] == row["task_id"]
    assert row["source"] == "discord:channel-1"
