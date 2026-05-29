from __future__ import annotations

import json

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
