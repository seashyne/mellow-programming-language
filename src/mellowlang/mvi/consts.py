"""The constant pool: intern a value once under its JSON key, read a Python value as a tagged
   constant, and turn a source position into a span tuple."""

from __future__ import annotations

import json
from typing import Any
from ..compiler.compiler import CompiledProgram


def _add_const(const_pool: list[dict[str, Any]], const_index: dict[str, int], spec: dict[str, Any]) -> int:
    key = json.dumps(spec, sort_keys=True, ensure_ascii=False)
    if key in const_index:
        return const_index[key]
    idx = len(const_pool)
    const_pool.append(spec)
    const_index[key] = idx
    return idx


def _const_from_python(value: Any) -> dict[str, Any]:
    if value is None:
        return {'tag': 'none'}
    if isinstance(value, bool):
        return {'tag': 'bool', 'value': bool(value)}
    if isinstance(value, int) and not isinstance(value, bool):
        return {'tag': 'i64', 'value': int(value)}
    if isinstance(value, float):
        return {'tag': 'f64', 'value': float(value)}
    if isinstance(value, str):
        return {'tag': 'str', 'value': value}
    raise ValueError(f'Unsupported Python constant for standalone image: {value!r}')


def _span_tuple(span_map: list[dict[str, Any]], pc: int, compiled: CompiledProgram) -> tuple[int, int, int, int]:
    if pc < len(span_map):
        s = span_map[pc] or {}
        return (
            int(s.get('start_line', 0) or 0),
            int(s.get('start_col', 1) or 1),
            int(s.get('end_line', s.get('start_line', 0) or 0) or 0),
            int(s.get('end_col', s.get('start_col', 1) or 1) or 1),
        )
    line = int((compiled.line_map or [0])[pc]) if compiled.line_map and pc < len(compiled.line_map) else 0
    col = int((compiled.col_map or [1])[pc]) if compiled.col_map and pc < len(compiled.col_map) else 1
    return (line, col, line, col)
