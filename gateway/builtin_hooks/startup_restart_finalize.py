"""Startup hook for restart-finalize markers."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Iterable

from gateway.config import Platform
from gateway.restart_finalize import (
    RestartFinalizeMarker,
    clear_pending_finalize_marker,
    read_pending_finalize_marker,
)


HOOK_NAME = "restart-finalize-notice"
DESCRIPTION = "Posts completion notices for tasks that closed before gateway restart."
EVENTS = ("gateway:startup",)
SUPPORTED_AGENTS = {"mia", "yomi", "sion"}

logger = logging.getLogger(__name__)


def _startup_agent() -> str:
    explicit = os.getenv("HERMES_RESTART_FINALIZE_AGENT", "").strip().lower()
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


def _platform_value(platform: Any) -> str:
    return str(getattr(platform, "value", platform))


def _ordered_adapters(adapters: dict[Any, Any]) -> Iterable[tuple[Any, Any]]:
    items = list(adapters.items())
    items.sort(key=lambda item: 0 if _platform_value(item[0]) == "discord" else 1)
    return items


async def _send_notice(marker: RestartFinalizeMarker, context: dict[str, Any]) -> bool:
    adapters = context.get("adapters") or {}
    config = context.get("config")
    if not isinstance(adapters, dict) or config is None:
        logger.warning("Restart-finalize notice skipped: startup context lacks adapters/config")
        return False

    for platform, adapter in _ordered_adapters(adapters):
        platform_value = _platform_value(platform)
        try:
            platform_enum = platform if isinstance(platform, Platform) else Platform(platform_value)
        except ValueError:
            platform_enum = platform

        home = config.get_home_channel(platform_enum)
        if not home or not getattr(home, "chat_id", None):
            continue

        platform_cfg = getattr(config, "platforms", {}).get(platform_enum)
        if platform_cfg is not None and not getattr(platform_cfg, "gateway_restart_notification", True):
            logger.info("Restart-finalize notice suppressed for %s", platform_value)
            continue

        metadata = {"thread_id": home.thread_id} if getattr(home, "thread_id", None) else None
        result = await adapter.send(str(home.chat_id), marker.notice, metadata=metadata)
        if result is not None and getattr(result, "success", True) is False:
            logger.warning(
                "Restart-finalize notice to %s:%s failed: %s",
                platform_value,
                home.chat_id,
                getattr(result, "error", "send returned success=False"),
            )
            continue

        logger.info("Restart-finalize notice sent for %s via %s", marker.task_id, platform_value)
        return True

    logger.warning("Restart-finalize notice skipped: no deliverable home channel")
    return False


async def handle(event_type: str, context: dict[str, Any]) -> None:
    if event_type != "gateway:startup":
        return

    marker = read_pending_finalize_marker()
    if marker is None:
        return

    agent = _startup_agent()
    if agent and marker.agent != agent:
        logger.debug(
            "Restart-finalize marker skipped: marker agent=%s startup agent=%s",
            marker.agent,
            agent,
        )
        return

    if await _send_notice(marker, context):
        clear_pending_finalize_marker()

