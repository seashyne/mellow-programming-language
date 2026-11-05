"""The unified offline AI API layer, plus the OpenAI-compatible HTTP provider."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from .models import ai_embed
from .state import _API_CONFIG

_REDACTED = "***"
_SECRET_HEADERS = {"authorization", "api-key", "x-api-key"}


def _redact(config: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(config)
    if out.get("api_key"):
        out["api_key"] = _REDACTED
    headers = out.get("headers")
    if isinstance(headers, dict) and headers:
        out["headers"] = {
            str(k): _REDACTED if str(k).lower() in _SECRET_HEADERS else v
            for k, v in headers.items()
        }
    return out


def ai_api_providers(args: List[Any]) -> Any:
    return [{"name": k, **_redact(v)} for k, v in sorted(_API_CONFIG.items())]

def ai_api_configure(args: List[Any]) -> Any:
    name = str(args[0]) if args else 'offline'
    config = dict(args[1]) if len(args) > 1 and isinstance(args[1], dict) else {}
    base = dict(_API_CONFIG.get(name, {"mode": "offline"}))
    base.update(config)
    if "base_url" in config and "mode" not in config:
        base["mode"] = "openai"
    if base.get("timeout_s") is not None:
        try:
            base["timeout_s"] = max(0.1, min(120.0, float(base["timeout_s"])))
        except (TypeError, ValueError) as exc:
            raise RuntimeError("AI_PROVIDER_CONFIG: timeout_s must be a number") from exc
    if str(base.get("mode", "offline")).lower() == "openai":
        base_url = str(base.get("base_url") or "")
        if not (base_url.startswith("http://") or base_url.startswith("https://")):
            raise RuntimeError("AI_PROVIDER_CONFIG: openai mode requires an http(s) base_url")
    base.setdefault('status', 'ready')
    _API_CONFIG[name] = base
    return {"provider": name, "config": _redact(base), "status": "configured"}

def ai_api_complete(args: List[Any], *, runtime_config: Optional[Dict[str, Any]] = None) -> Any:
    provider = str(args[0]) if args else 'offline'
    prompt = str(args[1]) if len(args) > 1 else ''
    options = dict(args[2]) if len(args) > 2 and isinstance(args[2], dict) else {}
    cfg = _API_CONFIG.get(provider, _API_CONFIG['offline'])
    if str(cfg.get('mode', 'offline')).lower() == 'openai':
        return _complete_openai(provider, prompt, options, cfg, dict(runtime_config or {}))
    style = str(options.get('style', 'concise'))
    max_words = int(options.get('max_words', 48))
    text = prompt.strip()
    if provider == 'local-rag':
        response = f"[local-rag] {text[:max_words*2]}"
    elif 'summar' in text.lower():
        words = text.split()
        response = ' '.join(words[:max_words])
    else:
        response = f"[{provider}/{style}] {text}"[: max(24, max_words * 8)]
    return {"provider": provider, "response": response, "options": options, "config": _redact(cfg)}

def _complete_openai(provider: str, prompt: str, options: Dict[str, Any], cfg: Dict[str, Any], runtime_config: Dict[str, Any]) -> Any:
    base_url = str(cfg.get('base_url') or '').rstrip('/')
    url = base_url if base_url.endswith('/chat/completions') else base_url + '/chat/completions'
    _require_network(url, runtime_config)
    model = str(options.get('model') or cfg.get('model') or 'gpt-4o-mini')
    messages = options.get('messages')
    if not isinstance(messages, list) or not messages:
        messages = []
        system = options.get('system', cfg.get('system'))
        if system:
            messages.append({"role": "system", "content": str(system)})
        messages.append({"role": "user", "content": prompt})
    body: Dict[str, Any] = {"model": model, "messages": messages}
    for key in ("temperature", "max_tokens", "top_p"):
        value = options.get(key, cfg.get(key))
        if value is not None:
            body[key] = value
    headers: Dict[str, str] = {}
    key = _api_key(cfg)
    if key:
        headers['Authorization'] = f"Bearer {key}"
    extra = cfg.get('headers')
    if isinstance(extra, dict):
        for k, v in extra.items():
            headers[str(k)] = str(v)
    timeout_s = options.get('timeout_s', cfg.get('timeout_s', runtime_config.get('net_timeout_s', 30.0)))
    try:
        timeout_s = max(0.1, min(120.0, float(timeout_s)))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("AI_PROVIDER_CONFIG: timeout_s must be a number") from exc
    from ..net_core import http_post_json
    try:
        data = http_post_json(url, body, timeout_s=timeout_s, headers=headers)
    except Exception as exc:
        raise RuntimeError(f"AI_PROVIDER_ERROR: {exc}") from exc
    max_bytes = int(runtime_config.get('net_max_bytes', 262144) or 262144)
    if len(json.dumps(data, ensure_ascii=False).encode('utf-8')) > max_bytes:
        raise RuntimeError("NET_QUOTA_BYTES: response too large")
    choices = data.get('choices')
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise RuntimeError("AI_PROVIDER_ERROR: response has no choices")
    message = choices[0].get('message') if isinstance(choices[0].get('message'), dict) else {}
    content = message.get('content')
    if isinstance(content, list):
        content = ''.join(str(part.get('text', '')) if isinstance(part, dict) else str(part) for part in content)
    return {
        "provider": provider,
        "response": '' if content is None else str(content),
        "model": model,
        "usage": data.get('usage') if isinstance(data.get('usage'), dict) else {},
        "options": options,
        "config": _redact(cfg),
    }

def _api_key(cfg: Dict[str, Any]) -> str:
    key = str(cfg.get('api_key') or '')
    if key:
        return key
    env_name = str(cfg.get('api_key_env') or '')
    if not env_name:
        return ''
    key = os.environ.get(env_name, '')
    if not key:
        raise RuntimeError(f"AI_PROVIDER_CONFIG: environment variable {env_name} is empty")
    return key

def _require_network(url: str, runtime_config: Dict[str, Any]) -> None:
    if not bool(runtime_config.get('allow_net', False)):
        raise RuntimeError("SANDBOX: net is disabled")
    allow = str(runtime_config.get('net_http_allow') or '')
    if not allow:
        raise RuntimeError("SANDBOX: net_http: no allowlist configured")
    for prefix in allow.split(','):
        prefix = prefix.strip()
        if prefix and url.startswith(prefix):
            return
    raise RuntimeError("SANDBOX: net_http: url not allowlisted")

def ai_api_embed(args: List[Any]) -> Any:
    provider = str(args[0]) if args else 'offline'
    text = args[1] if len(args) > 1 else ''
    return {"provider": provider, "embedding": ai_embed([text])}
