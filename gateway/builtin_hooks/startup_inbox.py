"""Mia startup inbox pickup hook.

The hook is intentionally read-only: it asks Maestro for pending Mia inbox
messages at gateway startup and logs only the pending count.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


HOOK_NAME = "mia-startup-inbox-pickup"
DESCRIPTION = "Checks Mia's Maestro inbox at gateway startup."
EVENTS = ("gateway:startup",)

DEFAULT_VAULT = Path("/Users/miyaihisataka/Vault")
MAESTRO_TIMEOUT_SECONDS = 10
SUPPORTED_AGENTS = {"mia", "yomi", "sion"}

logger = logging.getLogger(__name__)


def _vault_root() -> Path:
    raw = os.getenv("HERMES_MAESTRO_VAULT", "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_VAULT


def _maestro_bin() -> str:
    return (
        os.getenv("HERMES_MAESTRO_BIN", "").strip()
        or shutil.which("maestro")
        or str(Path.home() / ".local" / "bin" / "maestro")
    )


def _startup_agent() -> str:
    explicit = os.getenv("HERMES_STARTUP_INBOX_AGENT", "").strip().lower()
    if explicit:
        return explicit

    profile = os.getenv("HERMES_PROFILE", "").strip().lower()
    if profile in SUPPORTED_AGENTS:
        return profile

    home = Path(os.getenv("HERMES_HOME", "")).expanduser()
    parts = [part.lower() for part in home.parts]
    try:
        idx = parts.index(".second-ai")
    except ValueError:
        return ""
    if idx + 1 < len(parts) and parts[idx + 1] in SUPPORTED_AGENTS:
        return parts[idx + 1]
    return ""


def _pending_count(stdout: str) -> int:
    try:
        data = json.loads(stdout or "[]")
    except json.JSONDecodeError:
        logger.warning("Mia startup inbox pickup returned invalid JSON")
        return 0
    if isinstance(data, list):
        return len(data)
    logger.warning("Mia startup inbox pickup returned unexpected JSON shape")
    return 0


def handle(event_type: str, context: dict[str, Any]) -> None:
    if event_type != "gateway:startup":
        return

    if _startup_agent() != "mia":
        logger.debug("Mia startup inbox pickup skipped: not the Mia gateway")
        return

    vault = _vault_root()
    if not vault.exists():
        logger.warning("Mia startup inbox pickup skipped: Vault root not found")
        return

    command = [
        _maestro_bin(),
        "inbox",
        "pickup-on-startup",
        "--for",
        "mia",
        "--json",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=str(vault),
            text=True,
            capture_output=True,
            timeout=MAESTRO_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Mia startup inbox pickup timed out")
        return
    except OSError as exc:
        logger.warning("Mia startup inbox pickup failed to start: %s", exc)
        return

    if result.returncode != 0:
        logger.warning(
            "Mia startup inbox pickup failed with exit %s",
            result.returncode,
        )
        return

    count = _pending_count(result.stdout)
    logger.info("Mia startup inbox pickup found %d pending message(s)", count)
