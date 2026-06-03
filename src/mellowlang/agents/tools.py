from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


@dataclass
class Tool:
    name: str
    description: str
    fn: Callable[[Dict[str, Any]], Dict[str, Any]]
    alias: str | None = None
    defaults: Dict[str, Any] | None = None
    capabilities: List[str] = field(default_factory=list)
    secret_names: List[str] = field(default_factory=list)

    def call(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        merged = dict(self.defaults or {})
        merged.update(dict(payload or {}))
        return self.fn(merged)


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        if tool.alias and tool.alias not in self._tools:
            self._tools[tool.alias] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> List[str]:
        return sorted(self._tools)

    def describe(self) -> List[Dict[str, Any]]:
        return [
            {
                'name': t.name,
                'description': t.description,
                'capabilities': list(t.capabilities),
                'secrets': list(t.secret_names),
            }
            for t in sorted(self._tools.values(), key=lambda t: t.name)
        ]


def _time_tool(_: Dict[str, Any]) -> Dict[str, Any]:
    now = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    return {'now_utc': now}


def _calc_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    expr = str(payload.get('expression', '0'))
    if not expr:
        expr = '0'
    allowed = set('0123456789+-*/(). %')
    if any(ch not in allowed for ch in expr):
        raise ValueError('expression contains unsupported characters')
    return {'expression': expr, 'result': eval(expr, {'__builtins__': {}}, {})}


def _search_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    query = str(payload.get('query', '')).strip()
    corpus = [
        'Mellow 1.8 ships sandboxed agent execution and capability permissions.',
        'Workflow steps can run in parallel with retries and timeouts.',
        'Structured output improves machine-to-machine automation.',
        'Observability logs trace agent decisions, token estimates, and tool calls.',
        'Developer platform features include preview, prompt debugger, playground, serve, and marketplace.',
    ]
    hits = [line for line in corpus if query.lower() in line.lower()] if query else corpus[:]
    return {'query': query, 'hits': hits[:5]}


def builtin_tool_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(Tool('time.now', 'Return the current UTC time.', _time_tool, capabilities=['tools.time.now']))
    reg.register(Tool('calc.eval', 'Safely evaluate a basic arithmetic expression.', _calc_tool, capabilities=['tools.calc.eval']))
    reg.register(Tool('search.docs', 'Search the built-in Mellow AI docs corpus.', _search_tool, capabilities=['tools.search.docs']))
    return reg



def apply_tool_manifest(reg: ToolRegistry, manifest_entries) -> ToolRegistry:
    base = {name: reg.get(name) for name in reg.names()}
    for entry in manifest_entries:
        target = entry.builtin or entry.name
        builtin = base.get(target)
        if not builtin:
            continue
        reg.register(Tool(
            entry.name,
            entry.description or builtin.description,
            builtin.fn,
            alias=target,
            defaults=entry.defaults,
            capabilities=list(getattr(builtin, 'capabilities', [])),
            secret_names=list(getattr(builtin, 'secret_names', [])),
        ))
    return reg
