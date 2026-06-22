from __future__ import annotations

import os
from typing import Any

from .net_core import http_post_json

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_API_KEY_ENV = "OPENAI_API_KEY"


def _runtime_config(host: Any) -> dict[str, Any]:
    cfg = getattr(host, "runtime_config", None)
    return dict(cfg) if isinstance(cfg, dict) else {}


def _coerce_map(value: Any, *, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be a map")
    return dict(value)


def _resolve_api_key(config: dict[str, Any]) -> str:
    direct = str(config.get("api_key") or "").strip()
    if direct:
        return direct
    env_name = str(config.get("api_key_env") or DEFAULT_API_KEY_ENV).strip() or DEFAULT_API_KEY_ENV
    for candidate in (env_name, "OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        value = os.environ.get(candidate)
        if value:
            return str(value).strip()
    raise RuntimeError(
        "sdk.openai_chat: api_key is required. "
        "Pass api_key in client config or set OPENAI_API_KEY / DEEPSEEK_API_KEY."
    )


def _normalize_base_url(config: dict[str, Any]) -> str:
    base = str(config.get("base_url") or DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    return base.rstrip("/")


def _chat_completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    if "deepseek.com" in base:
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _shape_response(
    *,
    backend: str,
    model: str,
    base_url: str,
    content: str,
    raw: dict[str, Any],
) -> dict[str, Any]:
    message = {"role": "assistant", "content": content}
    choice = {"index": 0, "message": message, "finish_reason": "stop"}
    return {
        "ok": True,
        "backend": backend,
        "model": model,
        "base_url": base_url,
        "content": content,
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "message": message,
        "choice": choice,
        "raw": raw,
    }


def _check_net(host: Any, url: str) -> None:
    cfg = _runtime_config(host)
    if not cfg.get("project_mode"):
        return
    if not cfg.get("allow_net"):
        raise RuntimeError(
            'sdk.openai_chat: net is disabled. Add "net" to mellow.json permissions.'
        )
    allow = str(cfg.get("net_http_allow") or "")
    if not allow:
        raise RuntimeError(
            'sdk.openai_chat: no HTTP allowlist configured. '
            'Add net.http:https://api.example.com/ to mellow.json permissions.'
        )
    prefixes = [part.strip() for part in allow.split(",") if part.strip()]
    if not any(url.startswith(prefix) for prefix in prefixes):
        raise RuntimeError(f"sdk.openai_chat: URL not allowlisted: {url}")


def _build_request_body(model: str, messages: list[Any], options: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(messages, list):
        raise RuntimeError("sdk.openai_chat: messages must be a list")
    body: dict[str, Any] = {
        "model": str(model),
        "messages": messages,
        "stream": bool(options.get("stream", False)),
    }
    for key in ("temperature", "top_p", "max_tokens", "reasoning_effort"):
        if key in options and options[key] is not None:
            body[key] = options[key]
    extra_body = options.get("extra_body")
    if isinstance(extra_body, dict):
        body.update(extra_body)
    elif "thinking" in options and options["thinking"] is not None:
        body["thinking"] = options["thinking"]
    return body


def _extract_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("sdk.openai_chat: response missing choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise RuntimeError("sdk.openai_chat: invalid choice payload")
    message = first.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("sdk.openai_chat: response missing message")
    content = message.get("content")
    if content is None:
        return ""
    return str(content)


def _chat_rest(host: Any, config: dict[str, Any], model: str, messages: list[Any], options: dict[str, Any]) -> dict[str, Any]:
    api_key = _resolve_api_key(config)
    base_url = _normalize_base_url(config)
    url = _chat_completions_url(base_url)
    _check_net(host, url)
    timeout_s = float(options.get("timeout_s", config.get("timeout_s", 60.0)) or 60.0)
    body = _build_request_body(model, messages, options)
    headers = {"Authorization": f"Bearer {api_key}"}
    raw = http_post_json(url, body, timeout_s=timeout_s, headers=headers)
    content = _extract_content(raw)
    return _shape_response(
        backend="rest",
        model=str(model),
        base_url=base_url,
        content=content,
        raw=raw,
    )


def _chat_openai_sdk(host: Any, config: dict[str, Any], model: str, messages: list[Any], options: dict[str, Any]) -> dict[str, Any]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "sdk.openai_chat: openai package is not installed. "
            "Run: pip install openai"
        ) from exc

    api_key = _resolve_api_key(config)
    base_url = _normalize_base_url(config)
    url = _chat_completions_url(base_url)
    _check_net(host, url)

    client = OpenAI(api_key=api_key, base_url=base_url)
    kwargs: dict[str, Any] = {
        "model": str(model),
        "messages": messages,
        "stream": bool(options.get("stream", False)),
    }
    for key in ("temperature", "top_p", "max_tokens", "reasoning_effort"):
        if key in options and options[key] is not None:
            kwargs[key] = options[key]
    extra_body = options.get("extra_body")
    if isinstance(extra_body, dict):
        kwargs["extra_body"] = extra_body
    elif "thinking" in options and options["thinking"] is not None:
        kwargs["extra_body"] = {"thinking": options["thinking"]}

    timeout_s = options.get("timeout_s", config.get("timeout_s"))
    if timeout_s is not None:
        kwargs["timeout"] = float(timeout_s)

    response = client.chat.completions.create(**kwargs)
    message = response.choices[0].message
    content = "" if message.content is None else str(message.content)
    raw = response.model_dump() if hasattr(response, "model_dump") else {"choices": [{"message": {"content": content}}]}
    return _shape_response(
        backend="openai-sdk",
        model=str(model),
        base_url=base_url,
        content=content,
        raw=raw,
    )


def register_sdk_functions(host: Any) -> None:
    from .host.runtime import HostFunction

    def _openai_client(args: list[Any]) -> dict[str, Any]:
        config = _coerce_map(args[0] if args else None, label="sdk.openai_client")
        normalized = {
            "api_key": str(config.get("api_key") or "").strip(),
            "api_key_env": str(config.get("api_key_env") or DEFAULT_API_KEY_ENV).strip() or DEFAULT_API_KEY_ENV,
            "base_url": _normalize_base_url(config),
            "backend": str(config.get("backend") or "auto").strip() or "auto",
            "timeout_s": float(config.get("timeout_s", 60.0) or 60.0),
        }
        return normalized

    def _openai_chat(args: list[Any]) -> dict[str, Any]:
        if len(args) < 3:
            raise RuntimeError("sdk.openai_chat expects client, model, messages[, options]")
        client = _coerce_map(args[0], label="sdk.openai_chat client")
        model = str(args[1])
        messages = args[2]
        options = _coerce_map(args[3] if len(args) > 3 else None, label="sdk.openai_chat options")
        backend = str(client.get("backend") or options.get("backend") or "auto").strip().lower()
        if backend in {"sdk", "openai", "openai-sdk"}:
            return _chat_openai_sdk(host, client, model, messages, options)
        if backend in {"rest", "http"}:
            return _chat_rest(host, client, model, messages, options)
        try:
            return _chat_openai_sdk(host, client, model, messages, options)
        except RuntimeError as exc:
            if "openai package is not installed" not in str(exc):
                raise
            return _chat_rest(host, client, model, messages, options)

    def _describe(args: list[Any]) -> dict[str, Any]:
        has_openai = True
        try:
            import openai  # noqa: F401
        except ImportError:
            has_openai = False
        return {
            "name": "mellow-sdk",
            "version": "0.3.0",
            "style": "python-openai-sdk",
            "providers": ["openai", "deepseek", "openai-compatible"],
            "backends": ["auto", "openai-sdk", "rest"],
            "openai_installed": has_openai,
            "default_base_url": DEFAULT_BASE_URL,
            "default_api_key_env": DEFAULT_API_KEY_ENV,
            "example_env": ["OPENAI_API_KEY", "DEEPSEEK_API_KEY"],
            "recommended_entry": "use mellow-sdk as openai",
            "python_mapping": {
                "from openai import OpenAI": "use mellow-sdk as openai",
                "OpenAI(...)": "openai.OpenAI({...})",
                "client.chat.completions.create(...)": "call chat.completions_create(client, model, messages, options)",
                "response.choices[0].message.content": "response[\"choices\"][0][\"message\"][\"content\"]",
            },
        }

    def _deepseek_client(args: list[Any]) -> dict[str, Any]:
        config = _coerce_map(args[0] if args else None, label="sdk.deepseek_client")
        merged = {
            "api_key_env": "DEEPSEEK_API_KEY",
            "base_url": "https://api.deepseek.com",
        }
        merged.update(config)
        return _openai_client([merged])

    def _openai_preset_client(args: list[Any]) -> dict[str, Any]:
        config = _coerce_map(args[0] if args else None, label="sdk.openai_preset_client")
        merged = {
            "api_key_env": DEFAULT_API_KEY_ENV,
            "base_url": DEFAULT_BASE_URL,
        }
        merged.update(config)
        return _openai_client([merged])

    host.register(HostFunction("std.sdk.openai_client", _openai_client, cost=1, min_args=0, max_args=1))
    host.register(HostFunction("std.sdk.openai_preset_client", _openai_preset_client, cost=1, min_args=0, max_args=1))
    host.register(HostFunction("std.sdk.deepseek_client", _deepseek_client, cost=1, min_args=0, max_args=1))
    host.register(HostFunction("std.sdk.openai_chat", _openai_chat, cost=20, min_args=3, max_args=4))
    host.register(HostFunction("std.sdk.chat_completions_create", _openai_chat, cost=20, min_args=3, max_args=4))
    host.register(HostFunction("std.sdk.describe", _describe, cost=1, min_args=0, max_args=0))
