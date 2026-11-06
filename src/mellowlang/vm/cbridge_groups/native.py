"""The native extension's vocabulary: the error types, the run result and
the loader for the C extension."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class CVMUnsupportedOpcode(RuntimeError):
    pass


@dataclass(frozen=True)
class NativeRunResult:
    result: Any
    engine: str
    used_fallback: bool
    detail: str
    native_available: bool


class NativeExecutionRequiredError(RuntimeError):
    pass


def _load_ext():
    """Try to load the native C extension. Returns None if unavailable."""
    try:
        from ... import _mellowvm  # type: ignore
        return _mellowvm
    except Exception:
        return None
