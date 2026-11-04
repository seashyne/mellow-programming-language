"""Where the control-plane state lives, and the timestamp and slug helpers
every record carries."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


CONTROL_PLANE_HOME = Path('.mellow/control-plane')


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _slugify(ref: str) -> str:
    return ''.join(ch if ch.isalnum() or ch in '-_.' else '-' for ch in str(ref)).strip('-') or 'deployment'


def _state_path(base: str | Path | None = None) -> Path:
    root = Path(base) if base else CONTROL_PLANE_HOME
    root.mkdir(parents=True, exist_ok=True)
    return root / 'state.json'


def _load_state(base: str | Path | None = None) -> Dict[str, Any]:
    p = _state_path(base)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                data.setdefault('deployments', {})
                return data
        except Exception:
            pass
    return {'deployments': {}}


def _save_state(state: Dict[str, Any], base: str | Path | None = None) -> Path:
    p = _state_path(base)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return p
