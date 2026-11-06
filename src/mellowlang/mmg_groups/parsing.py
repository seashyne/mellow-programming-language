"""The call syntax: the three regexes that find draw calls and keep
bindings, and the argument splitter, value parser and command builder
they share."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


APP_RE = re.compile(r'mmg\.app\((.*?)\)', re.DOTALL)
CALL_RE = re.compile(
    r'mmg\.(clear|rect|circle|line|text|scene|camera|texture|sprite|on|frame)\((.*?)\)',
    re.DOTALL,
)
KEEP_RE = re.compile(r'^\s*keep\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$', re.MULTILINE)


def _split_args(raw: str) -> List[str]:
    parts: List[str] = []
    cur: List[str] = []
    depth = 0
    in_str = False
    quote = ''
    esc = False
    for ch in raw:
        if in_str:
            cur.append(ch)
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == quote:
                in_str = False
            continue
        if ch in ('"', "'"):
            in_str = True
            quote = ch
            cur.append(ch)
            continue
        if ch in '([{':
            depth += 1
            cur.append(ch)
            continue
        if ch in ')]}':
            depth = max(0, depth - 1)
            cur.append(ch)
            continue
        if ch == ',' and depth == 0:
            parts.append(''.join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    if cur:
        parts.append(''.join(cur).strip())
    return [p for p in parts if p]


def _parse_value(token: str, env: Dict[str, Any] | None = None) -> Any:
    token = token.strip()
    if not token:
        return None
    env = env or {}
    if token[0] in ('"', "'") and token[-1] == token[0]:
        return token[1:-1]
    low = token.lower()
    if low == 'true':
        return True
    if low == 'false':
        return False
    if low == 'null':
        return None
    if token.startswith('[') and token.endswith(']'):
        inner = token[1:-1].strip()
        if not inner:
            return []
        return [_parse_value(p, env) for p in _split_args(inner)]
    if token.startswith('{') and token.endswith('}'):
        inner = token[1:-1].strip()
        if not inner:
            return {}
        out: Dict[str, Any] = {}
        for part in _split_args(inner):
            if ':' not in part:
                continue
            k, v = part.split(':', 1)
            out[str(_parse_value(k, env))] = _parse_value(v, env)
        return out
    if re.fullmatch(r'-?\d+', token):
        return int(token)
    if re.fullmatch(r'-?\d+\.\d+', token):
        return float(token)
    if token in env:
        return env[token]
    return token


def _extract_named_and_positional(args: List[str], env: Dict[str, Any] | None = None) -> Tuple[list[Any], dict[str, Any]]:
    positional: list[Any] = []
    named: dict[str, Any] = {}
    for arg in args:
        stripped = arg.strip()
        is_quoted = len(stripped) >= 2 and stripped[0] in ('"', "'") and stripped[-1] == stripped[0]
        if (not is_quoted) and re.match(r'^[A-Za-z_][A-Za-z0-9_]*\s*:', stripped):
            k, v = stripped.split(':', 1)
            named[k.strip()] = _parse_value(v, env)
        else:
            positional.append(_parse_value(stripped, env))
    return positional, named


def _scan_keep_env(source: str) -> Dict[str, Any]:
    env: Dict[str, Any] = {}
    for name, raw in KEEP_RE.findall(source):
        try:
            env[name] = _parse_value(raw, env)
        except Exception:
            env[name] = raw.strip()
    return env


def _action_expr_to_command(expr: Any) -> Dict[str, Any]:
    if isinstance(expr, str):
        expr = expr.strip()
        if not expr:
            return {'type': 'noop'}
        if expr == 'close':
            return {'type': 'close'}
        if expr.startswith('print:'):
            return {'type': 'print', 'message': expr.split(':', 1)[1]}
        if expr.startswith('set:') and '=' in expr:
            payload = expr.split(':', 1)[1]
            key, value = payload.split('=', 1)
            return {'type': 'set', 'key': key.strip(), 'value': _parse_value(value)}
        if expr.startswith('inc:'):
            return {'type': 'inc', 'key': expr.split(':', 1)[1].strip(), 'delta': 1}
        if expr.startswith('toggle:'):
            return {'type': 'toggle', 'key': expr.split(':', 1)[1].strip()}
    return {'type': 'script', 'value': expr}
