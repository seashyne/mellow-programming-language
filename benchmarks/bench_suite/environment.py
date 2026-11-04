from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import ROOT


def _tool_version(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    text = (completed.stdout or completed.stderr).strip()
    return text or None


def _git_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _environment(mellow_binary: Path, zig_path: str | None) -> dict[str, Any]:
    return {
        "timestamp_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "root": str(ROOT),
        "git_commit": _git_commit(),
        "host": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": {
            "executable": sys.executable,
            "version": platform.python_version(),
        },
        "tools": {
            "mellow_binary": str(mellow_binary),
            "mellow_version": _tool_version([str(mellow_binary), "--version"])
            if mellow_binary.exists()
            else None,
            "zig": {
                "path": zig_path,
                "version": _tool_version([zig_path, "version"]) if zig_path else None,
            },
            "c_compiler": shutil.which("gcc") or shutil.which("clang") or shutil.which("cl"),
            "lua": shutil.which("lua") or shutil.which("luajit"),
        },
    }
