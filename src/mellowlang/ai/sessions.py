"""AI runtime boot, sessions, prompt templates, and retrieval."""

from __future__ import annotations

import time
from typing import Any, List


from .models import ai_chat, ai_embed
from .numerics import _cosine
from .state import _MODELS, _RUNTIME_STATE, _SESSIONS


def _session_id(name: str) -> str:
    safe = ''.join(ch if ch.isalnum() or ch in ('_', '-') else '_' for ch in name).strip('_') or 'session'
    return f"{safe}_{len(_SESSIONS) + 1}"

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
