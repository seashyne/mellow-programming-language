"""Mellow SDK — OpenAI-compatible provider bridge.

Can be used standalone from stdin/stdout or via mellow interop.

Install:
    pip install openai

Example:
    echo '{"model":"deepseek-chat","messages":[{"role":"user","content":"Hello"}]}' \\
      | python -m mellow_sdk.openai_bridge
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any


def _read_request() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("request must be a JSON object")
    return data


def chat(request: dict[str, Any]) -> dict[str, Any]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Please install OpenAI SDK first: pip install openai") from exc

    api_key = str(
        request.get("api_key")
        or os.environ.get(str(request.get("api_key_env") or "OPENAI_API_KEY"))
        or os.environ.get("DEEPSEEK_API_KEY")
        or ""
    ).strip()
    if not api_key:
        raise RuntimeError("api_key is required in payload or environment")

    base_url = str(request.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    model = str(request.get("model") or "gpt-4o-mini")
    messages = request.get("messages") or []
    if not isinstance(messages, list):
        raise RuntimeError("messages must be a list")

    client = OpenAI(api_key=api_key, base_url=base_url)
    options = dict(request.get("options") or {})
    kwargs: dict[str, Any] = {
        "model": model,
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

    response = client.chat.completions.create(**kwargs)
    content = "" if response.choices[0].message.content is None else str(response.choices[0].message.content)
    return {
        "ok": True,
        "backend": "openai-sdk",
        "content": content,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "message": {"role": "assistant", "content": content},
        "raw": response.model_dump() if hasattr(response, "model_dump") else None,
    }


def main() -> int:
    try:
        payload = _read_request()
        if "protocol" in payload and "payload" in payload:
            payload = dict(payload.get("payload") or {})
        result = chat(payload)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
