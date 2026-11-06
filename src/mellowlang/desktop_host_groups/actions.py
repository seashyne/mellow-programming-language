"""The action vocabulary a widget or menu item can carry, and `{{state.x}}`
interpolation for labels."""

from __future__ import annotations

import re
from typing import Any, Dict

from .parsing import _parse_value


def _interpolate(text: str, state: Dict[str, Any]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        return str(state.get(key, ''))
    return re.sub(r'\{\{\s*state\.(\w+)\s*\}\}', repl, str(text))


def _apply_action(action: str, *, root: Any, state: Dict[str, Any], refresh: Any) -> None:
    action = str(action or '').strip()
    if not action:
        return
    low = action.lower()
    if low in ('close', 'quit', 'exit'):
        root.destroy()
        return
    if low.startswith('print:'):
        print(action.split(':', 1)[1])
        return
    if low.startswith('set:') and '=' in action:
        payload = action.split(':', 1)[1]
        key, value = payload.split('=', 1)
        state[key.strip()] = _parse_value(value.strip())
        refresh()
        return
    if low.startswith('inc:'):
        key = action.split(':', 1)[1].strip()
        state[key] = int(state.get(key, 0) or 0) + 1
        refresh()
        return
    if low.startswith('toggle:'):
        key = action.split(':', 1)[1].strip()
        state[key] = not bool(state.get(key, False))
        refresh()
        return
    print(action)
