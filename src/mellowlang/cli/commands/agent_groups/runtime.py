"""Running an agent: one-shot run, workflow, the offline demo, and reading an observation log back."""

from __future__ import annotations

from pathlib import Path
import json
import sys

from ...common import _cli_line, _json_print
from .deps import (
    Workflow, WorkflowRunner, WorkflowStep, render_prompt_file,
    read_observation_file, load_signed_policy,
)
from .support import _agent_prompt_context, _make_agent_runtime, _run_agent_package

def _cmd_agent_run(task: str, model: str, memory_path: str, obs_path: str, tools: list[str], allow_tools: list[str], deny_tools: list[str], rag_file: str | None, prompt_file: str | None = None, tool_manifest: str | None = None, package: str | None = None, structured: str = 'auto', json_out: bool = False, sandbox: bool = False, allow_caps: list[str] | None = None, deny_caps: list[str] | None = None, secrets: list[str] | None = None, timeout_ms: int | None = None, debug: bool = False, policy_file: str | None = None, policy_key: str | None = None) -> int:
    if prompt_file in {'auto', 'text'} and isinstance(tool_manifest, bool) and package is None and structured == 'auto' and json_out is False:
        structured = str(prompt_file)
        json_out = bool(tool_manifest)
        prompt_file = None
        tool_manifest = None
    if package:
        return _run_agent_package(package, task, json_out=json_out, sandbox=sandbox, allow_caps=allow_caps, deny_caps=deny_caps, secrets=secrets, timeout_ms=timeout_ms, debug=debug, policy_file=policy_file, policy_key=policy_key)
    signed_policy = None
    if policy_file and Path(policy_file).exists():
        signed_policy = load_signed_policy(policy_file, verify_key=policy_key) if policy_key else load_signed_policy(policy_file)
    effective_allow_tools = list(dict.fromkeys((allow_tools or []) + (tools or [])))
    runtime = _make_agent_runtime(model, memory_path, obs_path, effective_allow_tools, deny_tools, rag_file, tool_manifest, sandbox=sandbox, allow_caps=allow_caps, deny_caps=deny_caps, secrets=secrets, signed_policy=signed_policy)
    auto_tool = tools[0] if tools else None
    prompt = render_prompt_file(prompt_file, _agent_prompt_context(task, runtime)) if prompt_file else None
    try:
        result = runtime.run(task, structured_mode=structured, auto_tool=auto_tool, prompt_text=prompt, timeout_ms=timeout_ms, debug=debug)
    except Exception as e:
        if json_out:
            _json_print({'ok': False, 'error': str(e)})
        else:
            _cli_line(f'agent run failed: {e}', kind='error', file=sys.stderr)
        return 1
    payload = {
        'ok': True,
        'task': result.task,
        'answer': result.answer,
        'structured': result.structured,
        'memory_hits': result.memory_hits,
        'tool_calls': result.tool_calls,
        'rag_hits': result.rag_hits,
        'observations': result.observations,
        'prompt': prompt,
        'tool_manifest': tool_manifest,
        'debug': result.debug,
        'policy_file': policy_file,
    }
    if json_out:
        _json_print(payload)
    else:
        _cli_line('Mellow 1.8.1 Hosted Agent Platform run', kind='ok')
        print(f'Model           : {model}')
        print(f'Task            : {task}')
        if prompt:
            print(f'Prompt DSL      : {prompt_file}')
        if tool_manifest:
            print(f'Tool manifest   : {tool_manifest}')
        if policy_file:
            print(f'Policy file     : {policy_file}')
        print(f'Answer          : {result.answer}')
        print('Structured      : ' + json.dumps(result.structured, ensure_ascii=False))
        print(f'Memory hits     : {len(result.memory_hits)}')
        print(f'RAG hits        : {len(result.rag_hits)}')
        print(f'Tool calls      : {len(result.tool_calls)}')
        print(f'Observability   : {obs_path}')
        print(f"Run ID          : {result.debug.get('run_id')}")
        if debug:
            print('Debug           : ' + json.dumps(result.debug, ensure_ascii=False))
    return 0

