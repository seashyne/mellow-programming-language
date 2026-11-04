"""Read a window spec from disk, and dump one back out as JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from .parsing import parse_window_spec


def parse_window_file(path: str | Path) -> Dict[str, Any]:
    return parse_window_spec(Path(path).read_text(encoding='utf-8'))


def dump_spec_json(path: str | Path) -> str:
    return json.dumps(parse_window_file(path), ensure_ascii=False, indent=2)
