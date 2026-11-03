"""std.ai model, training, embedding, chat, and decide syscalls."""

from __future__ import annotations

import json
import math
import os
import random
from typing import Any, List


from .network import MellowModel, _parse_layer_spec
from .state import _MODELS


def ai_model_create(args: List[Any]) -> Any:
    """
    ai.model_create(name, layers_list, task?)
    layers_list: list of dicts [{in:N, out:M, activation:"relu"}, ...]
    """
    name = str(args[0]) if args else "model"
    raw_layers = args[1] if len(args) > 1 else [{"in": 2, "out": 2}]
    task = str(args[2]) if len(args) > 2 else "classify"

    if not isinstance(raw_layers, list):
        raw_layers = [{"in": 2, "out": 2}]

    layers = [_parse_layer_spec(s) for s in raw_layers]
    m = MellowModel(name, layers, task)
    _MODELS[name] = m
    return {"model": name, "layers": len(layers), "task": task, "status": "created"}

def ai_train(args: List[Any]) -> Any:
    """
    ai.train(model_name, data, labels, epochs?, lr?)
    data: list of input lists  [[1,0],[0,1],...]
    labels: list of class indices or floats
    """
    if len(args) < 3:
        return {"error": "ai.train requires model_name, data, labels"}
    model_name = str(args[0])
    data = args[1]
    labels = args[2]
    epochs = int(args[3]) if len(args) > 3 else 10
    lr = float(args[4]) if len(args) > 4 else 0.01

    if model_name not in _MODELS:
        return {"error": f"Model '{model_name}' not found. Create it first with ai.model_create()"}

    m = _MODELS[model_name]
    if not isinstance(data, list) or not isinstance(labels, list):
        return {"error": "data and labels must be lists"}

    total_loss = 0.0
    n = len(data)
    for ep in range(max(1, epochs)):
        ep_loss = 0.0
        indices = list(range(n))
        random.shuffle(indices)
        for i in indices:
            x = [float(v) for v in (data[i] if isinstance(data[i], list) else [data[i]])]
            y = labels[i]
            ep_loss += m.train_step(x, y, lr)
        avg = ep_loss / max(n, 1)
        m.loss_history.append(round(avg, 6))
        total_loss = avg

    m.trained = True
    return {
        "model": model_name,
        "epochs": epochs,
        "samples": n,
        "final_loss": round(total_loss, 6),
        "status": "trained"
    }

def ai_predict(args: List[Any]) -> Any:
    """
    ai.predict(model_name, input_list)
    """
    if len(args) < 2:
        return {"error": "ai.predict requires model_name and input"}
    model_name = str(args[0])
    x_raw = args[1]
    if model_name not in _MODELS:
        return {"error": f"Model '{model_name}' not found"}
    m = _MODELS[model_name]
    x = [float(v) for v in (x_raw if isinstance(x_raw, list) else [x_raw])]
    result = m.predict(x)
    proba = m.predict_proba(x)
    return {
        "model": model_name,
        "input": x,
        "prediction": result,
        "probabilities": [round(p, 4) for p in proba],
    }

def ai_model_save(args: List[Any]) -> Any:
    """ai.model_save(model_name, path)"""
    if len(args) < 2:
        return {"error": "ai.model_save requires model_name and path"}
    model_name = str(args[0])
    path = str(args[1])
    if model_name not in _MODELS:
        return {"error": f"Model '{model_name}' not found"}
    m = _MODELS[model_name]
    # Safety: only allow relative paths within mellow_models/
    safe_dir = "mellow_models"
    os.makedirs(safe_dir, exist_ok=True)
    filename = os.path.join(safe_dir, os.path.basename(path.rstrip("/\\")))
    if not filename.endswith(".mmodel"):
        filename += ".mmodel"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(m.to_dict(), f, indent=2)
    return {"saved": filename, "model": model_name}

def ai_model_load(args: List[Any]) -> Any:
    """ai.model_load(path)  -> loads model into registry, returns model_name"""
    if not args:
        return {"error": "ai.model_load requires path"}
    path = str(args[0])
    safe_dir = "mellow_models"
    filename = os.path.join(safe_dir, os.path.basename(path.rstrip("/\\")))
    if not filename.endswith(".mmodel"):
        filename += ".mmodel"
    if not os.path.isfile(filename):
        return {"error": f"Model file not found: {filename}"}
    with open(filename, "r", encoding="utf-8") as f:
        d = json.load(f)
    m = MellowModel.from_dict(d)
    _MODELS[m.name] = m
    return {"loaded": m.name, "layers": len(m.layers), "task": m.task}

