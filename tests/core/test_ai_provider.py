from __future__ import annotations

from unittest.mock import patch

import pytest

from mellowlang.ai.state import _API_CONFIG
from mellowlang.compiler import Compiler
from mellowlang.host.runtime import default_host
from mellowlang.vm import MellowVM, RunConfig


@pytest.fixture(autouse=True)
def restore_api_config():
    snapshot = {name: dict(config) for name, config in _API_CONFIG.items()}
    yield
    _API_CONFIG.clear()
    _API_CONFIG.update(snapshot)


def _configure(host, name, config):
    return host.call("std.ai.api_configure", [name, config])


def test_openai_compatible_complete_builds_request_and_response():
    host = default_host()
    host.set_runtime_config({"allow_net": True, "net_http_allow": "https://llm.test/"})
    configured = _configure(
        host,
        "openai",
        {"base_url": "https://llm.test/v1", "model": "test-model", "api_key": "sk-secret"},
    )
    assert configured["config"]["mode"] == "openai"
    assert configured["config"]["api_key"] == "***"

    fake = {
        "choices": [{"message": {"role": "assistant", "content": "pong"}}],
        "usage": {"total_tokens": 3},
    }
    with patch("mellowlang.net_core.http_post_json", return_value=fake) as post:
        reply = host.call("std.ai.api_complete", ["openai", "ping", {"temperature": 0.2}])

    url = post.call_args.args[0]
    body = post.call_args.args[1]
    headers = post.call_args.kwargs["headers"]
    assert url == "https://llm.test/v1/chat/completions"
    assert body == {
        "model": "test-model",
        "messages": [{"role": "user", "content": "ping"}],
        "temperature": 0.2,
    }
    assert headers["Authorization"] == "Bearer sk-secret"
    assert reply["response"] == "pong"
    assert reply["model"] == "test-model"
    assert reply["usage"] == {"total_tokens": 3}
    assert reply["config"]["api_key"] == "***"


def test_openai_compatible_uses_env_key_and_system_prompt(monkeypatch):
    monkeypatch.setenv("MELLOW_TEST_API_KEY", "sk-env")
    host = default_host()
    host.set_runtime_config({"allow_net": True, "net_http_allow": "https://llm.test/"})
    _configure(
        host,
        "remote",
        {
            "base_url": "https://llm.test/v1/chat/completions",
            "model": "m",
            "api_key_env": "MELLOW_TEST_API_KEY",
        },
    )
    fake = {"choices": [{"message": {"content": [{"text": "part one"}, {"text": " part two"}]}}]}
    with patch("mellowlang.net_core.http_post_json", return_value=fake) as post:
        reply = host.call("std.ai.api_complete", ["remote", "hi", {"system": "be brief"}])

    assert post.call_args.args[0] == "https://llm.test/v1/chat/completions"
    assert post.call_args.args[1]["messages"] == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hi"},
    ]
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer sk-env"
    assert reply["response"] == "part one part two"


def test_openai_provider_requires_network_permission():
    host = default_host()
    _configure(host, "openai", {"base_url": "https://llm.test/v1", "api_key": "sk"})
    host.set_runtime_config({"allow_net": False})
    with pytest.raises(RuntimeError, match="net is disabled"):
        host.call("std.ai.api_complete", ["openai", "ping"])


def test_openai_provider_requires_allowlisted_url():
    host = default_host()
    host.set_runtime_config({"allow_net": True, "net_http_allow": "https://other.test/"})
    _configure(host, "openai", {"base_url": "https://llm.test/v1", "api_key": "sk"})
    with pytest.raises(RuntimeError, match="url not allowlisted"):
        host.call("std.ai.api_complete", ["openai", "ping"])


def test_configure_rejects_non_http_base_url():
    host = default_host()
    with pytest.raises(RuntimeError, match="requires an http"):
        _configure(host, "openai", {"base_url": "ftp://llm.test"})


def test_offline_provider_is_unchanged():
    host = default_host()
    reply = host.call("std.ai.api_complete", ["offline", "hello mellow", {"style": "test"}])
    assert reply["response"] == "[offline/test] hello mellow"
    assert reply["config"]["mode"] == "offline"


def test_providers_listing_redacts_secrets():
    host = default_host()
    _configure(host, "openai", {"base_url": "https://llm.test", "api_key": "sk-secret"})
    providers = host.call("std.ai.api_providers", [])
    listed = next(p for p in providers if p["name"] == "openai")
    assert listed["api_key"] == "***"
    assert "sk-secret" not in repr(providers)


def test_ai_provider_reaches_both_engines_from_source(capsys):
    source = (
        'let reply = call ai.api_complete("offline", "hello", {"style": "doc"})\n'
        'print(reply["response"])\n'
    )
    program = Compiler().compile(source, filename="<ai-provider-test>")
    for engine in ("py", "c"):
        MellowVM().run(program, config=RunConfig(engine=engine))
    assert capsys.readouterr().out == "[offline/doc] hello\n" * 2
