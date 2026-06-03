from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List

from .memory import MemoryStore
from .model import ModelAdapter
from .observability import ObservationLog
from .policy import PolicyEngine
from .rag import SimpleRAGIndex
from .sandbox import SandboxConfig
from .secrets import export_selected
from .structured import coerce_structured_output
from .tools import ToolRegistry


@dataclass
class AgentRunResult:
    task: str
    answer: str
    structured: Dict[str, Any]
    memory_hits: List[Dict[str, Any]]
    tool_calls: List[Dict[str, Any]]
    rag_hits: List[Dict[str, Any]]
    observations: List[Dict[str, Any]]
    debug: Dict[str, Any]


class AgentRuntime:
    def __init__(
        self,
        *,
        model: ModelAdapter,
        memory: MemoryStore,
        tools: ToolRegistry,
        policy: PolicyEngine,
        rag: SimpleRAGIndex,
        obs: ObservationLog,
        sandbox: SandboxConfig | None = None,
        secret_names: list[str] | None = None,
        secret_scopes: dict[str, list[str]] | None = None,
    ):
        self.model = model
        self.memory = memory
        self.tools = tools
        self.policy = policy
        self.rag = rag
        self.obs = obs
        self.sandbox = sandbox or getattr(policy, 'sandbox', SandboxConfig())
        self.secret_names = list(secret_names or [])
        self.secret_scopes = {str(k): [str(x) for x in v] for k, v in (secret_scopes or {}).items()}
        self._tool_calls: List[Dict[str, Any]] = []

    def build_context(self, task: str) -> Dict[str, Any]:
        memory_hits = [entry.to_dict() for entry in self.memory.query(task, limit=3)]
        rag_hits = [{'id': hit.id, 'text': hit.text, 'metadata': hit.metadata} for hit in self.rag.search(task, limit=3)]
        return {
            'memory_summary': ' | '.join(hit['text'] for hit in memory_hits[:2]),
            'rag_summary': ' | '.join(hit['text'] for hit in rag_hits[:2]),
            'tool_summary': '; '.join(f"{call['tool']}={call['result']}" for call in self._tool_calls[-2:]),
            'memory_hits': memory_hits,
            'rag_hits': rag_hits,
            'sandbox': {
                'enabled': self.sandbox.enabled,
                'network': self.sandbox.network,
                'filesystem': self.sandbox.filesystem,
                'memory': self.sandbox.memory,
            },
            'tools': self.tools.describe(),
        }

    def _check_deadline(self, deadline: float | None) -> None:
        if deadline is not None and time.monotonic() > deadline:
            self.obs.emit('agent.error', error='deadline exceeded')
            raise TimeoutError('agent deadline exceeded')

    def _scope_for_secret(self, secret_name: str, default_scope: str) -> str:
        scopes = self.secret_scopes.get(secret_name) or []
        return str(scopes[0]) if scopes else default_scope

    def call_tool(self, tool_name: str, payload: Dict[str, Any], *, deadline: float | None = None) -> Dict[str, Any]:
        self._check_deadline(deadline)
        tool = self.tools.get(tool_name)
        if not tool:
            raise KeyError(f'unknown tool `{tool_name}`')
        decision = self.policy.check_tool(tool_name, getattr(tool, 'capabilities', []))
        self.obs.emit('policy.check', tool=tool_name, allowed=decision.allowed, reason=decision.reason, capabilities=getattr(tool, 'capabilities', []))
        if not decision.allowed:
            raise PermissionError(decision.reason)
        for secret_name in getattr(tool, 'secret_names', []):
            secret_decision = self.policy.check_secret(secret_name)
            self.obs.emit('policy.secret', secret=secret_name, allowed=secret_decision.allowed, reason=secret_decision.reason)
            if not secret_decision.allowed:
                raise PermissionError(secret_decision.reason)
        merged = dict(payload)
        all_secret_names = self.secret_names + list(getattr(tool, 'secret_names', []))
        scoped_env: Dict[str, str] = {}
        for secret_name in all_secret_names:
            scoped_env.update(export_selected([secret_name], scope=self._scope_for_secret(secret_name, f'tool.{tool_name}')))
        merged.setdefault('_secrets', scoped_env)
        started = time.monotonic()
        result = tool.call(merged)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        call = {'tool': tool_name, 'input': payload, 'result': result, 'elapsed_ms': elapsed_ms}
        self._tool_calls.append(call)
        self.obs.emit('tool.call', **call)
        return result

    def run(self, task: str, *, structured_mode: str = 'auto', auto_tool: str | None = None, prompt_text: str | None = None, timeout_ms: int | None = None, debug: bool = False) -> AgentRunResult:
        started = time.monotonic()
        deadline = (started + (timeout_ms / 1000.0)) if timeout_ms else None
        self.obs.emit('agent.start', task=task, model=getattr(self.model, 'name', 'unknown'), timeout_ms=timeout_ms)
        memory_hits = [entry.to_dict() for entry in self.memory.query(task, limit=3)]
        rag_hits = [{'id': hit.id, 'text': hit.text, 'metadata': hit.metadata} for hit in self.rag.search(task, limit=3)]
        if auto_tool:
            self.call_tool(auto_tool, {'query': task, 'expression': '1+1'}, deadline=deadline)
        self._check_deadline(deadline)
        context = self.build_context(task)
        prompt = prompt_text or task
        model_secret_env: Dict[str, str] = {}
        for secret_name in self.secret_names:
            model_secret_env.update(export_selected([secret_name], scope=self._scope_for_secret(secret_name, 'agent.run')))
        if model_secret_env:
            self.obs.emit('secret.inject', scope='agent.run', names=sorted(model_secret_env.keys()))
        model_result = self.model.complete(prompt, context={**context, 'secrets': {k: '***' for k in model_secret_env}})
        answer = str(model_result.get('text', ''))
        prompt_tokens = max(1, len(prompt.split()))
        completion_tokens = max(1, len(answer.split()))
        self.obs.emit('model.tokens', model=getattr(self.model, 'name', 'unknown'), prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
        if self.sandbox.memory:
            self.memory.add('user', task, tags=['task'])
            self.memory.add('assistant', answer, tags=['answer'])
        structured = coerce_structured_output(answer, mode=structured_mode)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        self.obs.emit('agent.finish', task=task, answer=answer, structured=structured, elapsed_ms=elapsed_ms)
        debug_payload = {
            'run_id': self.obs.run_id,
            'elapsed_ms': elapsed_ms,
            'sandbox': context.get('sandbox'),
            'tool_count': len(self._tool_calls),
            'token_usage': {'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens},
            'memory_enabled': self.sandbox.memory,
            'secret_names': sorted(model_secret_env.keys()),
        }
        if debug:
            self.obs.emit('agent.debug', **debug_payload)
        return AgentRunResult(
            task=task,
            answer=answer,
            structured=structured,
            memory_hits=memory_hits,
            tool_calls=list(self._tool_calls),
            rag_hits=rag_hits,
            observations=self.obs.export(),
            debug=debug_payload,
        )
