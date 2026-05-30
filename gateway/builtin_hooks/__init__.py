"""Built-in gateway hooks that are always registered."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import startup_inbox, startup_restart_finalize

if TYPE_CHECKING:
    from gateway.hooks import HookRegistry


def register_builtin_hooks(registry: "HookRegistry") -> None:
    """Register shipped gateway hooks."""
    registry.register_handler(
        name=startup_inbox.HOOK_NAME,
        description=startup_inbox.DESCRIPTION,
        events=list(startup_inbox.EVENTS),
        handler=startup_inbox.handle,
        path="gateway.builtin_hooks.startup_inbox",
    )
    registry.register_handler(
        name=startup_restart_finalize.HOOK_NAME,
        description=startup_restart_finalize.DESCRIPTION,
        events=list(startup_restart_finalize.EVENTS),
        handler=startup_restart_finalize.handle,
        path="gateway.builtin_hooks.startup_restart_finalize",
    )