def _cmd_agent_workflow(task: str, model: str, memory_path: str, obs_path: str, rag_file: str | None, package: str | None = None, json_out: bool = False, sandbox: bool = False, allow_caps: list[str] | None = None, deny_caps: list[str] | None = None, secrets: list[str] | None = None, retries: int = 1, timeout_ms: int = 2000, parallel: bool = False, debug: bool = False, policy_file: str | None = None, policy_key: str | None = None) -> int:
    if isinstance(package, bool) and json_out is False:
        json_out = package
        package = None
    if package:
        return _run_agent_package(package, task, json_out=json_out, sandbox=sandbox, allow_caps=allow_caps, deny_caps=deny_caps, secrets=secrets, timeout_ms=timeout_ms, debug=debug, policy_file=policy_file, policy_key=policy_key)
    signed_policy = None
    if policy_file and Path(policy_file).exists():
        signed_policy = load_signed_policy(policy_file, verify_key=policy_key) if policy_key else load_signed_policy(policy_file)
    runtime = _make_agent_runtime(model, memory_path, obs_path, ['search.docs', 'time.now'], [], rag_file, sandbox=sandbox, allow_caps=allow_caps, deny_caps=deny_caps, secrets=secrets, signed_policy=signed_policy)
    steps = [
        WorkflowStep('recall-memory', 'memory', retries=retries, timeout_ms=timeout_ms),
        WorkflowStep('retrieve-context', 'rag', retries=retries, timeout_ms=timeout_ms),
    ]
    if parallel:
        steps.append(WorkflowStep('parallel-context', 'parallel', {'steps': [
            {'name': 'search-docs', 'kind': 'tool', 'payload': {'tool': 'search.docs', 'input': {'query': task}}, 'retries': retries, 'timeout_ms': timeout_ms},
            {'name': 'stamp-time', 'kind': 'tool', 'payload': {'tool': 'time.now', 'input': {}}, 'retries': retries, 'timeout_ms': timeout_ms},
        ]}, retries=retries, timeout_ms=timeout_ms))
    else:
        steps.extend([
            WorkflowStep('search-docs', 'tool', {'tool': 'search.docs', 'input': {'query': task}}, retries=retries, timeout_ms=timeout_ms),
            WorkflowStep('stamp-time', 'tool', {'tool': 'time.now', 'input': {}}, retries=retries, timeout_ms=timeout_ms),
        ])
    steps.append(WorkflowStep('generate-answer', 'model', retries=retries, timeout_ms=timeout_ms))
    wf = Workflow(name='default-agent-workflow', steps=steps)
    runner = WorkflowRunner(runtime)
    result = runner.run(wf, task)
    if json_out:
        _json_print({'ok': True, **result, 'debug': runtime.obs.summary(), 'policy_file': policy_file})
    else:
        _cli_line('Mellow workflow executed', kind='ok')
        print(f'Workflow        : {result["workflow"]}')
        if policy_file:
            print(f'Policy file     : {policy_file}')
        for step in result['steps']:
            print(f"- {step['step']} [{step['kind']}] -> {json.dumps(step, ensure_ascii=False)}")
        if debug:
            print('Debug           : ' + json.dumps(runtime.obs.summary(), ensure_ascii=False))
    return 0

def _cmd_agent_demo(json_out: bool) -> int:
    payload = {
        'version': '1.8.5',
        'focus': {
            'hosted_runtime': 5,
            'deployment_targets': 5,
            'deployment_manifests': 5,
            'remote_control_plane': 5,
            'deployment_health_checks': 5,
            'traffic_split_rollouts': 5,
            'rollback_management': 5,
            'secret_scopes': 5,
            'signed_capability_policies': 5,
            'observability': 4,
            'developer_platform': 4,
        },
        'commands': [
            'mellow agent deploy my.agent --target docker --public-url https://example.com',
            'mellow agent serve --package my.agent --deployment-manifest .mellow/deploy/my_agent/deployment.json',
            'mellow agent secret set OPENAI_API_KEY sk-demo --scope agent.run --scope tool.search.docs',
            'mellow agent run --task "..." --policy-file policies/capabilities.json --policy-key secret',
        ],
    }
    if json_out:
        _json_print(payload)
    else:
        _cli_line('Mellow 1.8.5 Deployment Metrics Platform', kind='ok')
        for key, stars in payload['focus'].items():
            print(f"- {key:26} : {'⭐' * stars}")
        print('Commands:')
        for cmd in payload['commands']:
            print(f'  {cmd}')
    return 0

def _cmd_agent_inspect_log(path: str, json_out: bool) -> int:
    p = Path(path)
    if not p.exists():
        if json_out:
            _json_print({'ok': False, 'error': f'log not found: {path}'})
        else:
            _cli_line(f'log not found: {path}', kind='error', file=sys.stderr)
        return 2
    events = read_observation_file(path)
    payload = {'ok': True, 'count': len(events), 'events': events[-20:]}
    if json_out:
        _json_print(payload)
    else:
        _cli_line(f'Loaded {len(events)} observability event(s)', kind='ok')
        for evt in events[-10:]:
            print(f"- {evt.get('kind')} :: {json.dumps(evt.get('payload', {}), ensure_ascii=False)}")
    return 0
