"""Pending restart-finalize marker helpers.

The marker lets an agent close its Maestro task before restarting its own
gateway. On the next boot, a startup hook consumes the marker and emits a
short completion notice.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes_cli.config import get_hermes_home


MARKER_FILENAME = ".restart-finalize-pending.json"
TASK_ID_RE = re.compile(r"^tsk-[A-Za-z0-9][A-Za-z0-9_-]{2,}$")
SUPPORTED_AGENTS = {"mia", "yomi", "sion"}


@dataclass(frozen=True)
class RestartFinalizeMarker:
    task_id: str
    agent: str
    summary: str
    written_at: str

    @property
    def notice(self) -> str:
        return f"restarted for {self.task_id} (done)"


def marker_path(home: Path | None = None) -> Path:
    root = home if home is not None else get_hermes_home()
    return Path(root).expanduser() / MARKER_FILENAME


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_agent(agent: str | None) -> str:
    value = (agent or "").strip().lower()
    if value not in SUPPORTED_AGENTS:
        raise ValueError(f"unsupported restart-finalize agent: {agent!r}")
    return value


def _validate_task_id(task_id: str) -> str:
    value = (task_id or "").strip()
    if not TASK_ID_RE.match(value):
        raise ValueError(f"invalid Maestro task id: {task_id!r}")
    return value


def write_pending_finalize_marker(
    task_id: str,
    *,
    agent: str = "mia",
    summary: str = "",
    home: Path | None = None,
) -> Path:
    """Write the pending finalize marker atomically and return its path."""
    path = marker_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "schema": 1,
        "task_id": _validate_task_id(task_id),
        "agent": _normalize_agent(agent),
        "summary": str(summary or "").strip(),
        "written_at": _utc_now_iso(),
    }
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def read_pending_finalize_marker(home: Path | None = None) -> RestartFinalizeMarker | None:
    """Read and validate the marker without deleting it.

    Invalid or malformed markers are removed so gateway startup cannot get
    stuck retrying an unreadable file forever.
    """
    path = marker_path(home)
    if not path.exists():
        return None

    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("marker root is not an object")
        if int(data.get("schema", 0)) != 1:
            raise ValueError("unsupported marker schema")
        return RestartFinalizeMarker(
            task_id=_validate_task_id(str(data.get("task_id", ""))),
            agent=_normalize_agent(str(data.get("agent", ""))),
            summary=str(data.get("summary", "") or ""),
            written_at=str(data.get("written_at", "") or ""),
        )
    except Exception:
        clear_pending_finalize_marker(home)
        return None


def clear_pending_finalize_marker(home: Path | None = None) -> None:
    try:
        marker_path(home).unlink(missing_ok=True)
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage gateway restart-finalize markers")
    sub = parser.add_subparsers(dest="command", required=True)

    write_cmd = sub.add_parser("write", help="write a pending restart-finalize marker")
    write_cmd.add_argument(
        "--task",
        required=True,
        help="Maestro task id, e.g. tsk-abc123",
    )
    write_cmd.add_argument("--agent", default="mia", choices=sorted(SUPPORTED_AGENTS))
    write_cmd.add_argument("--summary", default="")
    write_cmd.add_argument("--home", type=Path, default=None)

    show_cmd = sub.add_parser("show", help="print the current marker JSON")
    show_cmd.add_argument("--home", type=Path, default=None)

    clear_cmd = sub.add_parser("clear", help="clear the current marker")
    clear_cmd.add_argument("--home", type=Path, default=None)

    args = parser.parse_args(argv)
    if args.command == "write":
        path = write_pending_finalize_marker(
            args.task,
            agent=args.agent,
            summary=args.summary,
            home=args.home,
        )
        print(path)
        return 0
    if args.command == "show":
        marker = read_pending_finalize_marker(args.home)
        if marker is None:
            return 1
        print(json.dumps(marker.__dict__, ensure_ascii=False, indent=2))
        return 0
    if args.command == "clear":
        clear_pending_finalize_marker(args.home)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
