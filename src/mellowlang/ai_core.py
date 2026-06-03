# mellowlang/ai_core.py  — v1.4.8
# Full AI capabilities: chat, train, model create/save/load, predict, embed
# Pure-Python, sandboxed. No network required (offline-first).
from __future__ import annotations

import json
import math
import os
import random
import struct
import time
from typing import Any, Dict, List, Optional

# ── helpers ──────────────────────────────────────────────────────────────────

def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-500, min(500, x))))

def _relu(x: float) -> float:
    return max(0.0, x)

def _softmax(xs: List[float]) -> List[float]:
    m = max(xs)
    exps = [math.exp(v - m) for v in xs]
    s = sum(exps)
    return [v / s for v in exps]

def _dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))

def _matmul(mat: List[List[float]], vec: List[float]) -> List[float]:
    return [_dot(row, vec) for row in mat]

def _add_vec(a: List[float], b: List[float]) -> List[float]:
    return [x + y for x, y in zip(a, b)]

def _scale_vec(a: List[float], s: float) -> List[float]:
    return [x * s for x in a]

# ── Simple Feed-Forward Neural Network ───────────────────────────────────────

class _Layer:
    def __init__(self, in_size: int, out_size: int, activation: str = "relu"):
        std = math.sqrt(2.0 / in_size)
        rng = random.Random(42)
        self.W = [[rng.gauss(0, std) for _ in range(in_size)] for _ in range(out_size)]
        self.b = [0.0] * out_size
        self.activation = activation
        # cache for backprop
        self._in: List[float] = []
        self._z: List[float] = []
        self._out: List[float] = []

    def forward(self, x: List[float]) -> List[float]:
        self._in = x
        z = _add_vec(_matmul(self.W, x), self.b)
        self._z = z
        if self.activation == "sigmoid":
            out = [_sigmoid(v) for v in z]
        elif self.activation == "softmax":
            out = _softmax(z)
        elif self.activation == "linear":
            out = list(z)
        else:  # relu
            out = [_relu(v) for v in z]
        self._out = out
        return out

    def backward(self, grad_out: List[float], lr: float) -> List[float]:
        n_out = len(grad_out)
        n_in = len(self._in)
        # activation gradient
        if self.activation == "sigmoid":
            act_grad = [self._out[i] * (1 - self._out[i]) * grad_out[i] for i in range(n_out)]
        elif self.activation == "relu":
            act_grad = [grad_out[i] if self._z[i] > 0 else 0.0 for i in range(n_out)]
        elif self.activation in ("softmax", "linear"):
            act_grad = list(grad_out)
        else:
            act_grad = list(grad_out)

        # weight/bias update
        for i in range(n_out):
            self.b[i] -= lr * act_grad[i]
            for j in range(n_in):
                self.W[i][j] -= lr * act_grad[i] * self._in[j]

        # gradient w.r.t. input
        grad_in = [0.0] * n_in
        for j in range(n_in):
            for i in range(n_out):
                grad_in[j] += self.W[i][j] * act_grad[i]
        return grad_in

    def to_dict(self) -> dict:
        return {"W": self.W, "b": self.b, "activation": self.activation}

    @classmethod
    def from_dict(cls, d: dict) -> "_Layer":
        out_size = len(d["W"])
        in_size = len(d["W"][0]) if out_size else 0
        obj = cls.__new__(cls)
        obj.W = d["W"]
        obj.b = d["b"]
        obj.activation = d.get("activation", "relu")
        obj._in = []
        obj._z = []
        obj._out = []
        return obj


class MellowModel:
    """Lightweight sandboxed neural network model."""

    def __init__(self, name: str, layers: List[_Layer], task: str = "classify"):
        self.name = name
        self.layers = layers
        self.task = task  # "classify" | "regress"
        self.trained = False
        self.loss_history: List[float] = []
        self._chat_memory: List[Dict] = []

    # ── forward ──
    def predict(self, x: List[float]) -> Any:
        out = list(x)
        for layer in self.layers:
            out = layer.forward(out)
        if self.task == "classify":
            return int(out.index(max(out)))
        return out[0] if len(out) == 1 else out

    def predict_proba(self, x: List[float]) -> List[float]:
        out = list(x)
        for layer in self.layers:
            out = layer.forward(out)
        return out

    # ── training ──
    def train_step(self, x: List[float], y: Any, lr: float = 0.01) -> float:
        # forward
        out = self.predict_proba(x)
        # loss + output grad
        if self.task == "classify":
            n_classes = len(out)
            target = int(y)
            # cross-entropy loss with softmax output
            loss = -math.log(max(out[target], 1e-9))
            grad = list(out)
            grad[target] -= 1.0
        else:
            target_val = float(y)
            diff = out[0] - target_val
            loss = 0.5 * diff * diff
            grad = [diff]
        # backward
        g = grad
        for layer in reversed(self.layers):
            g = layer.backward(g, lr)
        return loss

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "task": self.task,
            "trained": self.trained,
            "loss_history": self.loss_history[-20:],
            "layers": [la.to_dict() for la in self.layers],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MellowModel":
        layers = [_Layer.from_dict(ld) for ld in d.get("layers", [])]
        obj = cls(d["name"], layers, d.get("task", "classify"))
        obj.trained = d.get("trained", False)
        obj.loss_history = d.get("loss_history", [])
        obj._chat_memory = []
        return obj


