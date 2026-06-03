from __future__ import annotations

import json
from typing import Any, Dict


def coerce_structured_output(text: str, *, mode: str = 'auto') -> Dict[str, Any]:
    raw = text.strip()
    if mode == 'text':
        return {'text': raw}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
        return {'value': data}
    except Exception:
        # lightweight parser for key: value lines
        out: Dict[str, Any] = {}
        for line in raw.splitlines():
            if ':' not in line:
                continue
            key, value = line.split(':', 1)
            out[key.strip()] = value.strip()
        if out:
            return out
        return {'text': raw}
