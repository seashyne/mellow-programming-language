from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Protocol


class ModelAdapter(Protocol):
    name: str
    def complete(self, prompt: str, *, context: Dict[str, Any] | None = None) -> Dict[str, Any]: ...


@dataclass
class EchoModelAdapter:
    name: str = 'echo'

    def complete(self, prompt: str, *, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        context = context or {}
        memory = context.get('memory_summary', '')
        tools = context.get('tool_summary', '')
        answer = f"[echo:{self.name}] {prompt.strip()}"
        if memory:
            answer += f" | memory={memory}"
        if tools:
            answer += f" | tools={tools}"
        return {
            'model': self.name,
            'text': answer,
            'raw': {'prompt': prompt, 'context': context},
        }


@dataclass
class RuleBasedModelAdapter:
    name: str = 'rule-based'

    def complete(self, prompt: str, *, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        context = context or {}
        lower = prompt.lower()
        intent = 'answer'
        if 'plan' in lower or 'workflow' in lower:
            intent = 'workflow'
        elif 'search' in lower or 'retrieve' in lower or 'rag' in lower:
            intent = 'retrieve'
        elif 'tool' in lower or 'calculate' in lower or 'time' in lower:
            intent = 'tool'
        memory_summary = context.get('memory_summary', '')
        rag_summary = context.get('rag_summary', '')
        tool_summary = context.get('tool_summary', '')
        pieces: List[str] = [f"intent={intent}"]
        if rag_summary:
            pieces.append(f"rag={rag_summary}")
        if memory_summary:
            pieces.append(f"memory={memory_summary}")
        if tool_summary:
            pieces.append(f"tools={tool_summary}")
        return {
            'model': self.name,
            'text': f"[{self.name}] {'; '.join(pieces)}; prompt={prompt.strip()}",
            'raw': {'prompt': prompt, 'context': context, 'intent': intent},
        }


def resolve_model_adapter(name: str | None) -> ModelAdapter:
    key = (name or 'rule-based').strip().lower()
    if key in {'echo', 'local-echo'}:
        return EchoModelAdapter(name=key)
    if key in {'rule-based', 'rule', 'local'}:
        return RuleBasedModelAdapter(name=key)
    # abstraction point: remote providers can be wired later without changing the runtime surface
    return EchoModelAdapter(name=key)