# ── Module registry (called by host functions) ──────────────────────────────

_MODELS: Dict[str, MellowModel] = {}

def _parse_layer_spec(spec: Any) -> _Layer:
    """Parse a layer spec dict or tuple [in, out, activation]."""
    if isinstance(spec, dict):
        in_s = int(spec.get("in", spec.get("input", 2)))
        out_s = int(spec.get("out", spec.get("output", 2)))
        act = str(spec.get("activation", "relu"))
        return _Layer(in_s, out_s, act)
    elif isinstance(spec, (list, tuple)) and len(spec) >= 2:
        return _Layer(int(spec[0]), int(spec[1]), str(spec[2]) if len(spec) > 2 else "relu")
    return _Layer(2, 2, "relu")


# ── Public AI functions (called from host registry) ─────────────────────────

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




# ── AI Runtime Layer (sessions, prompt templating, retrieval) ────────────────

_SESSIONS: Dict[str, Dict[str, Any]] = {}
_RUNTIME_STATE: Dict[str, Any] = {
    "booted": False,
    "boot_count": 0,
    "last_boot_at": None,
}


def _session_id(name: str) -> str:
    safe = ''.join(ch if ch.isalnum() or ch in ('_', '-') else '_' for ch in name).strip('_') or 'session'
    return f"{safe}_{len(_SESSIONS) + 1}"


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    aa = a[:n]
    bb = b[:n]
    dot = sum(x * y for x, y in zip(aa, bb))
    ma = math.sqrt(sum(x * x for x in aa)) or 1.0
    mb = math.sqrt(sum(y * y for y in bb)) or 1.0
    return dot / (ma * mb)


def ai_runtime_boot(args: List[Any]) -> Any:
    """ai.runtime_boot(config?) -> runtime state"""
    config = args[0] if args and isinstance(args[0], dict) else {}
    _RUNTIME_STATE["booted"] = True
    _RUNTIME_STATE["boot_count"] += 1
    _RUNTIME_STATE["last_boot_at"] = int(time.time())
    return {
        "status": "ready",
        "booted": True,
        "boot_count": _RUNTIME_STATE["boot_count"],
        "features": [
            "chat", "train", "predict", "embed",
            "sessions", "retrieval", "prompt_template"
        ],
        "config": config,
    }


def ai_runtime_info(args: List[Any]) -> Any:
    """ai.runtime_info() -> state summary"""
    return {
        "booted": bool(_RUNTIME_STATE["booted"]),
        "boot_count": int(_RUNTIME_STATE["boot_count"]),
        "last_boot_at": _RUNTIME_STATE["last_boot_at"],
        "models": len(_MODELS),
        "sessions": len(_SESSIONS),
        "features": [
            "offline", "sandboxed", "chat", "ml", "embedding", "retrieval"
        ],
    }


def ai_session_open(args: List[Any]) -> Any:
    """ai.session_open(name?, system?) -> session metadata"""
    name = str(args[0]) if args else "default"
    system = str(args[1]) if len(args) > 1 else "You are a helpful offline assistant."
    sid = _session_id(name)
    _SESSIONS[sid] = {
        "id": sid,
        "name": name,
        "system": system,
        "messages": [],
        "created_at": int(time.time()),
    }
    return {"session": sid, "name": name, "system": system, "status": "opened"}


def ai_session_message(args: List[Any]) -> Any:
    """ai.session_message(session_id, prompt) -> chat response with session memory"""
    if len(args) < 2:
        return {"error": "ai.session_message requires session_id and prompt"}
    sid = str(args[0])
    prompt = str(args[1])
    if sid not in _SESSIONS:
        return {"error": f"Session '{sid}' not found"}
    session = _SESSIONS[sid]
    hist = session["messages"][-4:]
    history_text = " ".join(f"user:{m['user']} assistant:{m['assistant']}" for m in hist)
    merged = prompt if not history_text else f"{history_text} user:{prompt}"
    result = ai_chat([merged, sid, session["system"]])
    session["messages"].append({
        "user": prompt,
        "assistant": result.get("response", ""),
        "at": int(time.time()),
    })
    return {
        "session": sid,
        "response": result.get("response", ""),
        "messages": len(session["messages"]),
    }


def ai_session_history(args: List[Any]) -> Any:
    """ai.session_history(session_id) -> list"""
    sid = str(args[0]) if args else ""
    if sid not in _SESSIONS:
        return []
    return list(_SESSIONS[sid]["messages"])


