"""Parse Mellow window source into a spec: the widget and state patterns,
argument splitting, value coercion and `parse_window_spec` itself."""

from __future__ import annotations

import re
from typing import Any, Dict, List


WINDOW_RE = re.compile(r'win\.window\((.*?)\)', re.DOTALL)
CALL_RE = re.compile(r'win\.(label|button|input|textarea|checkbox|select|spacer|vstack|hstack|grid|menu|menu_item|slider|listbox)\((.*?)\)', re.DOTALL)
STATE_RE = re.compile(r'keep\s+(\w+)\s*=\s*(.+?)(?:\n|$)')


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


def _parse_value(token: str) -> Any:
    token = token.strip()
    if not token:
        return None
    if token[0] in ('"', "'") and token[-1] == token[0]:
        return token[1:-1]
    low = token.lower()
    if low == 'true':
        return True
    if low == 'false':
        return False
    if re.fullmatch(r'-?\d+', token):
        return int(token)
    if re.fullmatch(r'-?\d+\.\d+', token):
        return float(token)
    if token.startswith('[') and token.endswith(']'):
        inner = token[1:-1].strip()
        if not inner:
            return []
        return [_parse_value(x) for x in _split_args(inner)]
    return token


def _extract_named_and_positional(args: List[str]) -> tuple[list[Any], dict[str, Any]]:
    positional: list[Any] = []
    named: dict[str, Any] = {}
    for arg in args:
        stripped = arg.strip()
        is_quoted = len(stripped) >= 2 and stripped[0] in ('"', "'") and stripped[-1] == stripped[0]
        if (not is_quoted) and re.match(r'^[A-Za-z_][A-Za-z0-9_]*\s*:', stripped):
            k, v = stripped.split(':', 1)
            named[k.strip()] = _parse_value(v)
        else:
            positional.append(_parse_value(stripped))
    return positional, named


def _parse_state(source: str) -> Dict[str, Any]:
    state: Dict[str, Any] = {}
    for name, raw_value in STATE_RE.findall(source):
        value = raw_value.strip()
        if value.startswith('win.'):
            continue
        state[name] = _parse_value(value)
    return state


def parse_window_spec(source: str) -> Dict[str, Any]:
    spec: Dict[str, Any] = {
        'title': 'Mellow App',
        'width': 960,
        'height': 640,
        'widgets': [],
        'layout': 'vstack',
        'menus': [],
        'state': _parse_state(source),
        'events': [],
        'platforms': ['windows', 'linux'],
        'runtime': 'native-ui',
        'backend': 'ttk',
    }
    m = WINDOW_RE.search(source)
    if m:
        args = _split_args(m.group(1))
        positional, named = _extract_named_and_positional(args)
        if positional:
            spec['title'] = positional[0] if positional[0] is not None else spec['title']
        if len(positional) > 1 and positional[1] is not None:
            spec['width'] = int(positional[1])
        if len(positional) > 2 and positional[2] is not None:
            spec['height'] = int(positional[2])
        spec['title'] = named.get('title', spec['title'])
        spec['width'] = int(named.get('width', spec['width']))
        spec['height'] = int(named.get('height', spec['height']))
        spec['layout'] = str(named.get('layout', spec['layout']))
        platforms = named.get('platforms', spec['platforms'])
        spec['platforms'] = list(platforms) if isinstance(platforms, list) else spec['platforms']

    for kind, args_raw in CALL_RE.findall(source):
        args = _split_args(args_raw)
        positional, named = _extract_named_and_positional(args)
        if kind in ('vstack', 'hstack', 'grid'):
            spec['layout'] = kind
            if named:
                spec['layout_options'] = named
            continue
        if kind == 'menu':
            label = positional[1] if len(positional) > 1 else named.get('label', 'Menu')
            items = positional[2] if len(positional) > 2 else named.get('items', [])
            spec['menus'].append({'label': label, 'items': items if isinstance(items, list) else []})
            continue
        if kind == 'menu_item':
            menu_name = positional[1] if len(positional) > 1 else named.get('menu', 'Menu')
            item_label = positional[2] if len(positional) > 2 else named.get('label', '')
            action = positional[3] if len(positional) > 3 else named.get('action', '')
            accelerator = named.get('accelerator')
            for menu in spec['menus']:
                if menu.get('label') == menu_name:
                    menu.setdefault('items', []).append({'label': item_label, 'action': action, 'accelerator': accelerator})
                    break
            else:
                spec['menus'].append({'label': menu_name, 'items': [{'label': item_label, 'action': action, 'accelerator': accelerator}]})
            continue
        if len(positional) < 2 and 'text' not in named:
            continue
        widget: Dict[str, Any] = {
            'type': kind,
            'text': positional[1] if len(positional) > 1 else named.get('text', ''),
            'bind': named.get('bind'),
            'id': named.get('id'),
            'placeholder': named.get('placeholder'),
            'options': named.get('options') or positional[2] if kind in ('select', 'listbox') and len(positional) > 2 else named.get('options'),
            'action': named.get('action'),
        }
        if len(positional) > 2 and widget.get('action') is None and kind not in ('input', 'textarea', 'checkbox', 'select', 'listbox', 'slider'):
            widget['action'] = positional[2]
        if kind == 'checkbox':
            widget['default'] = bool(named.get('default', positional[2] if len(positional) > 2 else False))
        if kind == 'spacer':
            widget['size'] = int(named.get('size', positional[1] if positional else 12) or 12)
        if kind == 'slider':
            widget['min'] = int(named.get('min', positional[2] if len(positional) > 2 else 0) or 0)
            widget['max'] = int(named.get('max', positional[3] if len(positional) > 3 else 100) or 100)
        widget = {k: v for k, v in widget.items() if v is not None}
        spec['widgets'].append(widget)
        if widget.get('action'):
            spec['events'].append({'source': widget.get('id') or widget.get('text') or kind, 'action': widget['action']})
    return spec
