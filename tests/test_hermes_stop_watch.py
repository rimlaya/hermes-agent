from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "hermes_stop_watch.py"


def load_watch_module():
    spec = importlib.util.spec_from_file_location("hermes_stop_watch", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_stopped_gateway_notifies_once(tmp_path, monkeypatch):
    watch = load_watch_module()
    calls = []

    monkeypatch.setattr(watch, "is_gateway_running", lambda cleanup_stale=False: False)
    monkeypatch.setattr(
        watch,
        "read_runtime_status",
        lambda: {
            "gateway_state": "stopped",
            "exit_reason": "unexpected SIGTERM",
            "updated_at": "2026-05-27T00:00:00+00:00",
        },
    )
    monkeypatch.setattr(
        watch,
        "send_notification",
        lambda command, title, body: calls.append((command, title, body)),
    )

    state_file = tmp_path / "state.json"
    args = ["--state-file", str(state_file), "--notify-command", "/tmp/notify"]

    assert watch.main(args) == 2
    assert watch.main(args) == 2

    assert len(calls) == 1
    assert calls[0][0] == "/tmp/notify"
    assert calls[0][1] == "Hermes gateway stopped"
    assert "unexpected SIGTERM" in calls[0][2]


def test_status_only_does_not_notify_or_write_state(tmp_path, monkeypatch):
    watch = load_watch_module()
    calls = []

    monkeypatch.setattr(watch, "is_gateway_running", lambda cleanup_stale=False: False)
    monkeypatch.setattr(watch, "read_runtime_status", lambda: None)
    monkeypatch.setattr(
        watch,
        "send_notification",
        lambda command, title, body: calls.append((command, title, body)),
    )

    state_file = tmp_path / "state.json"

    assert watch.main(["--status-only", "--state-file", str(state_file)]) == 2
    assert calls == []
    assert not state_file.exists()


def test_recovery_notification_clears_previous_problem(tmp_path, monkeypatch):
    watch = load_watch_module()
    calls = []
    state_file = tmp_path / "state.json"
    state_file.write_text('{"last_problem_key": "stopped:old"}', encoding="utf-8")

    monkeypatch.setattr(watch, "is_gateway_running", lambda cleanup_stale=False: True)
    monkeypatch.setattr(watch, "read_runtime_status", lambda: {"gateway_state": "running"})
    monkeypatch.setattr(
        watch,
        "send_notification",
        lambda command, title, body: calls.append((command, title, body)),
    )

    assert watch.main(["--recovery", "--state-file", str(state_file)]) == 0

    assert len(calls) == 1
    assert calls[0][1] == "Hermes gateway recovered"
    assert "last_problem_key" not in state_file.read_text(encoding="utf-8")
