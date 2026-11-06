"""Raised when an AST node has no lowering in the IR pipeline."""

from __future__ import annotations


class UnsupportedLoweringError(RuntimeError):
    pass
