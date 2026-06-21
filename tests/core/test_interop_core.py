from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from mellowlang.host.runtime import MODULE_ALLOWLIST, default_host


def test_interop_module_is_allowlisted():
    assert "interop" in MODULE_ALLOWLIST
    assert MODULE_ALLOWLIST["interop"]["run"] == "std.interop.run"
    assert MODULE_ALLOWLIST["interop"]["describe"] == "std.interop.describe"


def test_interop_run_is_deny_by_default(tmp_path: Path):
    tool = tmp_path / "tool.py"
    tool.write_text("print('{}')\n", encoding="utf-8")
    host = default_host()
    with pytest.raises(RuntimeError) as exc:
        host.call("std.interop.run", [sys.executable, [str(tool)], {}])
    assert "allowlisted" in str(exc.value)


def test_interop_run_calls_json_stdio_tool(tmp_path: Path):
    tool = tmp_path / "tool.py"
    tool.write_text(
        "import json, sys\n"
        "data = json.loads(sys.stdin.read())\n"
        "payload = data['payload']\n"
        "print(json.dumps({'hello': payload['name'], 'protocol': data['protocol']}))\n",
        encoding="utf-8",
    )
    host = default_host()
    host.set_runtime_config(
        {
            "interop_allow": Path(sys.executable).name.lower(),
            "project_root": str(tmp_path),
        }
    )
    res = host.call(
        "std.interop.run",
        [
            sys.executable,
            [str(tool)],
            {"name": "Mellow"},
            {"timeout_s": 5},
        ],
    )
    assert res["ok"] is True
    assert res["code"] == 0
    assert res["result"] == {"hello": "Mellow", "protocol": "mellow.interop.v1"}


def test_interop_plain_stdout_is_preserved(tmp_path: Path):
    tool = tmp_path / "tool.py"
    tool.write_text("print('plain output')\n", encoding="utf-8")
    host = default_host()
    host.set_runtime_config({"interop_allow": Path(sys.executable).name.lower()})
    res = host.call("std.interop.run", [sys.executable, [str(tool)], {}])
    assert res["ok"] is True
    assert res["result"] == {"stdout": "plain output\n"}
