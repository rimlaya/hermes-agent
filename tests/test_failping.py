import logging

from agent.failping import failping


def test_failping_emits_sanitized_marker(caplog):
    logger = logging.getLogger("tests.failping")
    long_error = RuntimeError("failed\nwith token sk-testsecret1234567890" + "x" * 300)

    with caplog.at_level(logging.WARNING, logger="tests.failping"):
        failping(
            logger,
            component="tool:exec command",
            signature="Runtime Error",
            error=long_error,
        )

    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert message.startswith("[FAILPING] component=tool:exec_command signature=Runtime_Error msg=")
    assert "\n" not in message
    assert "sk-testsecret" not in message
    assert len(message) < 360
