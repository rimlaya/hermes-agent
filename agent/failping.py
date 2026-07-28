"""Structured fail-ping logging for retry/error handlers."""

from __future__ import annotations

import logging
import re
from typing import Any

from agent.redact import redact_sensitive_text

_MAX_MSG_CHARS = 240
_TOKEN_RE = re.compile(r"[^A-Za-z0-9_.:-]+")


def _compact_token(value: Any, *, default: str) -> str:
    text = str(value or "").strip() or default
    text = _TOKEN_RE.sub("_", text).strip("_")
    return text[:80] or default


def failping(
    logger: logging.Logger,
    *,
    component: str,
    signature: str | None = None,
    error: BaseException | str | None = None,
    msg: str | None = None,
) -> None:
    """Emit one grep-friendly FAILPING line without leaking large payloads."""
    if signature is None:
        if isinstance(error, BaseException):
            status = getattr(error, "status_code", None) or getattr(
                getattr(error, "response", None), "status_code", None
            )
            signature = f"{error.__class__.__name__}_{status}" if status else error.__class__.__name__
        else:
            signature = "failure"

    raw_msg = msg if msg is not None else (str(error) if error is not None else signature)
    clean_msg = redact_sensitive_text(str(raw_msg or "").replace("\n", " ").strip())
    if len(clean_msg) > _MAX_MSG_CHARS:
        clean_msg = clean_msg[: _MAX_MSG_CHARS - 3].rstrip() + "..."

    logger.warning(
        "[FAILPING] component=%s signature=%s msg=%s",
        _compact_token(component, default="unknown"),
        _compact_token(signature, default="failure"),
        clean_msg or _compact_token(signature, default="failure"),
    )
