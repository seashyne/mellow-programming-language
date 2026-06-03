from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class MemoryEntry:
    role: str
    text: str
    ts: float
    tags: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {'role': self.role, 'text': self.text, 'ts': self.ts, 'tags': self.tags}


class MemoryStore:
    def __init__(self, path: str | None = None):
        self.path = path
        self._entries: List[MemoryEntry] = []
        if path and os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    raw = json.loads(line)
                    self._entries.append(MemoryEntry(
                        role=str(raw.get('role', 'note')),
                        text=str(raw.get('text', '')),
                        ts=float(raw.get('ts', time.time())),
                        tags=[str(t) for t in raw.get('tags', [])],
                    ))

    def add(self, role: str, text: str, tags: List[str] | None = None) -> MemoryEntry:
        entry = MemoryEntry(role=role, text=text, ts=time.time(), tags=list(tags or []))
        self._entries.append(entry)
        if self.path:
            os.makedirs(os.path.dirname(self.path) or '.', exist_ok=True)
            with open(self.path, 'a', encoding='utf-8') as fh:
                fh.write(json.dumps(entry.to_dict(), ensure_ascii=False) + '\n')
        return entry

    def query(self, text: str, limit: int = 5) -> List[MemoryEntry]:
        q = set(part.lower() for part in text.split() if part.strip())
        scored = []
        for entry in self._entries:
            tokens = set(part.lower() for part in entry.text.split() if part.strip())
            score = len(q & tokens)
            if score or not q:
                scored.append((score, entry.ts, entry))
        scored.sort(key=lambda item: (-item[0], -item[1]))
        return [entry for _, _, entry in scored[:limit]]

    def summary(self, text: str, limit: int = 3) -> str:
        hits = self.query(text, limit=limit)
        if not hits:
            return ''
        return ' | '.join(entry.text[:80] for entry in hits)

    def export(self) -> List[Dict[str, Any]]:
        return [entry.to_dict() for entry in self._entries]
