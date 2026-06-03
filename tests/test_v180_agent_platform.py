from pathlib import Path

from mellowlang.agents import (
    AgentRuntime,
    MemoryStore,
    ObservationLog,
    PolicyEngine,
    SandboxConfig,
    SimpleRAGIndex,
    Workflow,
    WorkflowRunner,
    WorkflowStep,
    builtin_tool_registry,
    resolve_model_adapter,
    set_secret,
    list_secrets,
)


def make_runtime(tmp_path, *, sandbox=False, allow_caps=None, secrets=None):
    obs = ObservationLog(str(tmp_path / 'obs.jsonl'))
    sandbox_cfg = SandboxConfig.from_flags(enabled=sandbox, allowed_secrets=secrets or [])
    return AgentRuntime(
        model=resolve_model_adapter('rule-based'),
        memory=MemoryStore(str(tmp_path / 'mem.jsonl')),
        tools=builtin_tool_registry(),
        policy=PolicyEngine(allowed_capabilities=allow_caps or [], sandbox=sandbox_cfg),
        rag=SimpleRAGIndex.from_texts(['sandbox docs', 'parallel workflow docs']),
        obs=obs,
        sandbox=sandbox_cfg,
        secret_names=secrets or [],
    )


def test_secret_store_roundtrip(tmp_path, monkeypatch):
    import mellowlang.agents.secrets as sec
    monkeypatch.setattr(sec, 'SECRET_FILE', tmp_path / 'agent_secrets.json')
    set_secret('OPENAI_API_KEY', 'sk-demo-secret')
    items = list_secrets()
    assert items[0]['name'] == 'OPENAI_API_KEY'
    assert items[0]['masked'].startswith('sk')


def test_sandbox_blocks_tool_without_capability(tmp_path):
    runtime = make_runtime(tmp_path, sandbox=True, allow_caps=[])
    try:
        runtime.call_tool('search.docs', {'query': 'docs'})
    except PermissionError as e:
        assert 'not in allow-list' in str(e) or 'denied' in str(e)
    else:
        raise AssertionError('expected permission error')


def test_workflow_parallel_and_debug(tmp_path):
    runtime = make_runtime(tmp_path, sandbox=True, allow_caps=['tools.search.docs', 'tools.time.now'])
    wf = Workflow(
        name='parallel',
        steps=[
            WorkflowStep('ctx', 'parallel', {'steps': [
                {'name': 'search', 'kind': 'tool', 'payload': {'tool': 'search.docs', 'input': {'query': 'docs'}}, 'retries': 1, 'timeout_ms': 1000},
                {'name': 'clock', 'kind': 'tool', 'payload': {'tool': 'time.now', 'input': {}}, 'retries': 1, 'timeout_ms': 1000},
            ]}),
            WorkflowStep('answer', 'model'),
        ],
    )
    res = WorkflowRunner(runtime).run(wf, 'plan agent platform')
    assert res['workflow'] == 'parallel'
    assert any(step['kind'] == 'parallel' for step in res['steps'])
