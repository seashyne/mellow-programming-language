from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class WorkflowStep:
    name: str
    kind: str
    payload: Dict[str, Any] = field(default_factory=dict)
    retries: int = 0
    timeout_ms: int | None = None


@dataclass
class Workflow:
    name: str
    steps: List[WorkflowStep]


class WorkflowRunner:
    def __init__(self, runtime: Any):
        self.runtime = runtime

    def _run_single_step(self, step: WorkflowStep, task: str) -> Dict[str, Any]:
        started = time.monotonic()
        if step.kind == 'memory':
            result = {'summary': self.runtime.memory.summary(task)}
        elif step.kind == 'rag':
            result = {'summary': self.runtime.rag.summary(task)}
        elif step.kind == 'tool':
            tool_name = str(step.payload.get('tool', ''))
            tool_payload = dict(step.payload.get('input', {}))
            result = self.runtime.call_tool(tool_name, tool_payload)
        elif step.kind == 'model':
            result = self.runtime.model.complete(task, context=self.runtime.build_context(task))
        elif step.kind == 'parallel':
            children = [WorkflowStep(**child) if isinstance(child, dict) else child for child in list(step.payload.get('steps', []))]
            with ThreadPoolExecutor(max_workers=max(1, len(children))) as ex:
                futures = {ex.submit(self._run_single_step, child, task): child.name for child in children}
                result = {'parallel': [f.result() for f in as_completed(futures)]}
        else:
            result = {'result': None}
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if step.timeout_ms is not None and elapsed_ms > step.timeout_ms:
            raise TimeoutError(f'step `{step.name}` exceeded timeout of {step.timeout_ms}ms')
        return {'step': step.name, 'kind': step.kind, 'elapsed_ms': elapsed_ms, **result}

    def run(self, workflow: Workflow, task: str) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
        for step in workflow.steps:
            attempts = 0
            while True:
                try:
                    attempts += 1
                    payload = self._run_single_step(step, task)
                    payload['attempts'] = attempts
                    results.append(payload)
                    break
                except Exception as exc:
                    if attempts > int(step.retries or 0):
                        results.append({'step': step.name, 'kind': step.kind, 'error': str(exc), 'attempts': attempts})
                        break
        return {'workflow': workflow.name, 'steps': results}
