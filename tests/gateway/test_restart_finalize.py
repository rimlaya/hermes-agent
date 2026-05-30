from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from gateway.builtin_hooks import startup_restart_finalize
from gateway.config import Platform
from gateway.restart_finalize import (
    clear_pending_finalize_marker,
    main,
    marker_path,
    read_pending_finalize_marker,
    write_pending_finalize_marker,
)


class _SendResult:
    success = True


class _Adapter:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict | None]] = []

    async def send(self, chat_id: str, message: str, metadata: dict | None = None):
        self.sent.append((chat_id, message, metadata))
        return _SendResult()


class _Config:
    def __init__(self) -> None:
        self.platforms = {}
        self._homes = {
            Platform.DISCORD: SimpleNamespace(chat_id="coord", thread_id="thread-1"),
        }

    def get_home_channel(self, platform):
        return self._homes.get(platform)


def test_write_read_and_clear_pending_finalize_marker(tmp_path):
    path = write_pending_finalize_marker(
        "tsk-abc123",
        agent="mia",
        summary="closed before restart",
        home=tmp_path,
    )

    assert path == marker_path(tmp_path)
    marker = read_pending_finalize_marker(tmp_path)
    assert marker is not None
    assert marker.task_id == "tsk-abc123"
    assert marker.agent == "mia"
    assert marker.notice == "restarted for tsk-abc123 (done)"

    clear_pending_finalize_marker(tmp_path)
    assert read_pending_finalize_marker(tmp_path) is None


def test_invalid_pending_finalize_marker_is_cleared(tmp_path):
    marker_path(tmp_path).write_text(
        json.dumps({"schema": 1, "task_id": "../bad", "agent": "mia"})
    )

    assert read_pending_finalize_marker(tmp_path) is None
    assert not marker_path(tmp_path).exists()


def test_write_rejects_unknown_agent(tmp_path):
    with pytest.raises(ValueError):
        write_pending_finalize_marker("tsk-abc123", agent="other", home=tmp_path)


def test_cli_writes_and_shows_marker(tmp_path, capsys):
    rc = main(
        [
            "write",
            "--task",
            "tsk-abc123",
            "--agent",
            "mia",
            "--home",
            str(tmp_path),
        ]
    )
    assert rc == 0
    assert str(marker_path(tmp_path)) in capsys.readouterr().out

    rc = main(["show", "--home", str(tmp_path)])
    assert rc == 0
    assert '"task_id": "tsk-abc123"' in capsys.readouterr().out


@pytest.mark.asyncio
async def test_startup_hook_posts_notice_and_clears_marker(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_PROFILE", "mia")
    write_pending_finalize_marker("tsk-abc123", agent="mia", home=tmp_path)
    adapter = _Adapter()

    await startup_restart_finalize.handle(
        "gateway:startup",
        {
            "adapters": {Platform.DISCORD: adapter},
            "config": _Config(),
        },
    )

    assert adapter.sent == [
        ("coord", "restarted for tsk-abc123 (done)", {"thread_id": "thread-1"}),
    ]
    assert not marker_path(tmp_path).exists()


@pytest.mark.asyncio
async def test_startup_hook_keeps_marker_when_send_not_possible(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_PROFILE", "mia")
    write_pending_finalize_marker("tsk-abc123", agent="mia", home=tmp_path)

    await startup_restart_finalize.handle(
        "gateway:startup",
        {"adapters": {}, "config": _Config()},
    )

    assert marker_path(tmp_path).exists()
