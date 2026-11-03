"""The unified offline AI API layer."""

from __future__ import annotations

from typing import Any, List


from .models import ai_embed
from .state import _API_CONFIG


def ai_api_providers(args: List[Any]) -> Any:
    return [{"name": k, **v} for k, v in sorted(_API_CONFIG.items())]

def ai_api_configure(args: List[Any]) -> Any:
    name = str(args[0]) if args else 'offline'
    config = dict(args[1]) if len(args) > 1 and isinstance(args[1], dict) else {}
    base = dict(_API_CONFIG.get(name, {"mode": "offline"}))
    base.update(config)
    base.setdefault('status', 'ready')
    _API_CONFIG[name] = base
    return {"provider": name, "config": base, "status": "configured"}

def ai_api_complete(args: List[Any]) -> Any:
    provider = str(args[0]) if args else 'offline'
    prompt = str(args[1]) if len(args) > 1 else ''
    options = dict(args[2]) if len(args) > 2 and isinstance(args[2], dict) else {}
    cfg = _API_CONFIG.get(provider, _API_CONFIG['offline'])
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
    return {"provider": provider, "response": response, "options": options, "config": cfg}

def ai_api_embed(args: List[Any]) -> Any:
    provider = str(args[0]) if args else 'offline'
    text = args[1] if len(args) > 1 else ''
    return {"provider": provider, "embedding": ai_embed([text])}
