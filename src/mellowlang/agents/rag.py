from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class RAGChunk:
    id: str
    text: str
    metadata: Dict[str, Any]


class SimpleRAGIndex:
    def __init__(self, chunks: List[RAGChunk] | None = None):
        self.chunks = list(chunks or [])

    @classmethod
    def from_texts(cls, texts: List[str]) -> 'SimpleRAGIndex':
        return cls([RAGChunk(id=f'chunk-{i+1}', text=text, metadata={}) for i, text in enumerate(texts)])

    def search(self, query: str, limit: int = 3) -> List[RAGChunk]:
        q = set(part.lower() for part in query.split() if part.strip())
        scored = []
        for chunk in self.chunks:
            tokens = set(part.lower() for part in chunk.text.split() if part.strip())
            score = len(q & tokens)
            if score or not q:
                scored.append((score, len(chunk.text), chunk))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [chunk for _, _, chunk in scored[:limit]]

    def summary(self, query: str, limit: int = 2) -> str:
        hits = self.search(query, limit=limit)
        if not hits:
            return ''
        return ' | '.join(hit.text[:100] for hit in hits)
