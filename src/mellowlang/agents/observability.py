from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class ObservationEvent:
    kind: str
    payload: Dict[str, Any]
    ts: float
    seq: int
    run_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {'kind': self.kind, 'payload': self.payload, 'ts': self.ts, 'seq': self.seq, 'run_id': self.run_id}


class ObservationLog:
    def __init__(self, path: str | None = None, *, run_id: str | None = None):
        self.path = path
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.events: List[ObservationEvent] = []
        self._seq = 0

    def emit(self, kind: str, **payload: Any) -> None:
        self._seq += 1
        evt = ObservationEvent(kind=kind, payload=dict(payload), ts=time.time(), seq=self._seq, run_id=self.run_id)
        self.events.append(evt)
        if self.path:
            os.makedirs(os.path.dirname(self.path) or '.', exist_ok=True)
            with open(self.path, 'a', encoding='utf-8') as fh:
                fh.write(json.dumps(evt.to_dict(), ensure_ascii=False) + '\n')

    def export(self) -> List[Dict[str, Any]]:
        return [evt.to_dict() for evt in self.events]

    def summary(self) -> Dict[str, Any]:
        token_prompt = 0
        token_completion = 0
        tool_calls = 0
        errors = 0
        for evt in self.events:
            if evt.kind == 'model.tokens':
                token_prompt += int(evt.payload.get('prompt_tokens', 0))
                token_completion += int(evt.payload.get('completion_tokens', 0))
            elif evt.kind == 'tool.call':
                tool_calls += 1
            elif evt.kind.endswith('.error'):
                errors += 1
        return {
            'run_id': self.run_id,
            'events': len(self.events),
            'tool_calls': tool_calls,
            'prompt_tokens': token_prompt,
            'completion_tokens': token_completion,
            'errors': errors,
        }


def read_observation_file(path: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return out
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out
