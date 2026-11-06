"""Mutable AI registries shared by every ai.* module."""

from __future__ import annotations

from typing import Any, Dict


from .language_model import TinyCausalLM
from .network import MellowModel


_MODELS: Dict[str, MellowModel] = {}

_LLM_MODELS: Dict[str, TinyCausalLM] = {}

_SESSIONS: Dict[str, Dict[str, Any]] = {}

_RUNTIME_STATE: Dict[str, Any] = {
    "booted": False,
    "boot_count": 0,
    "last_boot_at": None,
}

# ── v1.5.1: Unified AI API layer ───────────────────────────────────────────
_API_CONFIG: Dict[str, Dict[str, Any]] = {
    "offline": {"mode": "offline", "max_context": 16, "status": "ready"},
    "local-rag": {"mode": "offline", "max_context": 8, "status": "ready"},
}
