from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _runtime_config(host: Any) -> dict[str, Any]:
    cfg = getattr(host, "runtime_config", None)
    return dict(cfg) if isinstance(cfg, dict) else {}


def _split_csv(value: Any) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(part).strip() for part in value if str(part).strip()]
    return []


def _allowed_commands(host: Any) -> set[str]:
    cfg = _runtime_config(host)
    allowed = set(_split_csv(cfg.get("interop_allow")))
    allowed.update(_split_csv(os.environ.get("MELLOW_INTEROP_ALLOW")))
    return allowed


def _command_key(command: str) -> str:
    return Path(command).name.lower()


def _is_allowed(host: Any, command: str) -> bool:
    allowed = _allowed_commands(host)
    if "*" in allowed:
        return True
    command_text = str(command).strip()
    keys = {command_text, command_text.lower(), _command_key(command_text)}
    resolved = shutil.which(command_text)
    if resolved:
        keys.add(resolved)
        keys.add(str(Path(resolved).resolve()))
        keys.add(Path(resolved).name.lower())
    return any(item in allowed for item in keys)


def _coerce_args(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise RuntimeError("std.interop.run: args must be a list")
    return [str(item) for item in value]


def _coerce_options(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise RuntimeError("std.interop.run: options must be a map")
    return dict(value)


def _safe_cwd(host: Any, options: dict[str, Any]) -> str | None:
    cfg = _runtime_config(host)
    project_root = cfg.get("project_root")
    if not options.get("cwd"):
        return str(project_root) if project_root else None
    if not project_root:
        return str(Path(str(options["cwd"])).resolve())
    root = Path(str(project_root)).resolve()
    cwd = (root / str(options["cwd"])).resolve()
    if cwd != root and root not in cwd.parents:
        raise RuntimeError("std.interop.run: cwd must stay inside project_root")
    return str(cwd)


def _parse_stdout(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except Exception:
        return {"stdout": text}


def register_interop_functions(host: Any) -> None:
    from .host.legacy import HostFunction

    def _available(args: list[Any]) -> bool:
        command = str(args[0]).strip()
        return bool(command and _is_allowed(host, command) and shutil.which(command))

    def _run(args: list[Any]) -> dict[str, Any]:
        command = str(args[0]).strip()
        if not command:
            raise RuntimeError("std.interop.run: command is required")
        if not _is_allowed(host, command):
            raise RuntimeError(
                "std.interop.run: command not allowlisted. "
                "Add permission in mellow.json, for example: \"interop:node\""
            )
        argv = [command] + _coerce_args(args[1] if len(args) >= 2 else [])
        payload = args[2] if len(args) >= 3 else {}
        options = _coerce_options(args[3] if len(args) >= 4 else {})
        timeout = float(options.get("timeout_s", 5))
        if timeout <= 0 or timeout > 30:
            raise RuntimeError("std.interop.run: timeout_s must be between 0 and 30")
        max_stdout = int(options.get("max_stdout", 1_000_000))
        if max_stdout <= 0 or max_stdout > 5_000_000:
            raise RuntimeError("std.interop.run: max_stdout must be between 1 and 5000000")
        envelope = {
            "protocol": "mellow.interop.v1",
            "payload": payload,
        }
        proc = subprocess.run(
            argv,
            input=json.dumps(envelope, ensure_ascii=False),
            capture_output=True,
            text=True,
            cwd=_safe_cwd(host, options),
            timeout=timeout,
            shell=False,
        )
        stdout = proc.stdout[:max_stdout]
        stderr = proc.stderr[:max_stdout]
        parsed = _parse_stdout(stdout)
        return {
            "ok": proc.returncode == 0,
            "code": proc.returncode,
            "result": parsed,
            "stdout": stdout,
            "stderr": stderr,
        }

    def _describe(args: list[Any]) -> dict[str, Any]:
        allowed = sorted(_allowed_commands(host))
        return {
            "protocol": "mellow.interop.v1",
            "allow": allowed,
            "formats": ["json-stdin", "json-stdout", "plain-stdout"],
            "examples": {
                "javascript": 'get interop.run("node", ["tool.js"], {"name":"Mellow"})',
                "go": 'get interop.run("go", ["run", "tool.go"], {"name":"Mellow"})',
                "binary": 'get interop.run("./target/release/tool", [], {"name":"Mellow"})',
            },
        }

    host.register(HostFunction("std.interop.available", _available, cost=1, min_args=1, max_args=1))
    host.register(HostFunction("std.interop.run", _run, cost=10, min_args=1, max_args=4))
    host.register(HostFunction("std.interop.describe", _describe, cost=1, min_args=0, max_args=0))
