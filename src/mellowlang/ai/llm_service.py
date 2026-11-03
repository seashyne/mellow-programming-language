"""The hosted-style LLM surface: complete, chat, backends, tensors."""

from __future__ import annotations

import os
from typing import Any, List


from .language_model import _device_plan, _llm_prompt_from_messages, _torch_status
from .llm_api import ai_llm_generate, ai_llm_info
from .state import _LLM_MODELS


def ai_llm_complete(args: List[Any]) -> Any:
    """ai.llm_complete(name, prompt, options?) -> OpenAI-like completion result."""
    result = ai_llm_generate(args)
    if "error" in result:
        return result
    return {
        "model": result["model"],
        "choices": [{"text": result["completion"], "finish_reason": "length"}],
        "usage": {
            "prompt_tokens": len(result["prompt"]),
            "completion_tokens": result["generated_tokens"],
            "total_tokens": len(result["prompt"]) + result["generated_tokens"],
        },
        "text": result["text"],
    }

def ai_llm_chat(args: List[Any]) -> Any:
    """ai.llm_chat(name, messages, options?) -> chat-shaped local generation."""
    if len(args) < 2:
        return {"error": "ai.llm_chat requires model name and messages"}
    name = str(args[0])
    prompt = _llm_prompt_from_messages(args[1])
    options = dict(args[2]) if len(args) > 2 and isinstance(args[2], dict) else {}
    options.setdefault("include_prompt", False)
    generated = ai_llm_generate([name, prompt, options])
    if "error" in generated:
        return generated
    return {
        "model": name,
        "message": {"role": "assistant", "content": generated["completion"]},
        "usage": {
            "prompt_tokens": len(prompt),
            "completion_tokens": generated["generated_tokens"],
            "total_tokens": len(prompt) + generated["generated_tokens"],
        },
    }

def ai_llm_models(args: List[Any]) -> Any:
    """ai.llm_models() -> list registered local LLMs."""
    return [ai_llm_info([name]) for name in sorted(_LLM_MODELS.keys())]

def ai_llm_backends(args: List[Any]) -> Any:
    """ai.llm_backends() -> available local LLM backend capabilities."""
    torch_info = _torch_status()
    cpu_workers = os.cpu_count() or 1
    from .. import llm_native
    native_caps = llm_native.capabilities()
    return [
        {
            "name": "tiny-causal-char-lm",
            "available": True,
            "kind": "statistical-char-lm",
            "devices": ["cpu"],
            "training": True,
            "production": False,
        },
        {
            "name": "mellow-native",
            "available": True,
            "kind": "mellow-owned-transformer-runtime",
            "devices": native_caps.get("devices", ["cpu"]),
            "training": False,
            "inference": bool(native_caps.get("kernels")),
            "production": False,
            "status": "kernels-ready" if native_caps.get("kernels") else "contract-ready",
            "detail": {
                "runtime": "mellow",
                "native_extension": bool(native_caps.get("available")),
                "cpu_workers": cpu_workers,
                "kernels": native_caps.get("kernels", []),
                "planned_kernels": ["matmul", "softmax", "layer_norm", "gelu", "attention", "adamw"],
                "planned_devices": ["cpu", "cuda", "vulkan", "metal"],
                "capabilities": native_caps,
            },
        },
        {
            "name": "transformer-torch",
            "available": bool(torch_info.get("available")),
            "kind": "gpt-transformer",
            "devices": [d["id"] for d in torch_info.get("devices", [])],
            "training": bool(torch_info.get("available")),
            "production": True,
            "detail": torch_info,
        },
    ]

def ai_llm_device_plan(args: List[Any]) -> Any:
    """ai.llm_device_plan(config?) -> CPU/GPU placement plan for transformer backends."""
    config = dict(args[0]) if args and isinstance(args[0], dict) else {}
    backend = str(config.get("backend", "transformer-torch"))
    if backend == "mellow-native":
        from .. import llm_native
        native_caps = llm_native.capabilities()
        workers = max(1, int(config.get("cpu_workers", os.cpu_count() or 1)))
        plan = {
            "requested": config.get("devices", "cpu"),
            "selected": [{"id": "cpu", "type": "cpu", "workers": workers}],
            "strategy": "cpu-threaded" if workers > 1 else "single",
            "torch": _torch_status(),
            "native": native_caps,
        }
    else:
        plan = _device_plan(config)
    plan["backend"] = backend
    plan["multi_device"] = len(plan["selected"]) > 1
    if backend == "mellow-native":
        kernels = set(plan["native"].get("kernels", []))
        required = {"matmul", "softmax", "layer_norm", "gelu"}
        plan["status"] = "kernels-ready" if required <= kernels else "contract-ready"
        plan["next"] = "add attention and optimizer kernels before enabling transformer training"
    else:
        plan["status"] = "ready" if backend != "transformer-torch" or plan["torch"].get("available") else "requires-llm-extra"
    if plan["status"] == "requires-llm-extra":
        plan["install"] = "python -m pip install -e .[llm]"
    return plan

def ai_llm_tensor(args: List[Any]) -> Any:
    """ai.llm_tensor(op, args...) -> run Mellow-native tensor kernels."""
    if not args:
        return {"error": "ai.llm_tensor requires an operation"}
    from .. import llm_native
    op = str(args[0])
    try:
        if op == "matmul":
            if len(args) < 6:
                return {"error": "matmul requires a, b, m, n, k"}
            return {
                "op": op,
                "backend": llm_native.capabilities().get("backend"),
                "values": llm_native.matmul(args[1], args[2], int(args[3]), int(args[4]), int(args[5])),
            }
        if op == "softmax":
            return {"op": op, "backend": llm_native.capabilities().get("backend"), "values": llm_native.softmax(args[1])}
        if op == "gelu":
            return {"op": op, "backend": llm_native.capabilities().get("backend"), "values": llm_native.gelu(args[1])}
        if op == "layer_norm":
            gamma = args[2] if len(args) > 2 else None
            beta = args[3] if len(args) > 3 else None
            eps = float(args[4]) if len(args) > 4 else 1e-5
            return {
                "op": op,
                "backend": llm_native.capabilities().get("backend"),
                "values": llm_native.layer_norm(args[1], gamma, beta, eps),
            }
    except Exception as exc:
        return {"error": f"{op} failed: {exc}"}
    return {"error": f"unknown tensor op: {op}"}

def ai_llm_tensor_batch(args: List[Any]) -> Any:
    """ai.llm_tensor_batch(operations) -> execute multiple kernels in one host call."""
    operations = args[0] if args and isinstance(args[0], list) else []
    from .. import llm_native
    results = llm_native.run_batch(operations)
    return {
        "operations": len(operations),
        "backend": llm_native.capabilities().get("backend"),
        "results": results,
        "errors": sum(1 for result in results if "error" in result),
    }
