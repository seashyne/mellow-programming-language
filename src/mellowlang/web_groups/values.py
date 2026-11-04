"""Scalar conversions shared by the parser and the emitter: quoted
literals, JSX expressions, style sizes and state setter names."""

from __future__ import annotations

import json
import re


def _tsx_expr(value: str) -> str:
    value = value.strip()
    if _is_quoted(value):
        return json.dumps(_unquote(value))
    return value


def _style_size(value: str) -> str:
    value = value.strip()
    if re.match(r"^-?\d+(\.\d+)?$", value):
        return f"{value}"
    return _tsx_expr(value)


def _setter_name(name: str) -> str:
    return "set" + name[:1].upper() + name[1:]


def _is_quoted(value: str) -> bool:
    return len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}


def _unquote(value: str) -> str:
    if not _is_quoted(value):
        return value
    return json.loads(value) if value[0] == '"' else value[1:-1]
