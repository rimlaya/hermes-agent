"""Multimodal UserInput conversion for Codex app-server sessions."""

from __future__ import annotations

import base64
from pathlib import Path

from agent.transports.codex_app_server_session import _convert_to_user_inputs


def test_text_only_str_maps_to_text_user_input():
    assert _convert_to_user_inputs("hello") == [{"type": "text", "text": "hello"}]


def test_text_only_content_list_maps_to_text_user_input():
    assert _convert_to_user_inputs([{"type": "text", "text": "a"}]) == [
        {"type": "text", "text": "a"}
    ]


def test_text_and_http_image_url_maps_to_image_user_input():
    inputs = _convert_to_user_inputs(
        [
            {"type": "text", "text": "look"},
            {"type": "image_url", "image_url": {"url": "http://example.com/a.png"}},
        ]
    )

    assert inputs == [
        {"type": "text", "text": "look"},
        {"type": "image", "url": "http://example.com/a.png"},
    ]


def test_text_and_https_image_url_maps_to_image_user_input():
    inputs = _convert_to_user_inputs(
        [
            {"type": "text", "text": "look"},
            {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}},
        ]
    )

    assert inputs == [
        {"type": "text", "text": "look"},
        {"type": "image", "url": "https://example.com/a.png"},
    ]


def test_text_and_data_image_url_maps_to_local_image_user_input():
    image_url = "data:image/png;base64," + base64.b64encode(b"png-data").decode("ascii")
    cleanup_paths: list[Path] = []

    try:
        inputs = _convert_to_user_inputs(
            [
                {"type": "text", "text": "look"},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
            cleanup_paths=cleanup_paths,
        )

        assert inputs[0] == {"type": "text", "text": "look"}
        assert inputs[1]["type"] == "localImage"
        assert Path(inputs[1]["path"]).exists()
        assert Path(inputs[1]["path"]).read_bytes() == b"png-data"
        assert cleanup_paths == [Path(inputs[1]["path"])]
    finally:
        for path in cleanup_paths:
            path.unlink(missing_ok=True)


def test_text_and_file_image_url_maps_to_local_image_user_input():
    inputs = _convert_to_user_inputs(
        [
            {"type": "text", "text": "look"},
            {"type": "image_url", "image_url": "file:///tmp/example image.png"},
        ]
    )

    assert inputs == [
        {"type": "text", "text": "look"},
        {"type": "localImage", "path": "/tmp/example image.png"},
    ]


def test_unknown_content_block_is_skipped_with_trailing_note():
    inputs = _convert_to_user_inputs(
        [
            {"type": "text", "text": "keep"},
            {"type": "audio", "audio": {"url": "https://example.com/a.wav"}},
            {"unexpected": True},
        ]
    )

    assert inputs[0] == {"type": "text", "text": "keep"}
    assert inputs[1]["type"] == "text"
    assert inputs[1]["text"].startswith("[note: skipped 2 parts:")
    assert "audio" in inputs[1]["text"]
    assert "unknown" in inputs[1]["text"]


def test_empty_list_falls_back_to_empty_text():
    assert _convert_to_user_inputs([]) == [{"type": "text", "text": "(empty)"}]
