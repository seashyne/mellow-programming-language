from __future__ import annotations

from mellowlang.agents import AgentRuntime, MemoryStore, ObservationLog, PolicyEngine, SimpleRAGIndex, builtin_tool_registry, resolve_model_adapter
from mellowlang.diagnostics import diagnostics_for_source
from mellowlang.lsp_server import DOC_STORE, _publish, server
from mellowlang.playground.server import run_playground_session


def test_diagnostics_core_returns_ai_hints_for_syntax_error() -> None:
    payload = diagnostics_for_source("let = 1\n", filename="bad.mellow")
    assert payload["ok"] is False
    assert payload["compile_ok"] is False
    assert payload["diagnostics"]
    first = payload["diagnostics"][0]
    assert first["severity"] == "error"
    assert first["code"] == "E001"
    assert first["hints"]
    assert "Mellow diagnostic assistant" in payload["ai_prompt"]


def test_lsp_publish_uses_native_core_diagnostics() -> None:
    uri = "file:///bad.mellow"
    captured = {}
    server.publish_diagnostics = lambda published_uri, diags: captured.update({"uri": published_uri, "diags": diags})
    _publish(server, uri, "let = 1\n")
    published_uri, diags = captured["uri"], captured["diags"]
    assert published_uri == uri
    assert DOC_STORE[uri].startswith("let =")
    assert diags
    assert diags[0].source == "mellow-native-core"
    assert "AI hint:" in diags[0].message


def test_playground_compile_error_returns_structured_diagnostics() -> None:
    payload = run_playground_session("let = 1\n", include_dumps=False, trace=False, record_execution=False)
    assert payload["ok"] is False
    assert payload["stage"] == "compile"
    assert payload["diagnostics"]["diagnostics"]
    assert payload["debug_capabilities"]["engine_contract"] == "native-core-diagnostics"
    assert "Mellow diagnostic assistant" in payload["ai_prompt"]


def test_diagnostics_core_does_not_warn_for_known_host_module_calls() -> None:
    payload = diagnostics_for_source('let cash = money.of("1.00", "USD")\nprint(money.format(cash))\n', filename="money.mellow")
    messages = [item["message"] for item in payload["diagnostics"]]
    assert not any("money.of" in message or "money.format" in message for message in messages)


def test_agent_debug_payload_declares_native_core_contract(tmp_path) -> None:
    runtime = AgentRuntime(
        model=resolve_model_adapter("rule-based"),
        memory=MemoryStore(str(tmp_path / "memory.jsonl")),
        tools=builtin_tool_registry(),
        policy=PolicyEngine(),
        rag=SimpleRAGIndex.from_texts(["diagnostics"]),
        obs=ObservationLog(str(tmp_path / "obs.jsonl")),
    )
    result = runtime.run("say hi", debug=True)
    assert result.debug["native_core_contract"] == "agent-runtime-v1"
    assert result.debug["diagnostics_contract"] == "native-core-diagnostics-v1"