def ai_prompt_template(args: List[Any]) -> Any:
    """ai.prompt_template(template, vars) -> rendered prompt string"""
    if len(args) < 2:
        return {"error": "ai.prompt_template requires template and vars map"}
    template = str(args[0])
    vars_map = args[1] if isinstance(args[1], dict) else {}
    out = template
    for key, value in vars_map.items():
        out = out.replace('{{' + str(key) + '}}', str(value))
    return out


def ai_vector_search(args: List[Any]) -> Any:
    """ai.vector_search(query, docs, top_k?) -> ranked docs by embedding similarity"""
    if len(args) < 2:
        return {"error": "ai.vector_search requires query and docs"}
    query = str(args[0])
    docs = args[1] if isinstance(args[1], list) else []
    top_k = int(args[2]) if len(args) > 2 else 3
    qv = ai_embed([query])
    ranked = []
    for i, doc in enumerate(docs):
        text = str(doc)
        dv = ai_embed([text])
        ranked.append({
            "index": i,
            "text": text,
            "score": round(_cosine(qv, dv), 6),
        })
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:max(1, top_k)]


def ai_rag_answer(args: List[Any]) -> Any:
    """ai.rag_answer(query, docs, top_k?) -> offline retrieval-based answer"""
    if len(args) < 2:
        return {"error": "ai.rag_answer requires query and docs"}
    query = str(args[0])
    docs = args[1] if isinstance(args[1], list) else []
    top_k = int(args[2]) if len(args) > 2 else 2
    matches = ai_vector_search([query, docs, top_k])
    context = ' | '.join(m["text"][:180] for m in matches)
    answer = (
        f"Offline RAG summary for '{query}': "
        f"best matches suggest {context}"
    ) if matches else f"No relevant context found for '{query}'."
    return {
        "query": query,
        "matches": matches,
        "answer": answer,
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


# ── register into host registry ─────────────────────────────────────────────

def register_ai_functions(registry: Any) -> None:
    """Register all AI host functions into a HostRegistry."""
    from .host.legacy import HostFunction

    funcs = [
        HostFunction("std.ai.model_create",  ai_model_create,  cost=5,  min_args=1, max_args=3),
        HostFunction("std.ai.train",         ai_train,          cost=50, min_args=3, max_args=5),
        HostFunction("std.ai.predict",       ai_predict,        cost=5,  min_args=2, max_args=2),
        HostFunction("std.ai.model_save",    ai_model_save,     cost=10, min_args=2, max_args=2),
        HostFunction("std.ai.model_load",    ai_model_load,     cost=10, min_args=1, max_args=1),
        HostFunction("std.ai.embed",         ai_embed,          cost=5,  min_args=1, max_args=1),
        HostFunction("std.ai.chat",          ai_chat,           cost=10, min_args=1, max_args=3),
        HostFunction("std.ai.runtime_boot",  ai_runtime_boot,   cost=2,  min_args=0, max_args=1),
        HostFunction("std.ai.runtime_info",  ai_runtime_info,   cost=1,  min_args=0, max_args=0),
        HostFunction("std.ai.session_open",  ai_session_open,   cost=2,  min_args=0, max_args=2),
        HostFunction("std.ai.session_message", ai_session_message, cost=5, min_args=2, max_args=2),
        HostFunction("std.ai.session_history", ai_session_history, cost=1, min_args=1, max_args=1),
        HostFunction("std.ai.prompt_template", ai_prompt_template, cost=1, min_args=2, max_args=2),
        HostFunction("std.ai.vector_search", ai_vector_search,  cost=3,  min_args=2, max_args=3),
        HostFunction("std.ai.rag_answer",    ai_rag_answer,     cost=5,  min_args=2, max_args=3),
        HostFunction("std.ai.loss_history",  ai_loss_history,   cost=1,  min_args=1, max_args=1),
        HostFunction("std.ai.model_info",    ai_model_info,     cost=1,  min_args=1, max_args=1),
        HostFunction("std.ai.models_list",   ai_models_list,    cost=1,  min_args=0, max_args=0),
        HostFunction("std.ai.api_providers", ai_api_providers,  cost=1,  min_args=0, max_args=0),
        HostFunction("std.ai.api_configure", ai_api_configure,  cost=1,  min_args=1, max_args=2),
        HostFunction("std.ai.api_complete",  ai_api_complete,   cost=2,  min_args=1, max_args=3),
        HostFunction("std.ai.api_embed",     ai_api_embed,      cost=1,  min_args=1, max_args=2),
    ]
    for fn in funcs:
        registry.register(fn)


# ── v1.5.1: Unified AI API layer ───────────────────────────────────────────
_API_CONFIG: Dict[str, Dict[str, Any]] = {
    "offline": {"mode": "offline", "max_context": 16, "status": "ready"},
    "local-rag": {"mode": "offline", "max_context": 8, "status": "ready"},
}


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
