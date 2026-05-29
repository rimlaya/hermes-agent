from types import SimpleNamespace

from agent.codex_runtime import run_codex_app_server_turn


class FakeCodexSession:
    def __init__(self):
        self.user_input = None

    def run_turn(self, *, user_input):
        self.user_input = user_input
        return SimpleNamespace(
            should_retire=False,
            projected_messages=[],
            tool_iterations=0,
            interrupted=False,
            error=None,
            final_text="ok",
            thread_id="thread-1",
            turn_id="turn-1",
        )


def test_codex_app_server_turn_preserves_multimodal_user_message_for_transport():
    session = FakeCodexSession()
    agent = SimpleNamespace(
        _codex_session=session,
        _iters_since_skill=0,
        _skill_nudge_interval=0,
        valid_tool_names=set(),
        _sync_external_memory_for_turn=lambda **_: None,
    )
    user_message = [
        {"type": "text", "text": "Please inspect this."},
        {"type": "image_url", "image_url": {"url": "https://example.test/a.png"}},
    ]

    result = run_codex_app_server_turn(
        agent,
        user_message=user_message,
        original_user_message=user_message,
        messages=[],
        effective_task_id="task-1",
    )

    assert result["completed"] is True
    assert session.user_input is user_message
