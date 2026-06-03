
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict

_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_\.]*)\s*\}\}")
_IF_RE = re.compile(r"\{%\s*if\s+([a-zA-Z_][a-zA-Z0-9_\.]*)\s*%\}(.*?)\{%\s*endif\s*%\}", re.DOTALL)
_FOR_RE = re.compile(r"\{%\s*for\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+in\s+([a-zA-Z_][a-zA-Z0-9_\.]*)\s*%\}(.*?)\{%\s*endfor\s*%\}", re.DOTALL)


def _resolve(name: str, ctx: Dict[str, Any]) -> Any:
    cur: Any = ctx
    for part in name.split('.'):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            cur = getattr(cur, part, None)
        if cur is None:
            return ''
    return cur


def render_prompt(template: str, context: Dict[str, Any]) -> str:
    rendered = template
    while True:
        match = _FOR_RE.search(rendered)
        if not match:
            break
        item_name, source_name, body = match.groups()
        items = _resolve(source_name, context)
        out = []
        if isinstance(items, list):
            for item in items:
                local = dict(context)
                local[item_name] = item
                out.append(render_prompt(body, local))
        rendered = rendered[:match.start()] + ''.join(out) + rendered[match.end():]

    while True:
        match = _IF_RE.search(rendered)
        if not match:
            break
        key, body = match.groups()
        value = _resolve(key, context)
        replacement = render_prompt(body, context) if value else ''
        rendered = rendered[:match.start()] + replacement + rendered[match.end():]

    def _sub(m: re.Match[str]) -> str:
        value = _resolve(m.group(1), context)
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return '' if value is None else str(value)

    return _VAR_RE.sub(_sub, rendered).strip()


def render_prompt_file(path: str | Path, context: Dict[str, Any]) -> str:
    return render_prompt(Path(path).read_text(encoding='utf-8', errors='replace'), context)
