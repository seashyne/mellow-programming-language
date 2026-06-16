from __future__ import annotations

import json

from mellowlang.agents.policy import PolicyEngine
from mellowlang.agents.tools import builtin_tool_registry
from mellowlang.benchmarking import run_benchmarks
from mellowlang.cli import main as cli_main
from mellowlang.security_audit import run_security_audit


def test_ai_tool_policy_is_default_deny():
    tool = builtin_tool_registry().get("search.docs")
    decision = PolicyEngine().check_tool("search.docs", getattr(tool, "capabilities", []))
    assert decision.allowed is False
    assert "default" in decision.reason


def test_ai_tool_policy_explicit_allow():
    tool = builtin_tool_registry().get("search.docs")
    decision = PolicyEngine(allowed_tools=["search.docs"]).check_tool("search.docs", getattr(tool, "capabilities", []))
    assert decision.allowed is True


def test_agent_run_allows_explicit_tool(tmp_path, capsys):
    obs = tmp_path / "obs.jsonl"
    code = cli_main([
        "agent",
        "run",
        "--task",
        "search Mellow docs",
        "--tool",
        "search.docs",
        "--obs",
        str(obs),
        "--json",
    ])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["tool_calls"][0]["tool"] == "search.docs"


def test_benchmark_smoke():
    result = run_benchmarks(rounds=1)
    assert result["ok"] is True
    assert {suite["name"] for suite in result["suites"]} >= {"compiler", "python-vm", "native-host-batch"}


def test_security_audit_smoke_without_package_scan():
    result = run_security_audit(include_packages=False)
    assert result["ok"] is True
    assert result["errors"] == 0


def test_cli_bench_json(capsys):
    assert cli_main(["bench", "--rounds", "1", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True


def test_cli_security_audit_json_without_packages(capsys):
    assert cli_main(["security", "audit", "--no-packages", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