def ai_embed(args: List[Any]) -> Any:
    """
    ai.embed(text)  ->  simple character-frequency embedding (64-dim, offline)
    This is a deterministic offline embedding — good enough for basic NLP demos.
    """
    text = str(args[0]) if args else ""
    dim = 64
    vec = [0.0] * dim
    for i, ch in enumerate(text):
        idx = ord(ch) % dim
        vec[idx] += 1.0 / max(len(text), 1)
        # positional component
        vec[(idx + i) % dim] += 0.5 / max(len(text), 1)
    # L2 normalize
    mag = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / mag, 6) for v in vec]

def ai_chat(args: List[Any]) -> Any:
    """
    ai.chat(prompt, model_name?, system?)
    Offline rule-based chat engine (sandbox-safe, no network).
    Provides meaningful responses using pattern matching + templates.
    """
    prompt = str(args[0]) if args else ""
    model_name = str(args[1]) if len(args) > 1 else "_chat_default"
    system = str(args[2]) if len(args) > 2 else "You are a helpful assistant."

    low = prompt.lower().strip()

    # Pattern-based response system
    responses = {
        ("hello", "hi", "hey", "สวัสดี"): [
            "Hello! How can I help you today?",
            "Hi there! What can I do for you?",
            "Hey! Ready to assist.",
        ],
        ("bye", "goodbye", "ลาก่อน"): [
            "Goodbye! Have a great time!",
            "See you later!",
            "Farewell! Come back anytime.",
        ],
        ("how are you", "how do you do", "เป็นยังไงบ้าง"): [
            "I'm doing great, thanks for asking!",
            "All systems running smoothly!",
            "Feeling helpful as always!",
        ],
        ("what is your name", "who are you", "ชื่ออะไร"): [
            "I'm MellowAI, built into MellowLang v1.4.8.",
            "My name is MellowAI — your in-language AI assistant.",
        ],
        ("help", "what can you do", "ช่วยอะไรได้", "ทำอะไรได้"): [
            "I can chat, answer questions, and I'm part of MellowLang's AI module.\n"
            "You can also train custom models, make predictions, and more!",
        ],
        ("mellow", "mellowlang"): [
            "MellowLang is a sandboxed scripting language with built-in AI, game, and math modules.",
            "MellowLang v1.4.8 introduces full AI capabilities via the `ai` module!",
        ],
        ("train", "training", "เทรน"): [
            "To train a model: ai.model_create(name, layers), then ai.train(name, data, labels).",
        ],
        ("predict", "prediction", "พยากรณ์"): [
            "Use ai.predict(model_name, input) to get predictions from a trained model.",
        ],
    }

    matched = None
    for patterns, replies in responses.items():
        if any(p in low for p in patterns):
            matched = random.choice(replies)
            break

    if matched is None:
        # Generic contextual response
        words = prompt.split()
        if len(words) <= 2:
            matched = f"I see you said '{prompt}'. Could you tell me more?"
        elif "?" in prompt:
            matched = f"That's a great question about '{' '.join(words[:3])}...' Let me think — as MellowAI I'd suggest exploring the docs or running more experiments!"
        else:
            matched = (
                f"Interesting point about '{' '.join(words[:4])}...'. "
                "MellowAI is learning from your input. For deeper AI, use ai.train() with your own data!"
            )

    # Store in model memory if model exists
    if model_name not in _MODELS:
        # Create a lightweight chat model
        chat_model = MellowModel(model_name, [], "chat")
        _MODELS[model_name] = chat_model

    chat_model = _MODELS[model_name]
    chat_model._chat_memory.append({"user": prompt, "assistant": matched})

    return {
        "response": matched,
        "model": model_name,
        "memory_size": len(chat_model._chat_memory),
    }

def ai_decide(args: List[Any]) -> Any:
    """Existing game AI decide — delegates to existing implementation."""
    # This is already in game AI; kept here for completeness
    if not args:
        return None
    choices = args[0] if isinstance(args[0], list) else list(args)
    if not choices:
        return None
    return random.choice(choices) if isinstance(choices[0], str) else choices[0]

def ai_loss_history(args: List[Any]) -> Any:
    """ai.loss_history(model_name) -> list of loss values"""
    model_name = str(args[0]) if args else ""
    if model_name not in _MODELS:
        return []
    return _MODELS[model_name].loss_history

def ai_model_info(args: List[Any]) -> Any:
    """ai.model_info(model_name) -> info dict"""
    model_name = str(args[0]) if args else ""
    if model_name not in _MODELS:
        return {"error": f"Model '{model_name}' not found"}
    m = _MODELS[model_name]
    return {
        "name": m.name,
        "task": m.task,
        "trained": m.trained,
        "layers": len(m.layers),
        "layer_shapes": [{"out": len(la.W), "in": len(la.W[0]) if la.W else 0} for la in m.layers],
        "loss_points": len(m.loss_history),
        "chat_memory": len(m._chat_memory),
    }

def ai_models_list(args: List[Any]) -> Any:
    """ai.models_list() -> list of model names"""
    return list(_MODELS.keys())
