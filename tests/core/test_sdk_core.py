from __future__ import annotations

from unittest.mock import patch

import pytest

from mellowlang.host.runtime import MODULE_ALLOWLIST, default_host


def test_sdk_module_is_allowlisted():
    assert "sdk" in MODULE_ALLOWLIST
    assert "chat" in MODULE_ALLOWLIST
    assert MODULE_ALLOWLIST["chat"]["completions_create"] == "std.sdk.chat_completions_create"
    assert MODULE_ALLOWLIST["sdk"]["openai_chat"] == "std.sdk.openai_chat"


def test_sdk_describe_reports_backends():
    host = default_host()
    info = host.call("std.sdk.describe", [])
    assert info["name"] == "mellow-sdk"
    assert info["version"] == "0.3.0"
    assert info["recommended_entry"] == "use mellow-sdk as openai"
    assert "client.chat.completions.create(...)" in info["python_mapping"]
    assert "rest" in info["backends"]
    assert "openai-sdk" in info["backends"]


def test_deepseek_client_defaults():
    host = default_host()
    client = host.call("std.sdk.deepseek_client", [{}])
    assert client["api_key_env"] == "DEEPSEEK_API_KEY"
    assert client["base_url"] == "https://api.deepseek.com"


def test_openai_chat_rest_backend():
    host = default_host()
    host.set_runtime_config({"project_mode": False})
    fake_response = {
        "choices": [{"message": {"content": "Hello from DeepSeek"}}],
    }
    with patch("mellowlang.sdk_core.http_post_json", return_value=fake_response):
        result = host.call(
            "std.sdk.openai_chat",
            [
                {
                    "api_key": "test-key",
                    "base_url": "https://api.deepseek.com",
                    "backend": "rest",
                },
                "deepseek-chat",
                [{"role": "user", "content": "Hello"}],
                {"thinking": {"type": "enabled"}, "reasoning_effort": "high"},
            ],
        )
    assert result["ok"] is True
    assert result["backend"] == "rest"
    assert result["content"] == "Hello from DeepSeek"
    assert result["choices"][0]["message"]["content"] == "Hello from DeepSeek"


def test_openai_chat_requires_api_key():
    host = default_host()
    host.set_runtime_config({"project_mode": False})
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(RuntimeError) as exc:
            host.call(
                "std.sdk.openai_chat",
                [
                    {"base_url": "https://api.deepseek.com", "backend": "rest"},
                    "deepseek-chat",
                    [{"role": "user", "content": "Hello"}],
                    {},
                ],
            )
    assert "api_key is required" in str(exc.value)


def test_openai_chat_respects_project_net_allowlist():
    host = default_host()
    host.set_runtime_config(
        {
            "project_mode": True,
            "allow_net": True,
            "net_http_allow": "https://api.openai.com/",
        }
    )
    with pytest.raises(RuntimeError) as exc:
        host.call(
            "std.sdk.openai_chat",
            [
                {"api_key": "test-key", "base_url": "https://api.deepseek.com", "backend": "rest"},
                "deepseek-chat",
                [{"role": "user", "content": "Hello"}],
                {},
            ],
        )
    assert "not allowlisted" in str(exc.value)
