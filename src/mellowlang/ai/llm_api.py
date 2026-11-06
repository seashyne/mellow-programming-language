"""std.ai.llm_* model lifecycle syscalls over TinyCausalLM."""

from __future__ import annotations

import json
import os
from typing import Any, List


from .language_model import TinyCausalLM, _llm_dataset_from_texts, _llm_texts
from .state import _LLM_MODELS


def ai_llm_create(args: List[Any]) -> Any:
    """ai.llm_create(name, config?) -> create a tiny local causal LM."""
    name = str(args[0]) if args else "llm"
    config = dict(args[1]) if len(args) > 1 and isinstance(args[1], dict) else {}
    order = int(config.get("order", config.get("context", 3)))
    seed = int(config.get("seed", 42))
    model = TinyCausalLM(name, order=order, seed=seed)
    _LLM_MODELS[name] = model
    return {
        "model": name,
        "kind": "tiny-causal-char-lm",
        "order": model.order,
        "status": "created",
    }

def ai_llm_train(args: List[Any]) -> Any:
    """ai.llm_train(name, texts, options?) -> train from local text."""
    if len(args) < 2:
        return {"error": "ai.llm_train requires model name and text corpus"}
    name = str(args[0])
    if name not in _LLM_MODELS:
        _LLM_MODELS[name] = TinyCausalLM(name)
    raw_texts = args[1]
    if isinstance(raw_texts, dict) and isinstance(raw_texts.get("samples"), list):
        texts = _llm_texts(raw_texts.get("samples"))
    else:
        texts = _llm_texts(raw_texts)
    options = dict(args[2]) if len(args) > 2 and isinstance(args[2], dict) else {}
    epochs = int(options.get("epochs", 1))
    loss = _LLM_MODELS[name].train(texts, epochs=epochs)
    model = _LLM_MODELS[name]
    eval_result = model.evaluate(texts)
    return {
        "model": name,
        "epochs": max(1, epochs),
        "samples": len(texts),
        "tokens": model.trained_tokens,
        "vocab": len(model.vocab),
        "loss": round(loss, 6),
        "perplexity": eval_result["perplexity"],
        "status": "trained",
    }

def ai_llm_generate(args: List[Any]) -> Any:
    """ai.llm_generate(name, prompt?, options?) -> generate text."""
    if not args:
        return {"error": "ai.llm_generate requires model name"}
    name = str(args[0])
    if name not in _LLM_MODELS:
        return {"error": f"LLM model '{name}' not found"}
    prompt = str(args[1]) if len(args) > 1 else ""
    options = dict(args[2]) if len(args) > 2 and isinstance(args[2], dict) else {}
    max_tokens = int(options.get("max_tokens", options.get("tokens", 64)))
    temperature = float(options.get("temperature", 1.0))
    seed = options.get("seed")
    top_k = int(options.get("top_k", 0))
    stop = options.get("stop") if isinstance(options.get("stop"), list) else []
    include_prompt = bool(options.get("include_prompt", True))
    text = _LLM_MODELS[name].generate(
        prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        seed=seed,
        top_k=top_k,
        stop=stop,
    )
    completion = text[len(prompt):] if text.startswith(prompt) else text
    return {
        "model": name,
        "prompt": prompt,
        "text": text if include_prompt else completion,
        "completion": completion,
        "generated_tokens": max(0, len(text) - len(prompt)),
        "options": {
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_k": top_k,
            "include_prompt": include_prompt,
        },
    }

def ai_llm_tokenize(args: List[Any]) -> Any:
    """ai.llm_tokenize(text) -> character token ids for the tiny LM package."""
    text = str(args[0]) if args else ""
    tokens = [ord(ch) for ch in text]
    return {"tokens": tokens, "count": len(tokens), "tokenizer": "unicode-char"}

def ai_llm_info(args: List[Any]) -> Any:
    """ai.llm_info(name?) -> model metadata or all local LLM names."""
    if not args:
        return {"models": list(_LLM_MODELS.keys()), "count": len(_LLM_MODELS)}
    name = str(args[0])
    if name not in _LLM_MODELS:
        return {"error": f"LLM model '{name}' not found"}
    model = _LLM_MODELS[name]
    return {
        "name": model.name,
        "kind": "tiny-causal-char-lm",
        "order": model.order,
        "vocab": len(model.vocab),
        "tokens": model.trained_tokens,
        "loss_points": len(model.loss_history),
        "loss": model.loss_history[-1] if model.loss_history else None,
        "created_at": model.created_at,
        "trained": model.trained_tokens > 0,
        "capabilities": ["train", "generate", "evaluate", "checkpoint", "chat-format"],
    }

def ai_llm_dataset(args: List[Any]) -> Any:
    """ai.llm_dataset(texts, options?) -> normalize text into training chunks."""
    if not args:
        return {"samples": [], "count": 0, "chars": 0}
    options = dict(args[1]) if len(args) > 1 and isinstance(args[1], dict) else {}
    return _llm_dataset_from_texts(_llm_texts(args[0]), options)

def ai_llm_eval(args: List[Any]) -> Any:
    """ai.llm_eval(name, texts) -> loss/perplexity metrics."""
    if len(args) < 2:
        return {"error": "ai.llm_eval requires model name and eval texts"}
    name = str(args[0])
    if name not in _LLM_MODELS:
        return {"error": f"LLM model '{name}' not found"}
    raw_texts = args[1]
    texts = _llm_texts(raw_texts.get("samples")) if isinstance(raw_texts, dict) else _llm_texts(raw_texts)
    result = _LLM_MODELS[name].evaluate(texts)
    result["model"] = name
    return result

def ai_llm_save(args: List[Any]) -> Any:
    """ai.llm_save(name, path) -> save a tiny LM checkpoint under mellow_models."""
    if len(args) < 2:
        return {"error": "ai.llm_save requires model name and path"}
    name = str(args[0])
    if name not in _LLM_MODELS:
        return {"error": f"LLM model '{name}' not found"}
    path = str(args[1])
    safe_dir = "mellow_models"
    os.makedirs(safe_dir, exist_ok=True)
    filename = os.path.join(safe_dir, os.path.basename(path.rstrip("/\\")))
    if not filename.endswith(".mllm"):
        filename += ".mllm"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(_LLM_MODELS[name].to_dict(), f, indent=2, ensure_ascii=False)
    return {"saved": filename, "model": name}

def ai_llm_load(args: List[Any]) -> Any:
    """ai.llm_load(path) -> load a tiny LM checkpoint from mellow_models."""
    if not args:
        return {"error": "ai.llm_load requires path"}
    path = str(args[0])
    safe_dir = "mellow_models"
    filename = os.path.join(safe_dir, os.path.basename(path.rstrip("/\\")))
    if not filename.endswith(".mllm"):
        filename += ".mllm"
    if not os.path.isfile(filename):
        return {"error": f"LLM file not found: {filename}"}
    with open(filename, "r", encoding="utf-8") as f:
        model = TinyCausalLM.from_dict(json.load(f))
    _LLM_MODELS[model.name] = model
    return {"loaded": model.name, "kind": "tiny-causal-char-lm", "tokens": model.trained_tokens}
