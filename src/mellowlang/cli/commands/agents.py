from __future__ import annotations

import contextlib
import io
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ..common import _cli_line, _json_print, _lazy_attr

pkg_get_registry_url = _lazy_attr("mellowlang.package_manager", "get_registry_url")
serve_playground = _lazy_attr("mellowlang.playground", "serve_playground")
build_static_playground = _lazy_attr("mellowlang.playground", "build_static_playground")

_AG = "mellowlang.agents"
AgentRuntime = _lazy_attr(_AG, "AgentRuntime")
MemoryStore = _lazy_attr(_AG, "MemoryStore")
ObservationLog = _lazy_attr(_AG, "ObservationLog")
PolicyEngine = _lazy_attr(_AG, "PolicyEngine")
SimpleRAGIndex = _lazy_attr(_AG, "SimpleRAGIndex")
Workflow = _lazy_attr(_AG, "Workflow")
WorkflowRunner = _lazy_attr(_AG, "WorkflowRunner")
WorkflowStep = _lazy_attr(_AG, "WorkflowStep")
builtin_tool_registry = _lazy_attr(_AG, "builtin_tool_registry")
resolve_model_adapter = _lazy_attr(_AG, "resolve_model_adapter")
render_prompt_file = _lazy_attr(_AG, "render_prompt_file")
load_tool_manifest = _lazy_attr(_AG, "load_tool_manifest")
load_agent_package = _lazy_attr(_AG, "load_agent_package")
init_agent_package = _lazy_attr(_AG, "init_agent_package")
apply_tool_manifest = _lazy_attr(_AG, "apply_tool_manifest")
build_agent_archive = _lazy_attr(_AG, "build_agent_archive")
publish_agent_from_dir = _lazy_attr(_AG, "publish_agent_from_dir")
install_agent_package = _lazy_attr(_AG, "install_agent_package")
search_agent_local = _lazy_attr(_AG, "search_agent_local")
publish_agent_remote = _lazy_attr(_AG, "publish_agent_remote")
install_agent_remote = _lazy_attr(_AG, "install_agent_remote")
search_agent_remote = _lazy_attr(_AG, "search_agent_remote")
load_installed_agent = _lazy_attr(_AG, "load_installed_agent")
agent_dependency_graph = _lazy_attr(_AG, "agent_dependency_graph")
generate_agent_lock = _lazy_attr(_AG, "generate_agent_lock")
write_agent_lock = _lazy_attr(_AG, "write_agent_lock")
install_agent_with_lock = _lazy_attr(_AG, "install_agent_with_lock")
set_agent_auth_token = _lazy_attr(_AG, "set_agent_auth_token")
clear_agent_auth_token = _lazy_attr(_AG, "clear_agent_auth_token")
agent_registry_whoami = _lazy_attr(_AG, "agent_registry_whoami")
SandboxConfig = _lazy_attr(_AG, "SandboxConfig")
set_secret = _lazy_attr(_AG, "set_secret")
remove_secret = _lazy_attr(_AG, "remove_secret")
list_secrets = _lazy_attr(_AG, "list_secrets")
resolve_secret_env = _lazy_attr(_AG, "resolve_secret_env")
read_observation_file = _lazy_attr(_AG, "read_observation_file")
load_signed_policy = _lazy_attr(_AG, "load_signed_policy")
build_deployment_manifest = _lazy_attr(_AG, "build_deployment_manifest")
load_deployment_manifest = _lazy_attr(_AG, "load_deployment_manifest")
write_deployment_bundle = _lazy_attr(_AG, "write_deployment_bundle")
sign_capability_policy = _lazy_attr(_AG, "sign_capability_policy")
register_deployment = _lazy_attr(_AG, "register_deployment")
list_deployments = _lazy_attr(_AG, "list_deployments")
get_deployment_status = _lazy_attr(_AG, "get_deployment_status")
sync_deployment = _lazy_attr(_AG, "sync_deployment")
list_revisions = _lazy_attr(_AG, "list_revisions")
rollout_revision = _lazy_attr(_AG, "rollout_revision")
run_health_check = _lazy_attr(_AG, "run_health_check")
update_traffic_split = _lazy_attr(_AG, "update_traffic_split")
rollback_deployment = _lazy_attr(_AG, "rollback_deployment")
record_deployment_metrics = _lazy_attr(_AG, "record_deployment_metrics")
get_deployment_metrics = _lazy_attr(_AG, "get_deployment_metrics")
get_autoscaling_signals = _lazy_attr(_AG, "get_autoscaling_signals")
set_alert_rules = _lazy_attr(_AG, "set_alert_rules")
evaluate_alerts = _lazy_attr(_AG, "evaluate_alerts")
add_job = _lazy_attr(_AG, "add_job")
agent_list_jobs = _lazy_attr(_AG, "list_jobs")
run_due_jobs = _lazy_attr(_AG, "run_due_jobs")
run_background_runner = _lazy_attr(_AG, "run_background_runner")
read_runner_status = _lazy_attr(_AG, "read_runner_status")
add_trigger = _lazy_attr(_AG, "add_trigger")
list_triggers = _lazy_attr(_AG, "list_triggers")
emit_event = _lazy_attr(_AG, "emit_event")
add_webhook = _lazy_attr(_AG, "add_webhook")
list_webhooks = _lazy_attr(_AG, "list_webhooks")
receive_webhook = _lazy_attr(_AG, "receive_webhook")
submit_job = _lazy_attr(_AG, "submit_job")
get_queue_item = _lazy_attr(_AG, "get_queue_item")
list_queue = _lazy_attr(_AG, "list_queue")
drain_queue = _lazy_attr(_AG, "drain_queue")
list_dead_letter = _lazy_attr(_AG, "list_dead_letter")
retry_queue_item = _lazy_attr(_AG, "retry_queue_item")
read_queue_log = _lazy_attr(_AG, "read_queue_log")
queue_stats = _lazy_attr(_AG, "queue_stats")
start_webhook_server = _lazy_attr(_AG, "start_webhook_server")
read_webhook_server_status = _lazy_attr(_AG, "read_webhook_server_status")
read_job_api_status = _lazy_attr(_AG, "read_job_api_status")


def _load_rag_index(rag_file: str | None) -> SimpleRAGIndex:
    texts = [
        "Mellow 1.7 ships an AI-native agent runtime with tools, memory, workflows, and retrieval.",
        "Structured output lets agents return machine-readable objects for apps and automation.",
        "Policies gate tool usage and observability logs capture every major decision.",
        "Model abstraction keeps the runtime provider-agnostic so local or hosted adapters can fit later.",
    ]
    if rag_file and Path(rag_file).exists():
        raw = Path(rag_file).read_text(encoding='utf-8', errors='replace')
        extra = [part.strip() for part in raw.splitlines() if part.strip()]
        if extra:
            texts.extend(extra)
    return SimpleRAGIndex.from_texts(texts)



def _make_agent_runtime(model_name: str, memory_path: str, obs_path: str, allow_tools: list[str] | None = None, deny_tools: list[str] | None = None, rag_file: str | None = None, tool_manifest: str | None = None, *, sandbox: bool = False, allow_caps: list[str] | None = None, deny_caps: list[str] | None = None, secrets: list[str] | None = None, secret_scopes: dict[str, list[str]] | None = None, signed_policy: dict[str, Any] | None = None) -> AgentRuntime:
    tools = builtin_tool_registry()
    if tool_manifest and Path(tool_manifest).exists():
        tools = apply_tool_manifest(tools, load_tool_manifest(tool_manifest))
    sandbox_cfg = SandboxConfig.from_flags(enabled=sandbox, allowed_secrets=secrets or [])
    return AgentRuntime(
        model=resolve_model_adapter(model_name),
        memory=MemoryStore(memory_path),
        tools=tools,
        policy=PolicyEngine(allowed_tools=allow_tools or [], denied_tools=deny_tools or [], allowed_capabilities=allow_caps or [], denied_capabilities=deny_caps or [], sandbox=sandbox_cfg, signed_policy=signed_policy),
        rag=_load_rag_index(rag_file),
        obs=ObservationLog(obs_path),
        sandbox=sandbox_cfg,
        secret_names=secrets or [],
        secret_scopes=secret_scopes or {},
    )


def _agent_prompt_context(task: str, runtime: AgentRuntime, package_name: str | None = None) -> dict[str, Any]:
    context = runtime.build_context(task)
    context.update({
        'task': task,
        'package_name': package_name or 'adhoc.agent',
        'tools': runtime.tools.describe(),
    })
    return context


def _run_agent_package(package_dir: str, task: str, *, json_out: bool, sandbox: bool = False, allow_caps: list[str] | None = None, deny_caps: list[str] | None = None, secrets: list[str] | None = None, timeout_ms: int | None = None, debug: bool = False, policy_file: str | None = None, policy_key: str | None = None) -> int:
    package_dir = _resolve_agent_package_ref(package_dir)
    package = load_agent_package(package_dir)
    signed_policy = None
    effective_policy_file = policy_file or (str((package.root / package.policy_file).resolve()) if package.policy_file else None)
    if effective_policy_file and Path(effective_policy_file).exists():
        signed_policy = load_signed_policy(effective_policy_file, verify_key=policy_key) if policy_key else load_signed_policy(effective_policy_file)
    effective_allow = list(dict.fromkeys((allow_caps or []) + list(package.capabilities_allow)))
    effective_deny = list(dict.fromkeys((deny_caps or []) + list(package.capabilities_deny)))
    effective_secrets = list(dict.fromkeys((secrets or []) + list(package.required_secrets)))
    runtime = _make_agent_runtime(package.model, str((package.root / package.memory_path).resolve()), str((package.root / package.obs_path).resolve()), rag_file=None, tool_manifest=str(package.tool_manifest_path()) if package.tool_manifest_path() else None, sandbox=sandbox, allow_caps=effective_allow, deny_caps=effective_deny, secrets=effective_secrets, secret_scopes=package.secret_scopes, signed_policy=signed_policy)
    prompt = render_prompt_file(package.prompt_path(), _agent_prompt_context(task, runtime, package.name))
    result = runtime.run(task, structured_mode='auto', prompt_text=prompt, timeout_ms=timeout_ms, debug=debug)
    payload = {
        'ok': True,
        'package': package.name,
        'version': package.version,
        'task': task,
        'prompt': prompt,
        'answer': result.answer,
        'structured': result.structured,
        'tool_calls': result.tool_calls,
        'required_secrets': package.required_secrets,
        'secret_scopes': package.secret_scopes,
        'policy_file': effective_policy_file,
    }
    if json_out:
        _json_print(payload)
    else:
        _cli_line(f'Agent package executed: {package.name}', kind='ok')
        print(f'Package         : {package.name}@{package.version}')
        print(f'Prompt file     : {package.prompt_file}')
        print(f'Policy file     : {effective_policy_file or "-"}')
        print(f'Answer          : {result.answer}')
        print(f'Tool calls      : {len(result.tool_calls)}')
    return 0


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


def _cmd_agent_package_init(dir_path: str, name: str, force: bool, json_out: bool) -> int:
    try:
        root = init_agent_package(dir_path, name=name, force=force)
    except Exception as e:
        if json_out:
            _json_print({'ok': False, 'error': str(e)})
        else:
            _cli_line(f'agent package init failed: {e}', kind='error', file=sys.stderr)
        return 1
    payload = {'ok': True, 'dir': str(root), 'name': name}
    if json_out:
        _json_print(payload)
    else:
        _cli_line('Agent package created', kind='ok')
        print(f'Directory       : {root}')
        print(f'Name            : {name}')
    return 0



def _cmd_agent_package_lock(dir_path: str, json_out: bool = False) -> int:
    try:
        res = generate_agent_lock(dir_path)
        lock_path = write_agent_lock(dir_path, res['lock'])
        payload = {'ok': True, 'lockfile': str(lock_path), 'packages': len(res['lock'].get('packages') or [])}
    except Exception as e:
        payload = {'ok': False, 'error': str(e)}
    if json_out:
        _json_print(payload)
    else:
        if payload.get('ok'):
            _cli_line('Agent lockfile written', kind='ok')
            print(f"Lockfile        : {payload['lockfile']}")
            print(f"Packages pinned : {payload['packages']}")
        else:
            _cli_line(f"agent package lock failed: {payload.get('error')}", kind='error', file=sys.stderr)
    return 0 if payload.get('ok') else 1


def _cmd_agent_registry_login(registry: str | None, token: str, private: bool, json_out: bool = False) -> int:
    res = set_agent_auth_token((registry or pkg_get_registry_url()), token, private=private)
    if json_out:
        _json_print(res)
    else:
        _cli_line('Agent registry token saved', kind='ok')
        print(f"Registry        : {res['registry']}")
        print(f"Mode            : {'private' if private else 'read/publish'}")
    return 0


def _cmd_agent_registry_logout(registry: str | None, private: bool, json_out: bool = False) -> int:
    res = clear_agent_auth_token(registry, private=private)
    if json_out:
        _json_print(res)
    else:
        _cli_line('Agent registry token cleared', kind='ok')
        print(f"Registry        : {res['registry']}")
        print(f"Mode            : {'private' if private else 'read/publish'}")
    return 0


def _cmd_agent_registry_whoami(registry: str | None, json_out: bool = False) -> int:
    res = agent_registry_whoami(registry)
    if json_out:
        _json_print(res)
    else:
        _cli_line('Agent registry auth', kind='ok')
        print(f"Registry        : {res['registry']}")
        print(f"Read auth       : {res['read_auth']}")
        print(f"Private auth    : {res['private_auth']}")
        print(f"Config          : {res['config']}")
    return 0


def _cmd_agent_package_build(dir_path: str, out_path: str | None, signing_key: str | None = None, signer: str | None = None, write_lock: bool = False, json_out: bool = False) -> int:
    if isinstance(signing_key, bool) and signer is None and json_out is False:
        json_out = signing_key
        signing_key = None
    try:
        res = build_agent_archive(dir_path, out_path, signing_key=signing_key, signer=signer)
        lock_path = None
        if write_lock:
            lock_res = generate_agent_lock(dir_path)
            lock_path = write_agent_lock(dir_path, lock_res['lock'])
    except Exception as e:
        if json_out:
            _json_print({'ok': False, 'error': str(e)})
        else:
            _cli_line(f'agent package build failed: {e}', kind='error', file=sys.stderr)
        return 1
    if json_out:
        _json_print(res)
    else:
        _cli_line('Agent package archive built', kind='ok')
        print(f"Package         : {res['name']}@{res['version']}")
        print(f"Archive         : {res['archive']}")
        print(f"SHA256          : {res['sha256']}")
        print(f"Reproducible    : {res.get('reproducible', False)}")
        if write_lock and lock_path:
            print(f"Lockfile        : {lock_path}")
    return 0


def _cmd_agent_package_publish(dir_path: str, online: bool, registry: str | None, token: str | None, signing_key: str | None = None, signer: str | None = None, private: bool = False, write_lock: bool = False, json_out: bool = False) -> int:
    if isinstance(signing_key, bool) and signer is None and json_out is False:
        json_out = signing_key
        signing_key = None
    try:
        if write_lock:
            lock_res = generate_agent_lock(dir_path)
            write_agent_lock(dir_path, lock_res['lock'])
        res = publish_agent_remote(dir_path, registry=registry, token=token, signing_key=signing_key, signer=signer, private=private) if online else publish_agent_from_dir(dir_path, signing_key=signing_key, signer=signer)
    except Exception as e:
        res = {'ok': False, 'error': str(e)}
    if json_out:
        _json_print(res)
    else:
        if res.get('ok', True) and not res.get('error'):
            _cli_line('Agent package published', kind='ok')
            print(f"Package         : {res.get('name')}@{res.get('version')}")
            print(f"Published to    : {res.get('published_to') or (registry or pkg_get_registry_url())}")
        else:
            _cli_line(f"agent package publish failed: {res.get('error')}", kind='error', file=sys.stderr)
            if res.get('hint'):
                _cli_line(str(res['hint']), kind='hint', file=sys.stderr)
    return 0 if res.get('ok', True) and not res.get('error') else 1


def _cmd_agent_package_install(name: str | None, version: str | None, online: bool, registry: str | None, target_dir: str | None, verify_key: str | None = None, lockfile: str | None = None, frozen: bool = False, private: bool = False, json_out: bool = False) -> int:
    if isinstance(verify_key, bool) and json_out is False:
        json_out = verify_key
        verify_key = None
    try:
        if lockfile:
            res = install_agent_with_lock(lockfile, target_dir=target_dir, verify_key=verify_key, frozen=frozen)
        else:
            if not name:
                raise ValueError('name is required unless --lockfile is provided')
            res = install_agent_remote(name, version=version, registry=registry, target_dir=target_dir, verify_key=verify_key, private=private) if online else install_agent_package(name, version=version, target_dir=target_dir, verify_key=verify_key)
    except Exception as e:
        res = {'ok': False, 'error': str(e)}
    if json_out:
        _json_print(res)
    else:
        if res.get('ok'):
            _cli_line('Agent package installed', kind='ok')
            print(f"Package         : {res.get('name')}@{res.get('version')}")
            print(f"Installed to    : {res.get('installed_to')}")
        else:
            _cli_line(f"agent package install failed: {res.get('error')}", kind='error', file=sys.stderr)
            if res.get('hint'):
                _cli_line(str(res['hint']), kind='hint', file=sys.stderr)
    return 0 if res.get('ok') else 1




def _print_graph(node: dict[str, Any], indent: int = 0) -> None:
    prefix = '  ' * indent + '- '
    label = f"{node.get('name')}@{node.get('version', '?')}"
    if node.get('constraint'):
        label += f" ({node['constraint']})"
    if node.get('error'):
        label += f" ERROR={node['error']}"
    if node.get('cycle'):
        label += ' [cycle]'
    print(prefix + label)
    for child in node.get('dependencies') or []:
        _print_graph(child, indent + 1)


def _cmd_agent_package_graph(ref: str, json_out: bool) -> int:
    try:
        res = agent_dependency_graph(ref)
    except Exception as e:
        res = {'ok': False, 'error': str(e)}
    if json_out:
        _json_print(res)
    else:
        if not res.get('ok'):
            _cli_line(f"agent package graph failed: {res.get('error')}", kind='error', file=sys.stderr)
            return 1
        _cli_line('Agent dependency graph', kind='ok')
        _print_graph(res['graph'])
    return 0 if res.get('ok') else 1

def _cmd_agent_package_search(query: str, online: bool, registry: str | None, private: bool = False, json_out: bool = False) -> int:
    if isinstance(private, bool) and private is True and json_out is False:
        # backward compatibility with older helper signature (..., json_out=True)
        json_out = True
        private = False
    try:
        res = search_agent_remote(query, registry=registry, private=private) if online else search_agent_local(query)
    except Exception as e:
        res = {'ok': False, 'error': str(e)}
    if json_out:
        _json_print(res)
    else:
        items = list(res.get('items') or [])
        if not res.get('ok', True):
            _cli_line(f"agent package search failed: {res.get('error')}", kind='error', file=sys.stderr)
            return 1
        _cli_line(f"Found {len(items)} agent package(s)", kind='ok')
        for item in items:
            print(f"- {item.get('name')}@{item.get('version', '?')} [{', '.join(item.get('tags') or [])}] model={item.get('model', 'rule-based')}")
    return 0


def _resolve_agent_package_ref(package_or_dir: str) -> str:
    p = Path(package_or_dir)
    if p.exists():
        return str(p)
    installed = load_installed_agent(package_or_dir)
    if installed:
        return str(installed.root)
    return package_or_dir


def _cmd_agent_prompt(path: str, task: str, json_out: bool) -> int:
    runtime = _make_agent_runtime('rule-based', '.mellow/agent_memory.jsonl', '.mellow/agent_observability.jsonl')
    rendered = render_prompt_file(path, _agent_prompt_context(task, runtime))
    if json_out:
        _json_print({'ok': True, 'path': path, 'task': task, 'rendered': rendered})
    else:
        print(rendered)
    return 0


def _cmd_agent_trace(path: str, json_out: bool) -> int:
    events = read_observation_file(path)
    summary = {'count': len(events), 'kinds': {}, 'run_ids': sorted({e.get('run_id') for e in events if e.get('run_id')})}
    for evt in events:
        kind = str(evt.get('kind', 'unknown'))
        summary['kinds'][kind] = summary['kinds'].get(kind, 0) + 1
    if json_out:
        _json_print({'ok': True, 'summary': summary, 'events': events[-20:]})
    else:
        _cli_line(f"Trace loaded: {len(events)} event(s)", kind='ok')
        print('Kinds           : ' + json.dumps(summary['kinds'], ensure_ascii=False))
        if summary['run_ids']:
            print('Run IDs         : ' + ', '.join(summary['run_ids']))
    return 0


def _cmd_agent_preview(ref: str, json_out: bool) -> int:
    pkg = load_agent_package(_resolve_agent_package_ref(ref))
    payload = {
        'ok': True,
        'name': pkg.name,
        'version': pkg.version,
        'model': pkg.model,
        'prompt_file': pkg.prompt_file,
        'tool_manifest': pkg.tool_manifest,
        'tags': pkg.tags,
        'dependencies': pkg.dependencies,
    }
    if json_out:
        _json_print(payload)
    else:
        _cli_line(f"Agent preview: {pkg.name}", kind='ok')
        for key, value in payload.items():
            if key != 'ok':
                print(f"{key:15}: {json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value}")
    return 0


def _cmd_agent_prompt_debug(path: str, task: str, json_out: bool) -> int:
    runtime = _make_agent_runtime('rule-based', '.mellow/agent_memory.jsonl', '.mellow/agent_observability.jsonl')
    context = _agent_prompt_context(task, runtime)
    rendered = render_prompt_file(path, context)
    payload = {'ok': True, 'path': path, 'task': task, 'variables': sorted(context.keys()), 'rendered': rendered}
    if json_out:
        _json_print(payload)
    else:
        _cli_line('Prompt debug', kind='ok')
        print('Variables       : ' + ', '.join(payload['variables']))
        print(rendered)
    return 0


def _cmd_playground(host: str, port: int, build_only: bool, out: str, json_out: bool) -> int:
    target = build_static_playground(out)
    payload = {
        "ok": True,
        "path": str(target.resolve()),
        "url": None if build_only else f"http://{host}:{port}/",
        "served": not build_only,
        "host": host,
        "port": int(port),
    }
    if build_only:
        if json_out:
            _json_print(payload)
        else:
            _cli_line(f"Playground assets written to {target}", kind="ok")
        return 0

    server = serve_playground(host=host, port=port)
    if json_out:
        _json_print(payload)
        return 0
    _cli_line(f"Mellow Playground serving at {payload['url']}", kind='ok')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def _cmd_agent_playground(out: str, serve: bool, port: int, json_out: bool) -> int:
    build_only = not bool(serve)
    return _cmd_playground("127.0.0.1", port, build_only, str(Path(out).parent), json_out)


def _cmd_agent_serve(package: str | None, host: str, port: int, json_out: bool, deployment_manifest: str | None = None) -> int:
    manifest = load_deployment_manifest(deployment_manifest) if deployment_manifest else None
    effective_host = str((manifest or {}).get('runtime', {}).get('host', host))
    effective_port = int((manifest or {}).get('runtime', {}).get('port', port))
    effective_package = package
    if manifest and not effective_package:
        candidate = (Path(deployment_manifest).parent / 'package').resolve()
        if candidate.exists():
            effective_package = str(candidate)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            health_path = str((manifest or {}).get('runtime', {}).get('healthcheck', 'GET /health')).split(' ', 1)[-1]
            if self.path == health_path:
                body = json.dumps({'ok': True, 'provider': (manifest or {}).get('runtime', {}).get('provider', 'local-http')}).encode('utf-8')
                self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(body))); self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404); self.end_headers()

        def do_POST(self):
            run_path = str((manifest or {}).get('runtime', {}).get('entrypoint', 'POST /run')).split(' ', 1)[-1]
            if self.path != run_path:
                self.send_response(404); self.end_headers(); return
            length = int(self.headers.get('Content-Length', '0') or '0')
            raw = self.rfile.read(length) if length else b'{}'
            try:
                data = json.loads(raw.decode('utf-8'))
            except Exception:
                data = {}
            task = str(data.get('task', 'demo task'))
            if effective_package:
                payload = {'ok': _run_agent_package(effective_package, task, json_out=True) == 0, 'task': task, 'deployment_manifest': deployment_manifest}
            else:
                runtime = _make_agent_runtime('rule-based', '.mellow/agent_memory.jsonl', '.mellow/agent_observability.jsonl')
                res = runtime.run(task)
                payload = {'ok': True, 'task': task, 'answer': res.answer, 'deployment_manifest': deployment_manifest}
            body = json.dumps(payload).encode('utf-8')
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(body))); self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            return

    if json_out:
        _json_print({'ok': True, 'host': effective_host, 'port': effective_port, 'package': effective_package, 'deployment_manifest': deployment_manifest})
        return 0
    _cli_line(f'Hosted agent server listening on http://{effective_host}:{effective_port}', kind='ok')
    server = ThreadingHTTPServer((effective_host, effective_port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def _cmd_agent_marketplace(query: str, online: bool, registry: str | None, json_out: bool) -> int:
    res = search_agent_remote(query, registry=registry) if online else search_agent_local(query)
    payload = {'ok': True, 'query': query, 'items': list(res.get('items') or []), 'source': 'remote' if online else 'local'}
    if json_out:
        _json_print(payload)
    else:
        _cli_line(f"Marketplace results ({payload['source']})", kind='ok')
        for item in payload['items']:
            print(f"- {item.get('name')}@{item.get('version', '?')} :: model={item.get('model', 'rule-based')} tags={','.join(item.get('tags') or [])}")
    return 0


def _cmd_agent_deploy(ref: str, out: str, json_out: bool, public_url: str | None = None, host: str | None = None, port: int | None = None, target: str | None = None, control_plane: str | None = None) -> int:
    pkg_root = _resolve_agent_package_ref(ref)
    pkg = load_agent_package(pkg_root)
    out_dir = Path(out) / pkg.name.replace('.', '_')
    bundle = write_deployment_bundle(pkg_root, out_dir, public_url=public_url, host=host, port=port, target=target, control_plane=control_plane)
    reg = sync_deployment(bundle['manifest'], out_dir, control_plane=control_plane, manifest_path=bundle['manifest_path']) if control_plane else register_deployment(bundle['manifest'], out_dir, manifest_path=bundle['manifest_path'])
    payload = {'ok': True, 'out_dir': str(out_dir.resolve()), 'manifest': bundle['manifest'], 'manifest_path': bundle['manifest_path'], 'start_script': bundle['start_script'], 'adapters': bundle.get('adapters', {}), 'deployment': reg.get('deployment'), 'revision': reg.get('revision'), 'remote': reg.get('remote', False)}
    if json_out:
        _json_print(payload)
    else:
        _cli_line(f"Deployment bundle written to {out_dir}", kind='ok')
        print(f"Manifest        : {bundle['manifest_path']}")
        print(f"Start script    : {bundle['start_script']}")
        print(f"Target          : {bundle['manifest']['runtime']['provider']}")
        if bundle.get('adapters'):
            print(f"Adapters        : {json.dumps(bundle['adapters'], ensure_ascii=False)}")
        if reg.get('deployment'):
            print(f"Deployment ID   : {reg['deployment']['id']}")
        if reg.get('revision'):
            print(f"Revision        : {reg['revision']['revision']}")
        if reg.get('remote'):
            print('Control plane   : remote sync completed')
    return 0


def _cmd_agent_control_plane(action: str, ref: str | None, manifest: str | None, bundle_dir: str, control_plane: str | None, json_out: bool, token: str | None = None, revision: int | None = None, revision_notes: str | None = None, canary_percent: int | None = None, stable_percent: int | None = None, canary_split: int | None = None, rules_file: str | None = None, metrics: dict[str, Any] | None = None) -> int:
    if action == 'register' and manifest:
        payload = register_deployment(load_deployment_manifest(manifest), bundle_dir, control_plane=control_plane, manifest_path=manifest, revision_notes=revision_notes)
    elif action == 'sync' and manifest:
        payload = sync_deployment(load_deployment_manifest(manifest), bundle_dir, control_plane=control_plane, api_token=token, manifest_path=manifest, revision_notes=revision_notes)
    elif action == 'status' and ref:
        payload = get_deployment_status(ref, control_plane=control_plane, api_token=token)
    elif action == 'revisions' and ref:
        payload = list_revisions(ref, control_plane=control_plane, api_token=token)
    elif action == 'rollout' and ref and revision is not None:
        payload = rollout_revision(ref, revision, control_plane=control_plane, api_token=token, canary_percent=canary_percent)
    elif action == 'health' and ref:
        payload = run_health_check(ref, control_plane=control_plane, api_token=token)
    elif action == 'traffic' and ref and stable_percent is not None and canary_split is not None:
        payload = update_traffic_split(ref, stable_percent, canary_split, control_plane=control_plane, api_token=token)
    elif action == 'rollback' and ref:
        payload = rollback_deployment(ref, control_plane=control_plane, api_token=token, revision=revision)
    elif action == 'metrics' and ref:
        clean_metrics = {k: v for k, v in (metrics or {}).items() if v is not None}
        payload = record_deployment_metrics(ref, clean_metrics, control_plane=control_plane, api_token=token) if clean_metrics else get_deployment_metrics(ref, control_plane=control_plane, api_token=token)
    elif action == 'signals' and ref:
        payload = get_autoscaling_signals(ref, control_plane=control_plane, api_token=token)
    elif action == 'alert-rules' and ref:
        if rules_file:
            raw = json.loads(Path(rules_file).read_text(encoding='utf-8'))
            rules = raw.get('rules') if isinstance(raw, dict) else raw
            payload = set_alert_rules(ref, list(rules or []), control_plane=control_plane, api_token=token)
        else:
            status = get_deployment_status(ref, control_plane=control_plane, api_token=token)
            if status.get('ok'):
                dep = status['deployment']
                payload = {'ok': True, 'deployment': dep, 'rules': list(dep.get('alert_rules') or []), 'alerts': dep.get('alerts') or {'status': 'ok', 'count': 0}}
            else:
                payload = status
    elif action == 'alerts' and ref:
        payload = evaluate_alerts(ref, control_plane=control_plane, api_token=token)
    else:
        payload = list_deployments(control_plane=control_plane, api_token=token)
    if json_out:
        _json_print(payload)
    else:
        if action == 'status' and payload.get('ok'):
            dep = payload['deployment']
            _cli_line(f"Hosted deployment: {dep['id']}", kind='ok')
            print(f"Package         : {dep['package']['name']}@{dep['package']['version']}")
            print(f"Provider        : {dep['provider']}")
            print(f"Status          : {dep['status']}")
            print(f"Current rev     : {dep.get('current_revision')}")
            print(f"Latest rev      : {dep.get('latest_revision')}")
            if dep.get('traffic_split'):
                print(f"Traffic split   : {json.dumps(dep.get('traffic_split'), ensure_ascii=False)}")
            if dep.get('health'):
                print(f"Health          : {json.dumps(dep.get('health'), ensure_ascii=False)}")
            print(f"Bundle dir      : {dep['bundle_dir']}")
        elif action == 'revisions' and payload.get('ok'):
            _cli_line(f"Revisions: {payload.get('count', 0)}", kind='ok')
            if payload.get('traffic_split'):
                print('Traffic split   : ' + json.dumps(payload.get('traffic_split'), ensure_ascii=False))
            for item in payload.get('items') or []:
                marker = '*' if int(item.get('revision', 0)) == int(payload.get('current_revision') or 0) else ' '
                print(f"{marker} rev {item['revision']} :: status={item.get('status')} created={item.get('created_at')} notes={item.get('notes') or ''}")
        elif action == 'health' and payload.get('ok'):
            _cli_line(f"Health check ok for {payload['deployment']['package']['name']}", kind='ok')
            print('Health          : ' + json.dumps(payload.get('health'), ensure_ascii=False))
        elif action == 'traffic' and payload.get('ok'):
            _cli_line(f"Traffic updated for {payload['deployment']['package']['name']}", kind='ok')
            print('Traffic split   : ' + json.dumps(payload.get('traffic_split'), ensure_ascii=False))
        elif action == 'rollout' and payload.get('ok'):
            dep = payload['deployment']
            _cli_line(f"Rolled out revision {payload['revision']['revision']} for {dep['package']['name']}", kind='ok')
            print(f"Deployment ID   : {dep['id']}")
            print(f"Current rev     : {dep.get('current_revision')}")
            print(f"Status          : {dep.get('status')}")
            if dep.get('traffic_split'):
                print('Traffic split   : ' + json.dumps(dep.get('traffic_split'), ensure_ascii=False))
        elif action == 'rollback' and payload.get('ok'):
            dep = payload['deployment']
            _cli_line(f"Rolled back deployment {dep['package']['name']}", kind='ok')
            print(f"Deployment ID   : {dep['id']}")
            print(f"Current rev     : {dep.get('current_revision')}")
            print(f"Status          : {dep.get('status')}")
        elif action == 'metrics' and payload.get('ok'):
            dep = payload['deployment']
            _cli_line(f"Metrics for {dep['package']['name']}", kind='ok')
            print('Metrics         : ' + json.dumps(payload.get('metrics'), ensure_ascii=False))
            if payload.get('autoscaling'):
                print('Autoscaling     : ' + json.dumps(payload.get('autoscaling'), ensure_ascii=False))
            if payload.get('alerts'):
                print('Alerts          : ' + json.dumps(payload.get('alerts'), ensure_ascii=False))
        elif action == 'signals' and payload.get('ok'):
            dep = payload['deployment']
            _cli_line(f"Autoscaling signals for {dep['package']['name']}", kind='ok')
            print('Signals         : ' + json.dumps(payload.get('autoscaling'), ensure_ascii=False))
        elif action == 'alert-rules' and payload.get('ok'):
            dep = payload['deployment']
            _cli_line(f"Alert rules for {dep['package']['name']}", kind='ok')
            print('Rules           : ' + json.dumps(payload.get('rules') or [], ensure_ascii=False))
            print('Alerts          : ' + json.dumps(payload.get('alerts') or {'status': 'ok', 'count': 0}, ensure_ascii=False))
        elif action == 'alerts' and payload.get('ok'):
            dep = payload['deployment']
            _cli_line(f"Alert evaluation for {dep['package']['name']}", kind='ok')
            print('Alerts          : ' + json.dumps(payload.get('alerts'), ensure_ascii=False))
            if payload.get('rules') is not None:
                print('Rules           : ' + json.dumps(payload.get('rules'), ensure_ascii=False))
        elif action in ('status','revisions','rollout','health','traffic','rollback','metrics','signals','alert-rules','alerts'):
            _cli_line(payload.get('error', f'{action} failed'), kind='error', file=sys.stderr)
        else:
            items = payload.get('items') or ([payload.get('deployment')] if payload.get('deployment') else [])
            _cli_line(f"Hosted deployments: {len(items)}", kind='ok')
            for item in items:
                print(f"- {item['id']} :: {item['package']['name']}@{item['package']['version']} [{item['provider']}] status={item['status']} current_rev={item.get('current_revision')}")
    return 0 if payload.get('ok') else 1


def _cmd_agent_secret(action: str, name: str | None, value: str | None, json_out: bool, scopes: list[str] | None = None, description: str | None = None) -> int:
    if action == 'set' and name is not None and value is not None:
        set_secret(name, value, scopes=scopes or ['*'], description=description)
        payload = {'ok': True, 'name': name, 'scopes': scopes or ['*']}
    elif action == 'remove' and name is not None:
        payload = {'ok': remove_secret(name), 'name': name}
    else:
        payload = {'ok': True, 'items': list_secrets()}
    if json_out:
        _json_print(payload)
    else:
        if 'items' in payload:
            _cli_line(f"Stored secrets: {len(payload['items'])}", kind='ok')
            for item in payload['items']:
                print(f"- {item['name']} = {item['masked']} scopes={','.join(item.get('scopes') or ['*'])}")
        elif payload.get('ok'):
            _cli_line(f"Secret {action} ok: {name}", kind='ok')
        else:
            _cli_line(f"Secret {action} failed: {name}", kind='error', file=sys.stderr)
    return 0 if payload.get('ok') else 1


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


def _cmd_agent_policy_sign(path: str, key: str, signer: str | None, json_out: bool) -> int:
    p = Path(path)
    payload = sign_capability_policy(json.loads(p.read_text(encoding='utf-8')), key, signer=signer)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
    res = {'ok': True, 'path': str(p), 'signed_by': signer}
    if json_out:
        _json_print(res)
    else:
        _cli_line(f'Capability policy signed: {p}', kind='ok')
    return 0


def _cmd_agent_policy_verify(path: str, key: str, json_out: bool) -> int:
    try:
        payload = load_signed_policy(path, verify_key=key)
        res = {'ok': True, 'path': str(path), 'signed_by': payload.get('signed_by')}
    except Exception as e:
        res = {'ok': False, 'path': str(path), 'error': str(e)}
    if json_out:
        _json_print(res)
    else:
        if res.get('ok'):
            _cli_line(f'Capability policy verified: {path}', kind='ok')
        else:
            _cli_line(f"Capability policy verify failed: {res.get('error')}", kind='error', file=sys.stderr)
    return 0 if res.get('ok') else 1


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



def _scheduled_job_callback(job: dict[str, Any]) -> dict[str, Any]:
    if str(job.get('kind') or 'run') == 'workflow':
        runtime = _make_agent_runtime(str(job.get('model') or 'rule-based'), str(job.get('memory') or '.mellow/agent_memory.jsonl'), str(job.get('obs') or '.mellow/agent_observability.jsonl'), ['search.docs', 'time.now'], [], job.get('rag_file'), sandbox=bool(job.get('sandbox')), allow_caps=list(job.get('allow_caps') or []), secrets=list(job.get('secrets') or []))
        steps = [
            WorkflowStep('recall-memory', 'memory', retries=int(job.get('retries') or 0), timeout_ms=job.get('timeout_ms')),
            WorkflowStep('retrieve-context', 'rag', retries=int(job.get('retries') or 0), timeout_ms=job.get('timeout_ms')),
        ]
        if job.get('parallel'):
            steps.append(WorkflowStep('parallel-context', 'parallel', {'steps': [
                {'name': 'search-docs', 'kind': 'tool', 'payload': {'tool': 'search.docs', 'input': {'query': job['task']}}, 'retries': int(job.get('retries') or 0), 'timeout_ms': job.get('timeout_ms')},
                {'name': 'stamp-time', 'kind': 'tool', 'payload': {'tool': 'time.now', 'input': {}}, 'retries': int(job.get('retries') or 0), 'timeout_ms': job.get('timeout_ms')},
            ]}, retries=int(job.get('retries') or 0), timeout_ms=job.get('timeout_ms')))
        else:
            steps.append(WorkflowStep('search-docs', 'tool', {'tool': 'search.docs', 'input': {'query': job['task']}}, retries=int(job.get('retries') or 0), timeout_ms=job.get('timeout_ms')))
        steps.append(WorkflowStep('generate-answer', 'model', retries=int(job.get('retries') or 0), timeout_ms=job.get('timeout_ms')))
        result = WorkflowRunner(runtime).run(Workflow(name=f"scheduled-{job['name']}", steps=steps), str(job['task']))
        return {'ok': True, 'kind': 'workflow', 'workflow': result}
    if job.get('package'):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = _run_agent_package(str(job['package']), str(job['task']), json_out=True, sandbox=bool(job.get('sandbox')), allow_caps=list(job.get('allow_caps') or []), secrets=list(job.get('secrets') or []), timeout_ms=job.get('timeout_ms'))
        raw = buf.getvalue().strip()
        try:
            payload = json.loads(raw.splitlines()[-1]) if raw else {'ok': code == 0}
        except Exception:
            payload = {'ok': code == 0, 'raw': raw}
        return payload
    runtime = _make_agent_runtime(str(job.get('model') or 'rule-based'), str(job.get('memory') or '.mellow/agent_memory.jsonl'), str(job.get('obs') or '.mellow/agent_observability.jsonl'), [], [], job.get('rag_file'), sandbox=bool(job.get('sandbox')), allow_caps=list(job.get('allow_caps') or []), secrets=list(job.get('secrets') or []))
    result = runtime.run(str(job['task']), timeout_ms=job.get('timeout_ms'))
    return {'ok': True, 'kind': 'run', 'answer': result.answer, 'structured': result.structured, 'run_id': result.debug.get('run_id')}


def _cmd_agent_schedule(action: str, *, name: str | None = None, cron: str | None = None, task: str | None = None, kind: str = 'run', package: str | None = None, model: str = 'rule-based', memory: str = '.mellow/agent_memory.jsonl', obs: str = '.mellow/agent_observability.jsonl', rag_file: str | None = None, retries: int = 1, timeout_ms: int | None = None, parallel: bool = False, sandbox: bool = False, allow_caps: list[str] | None = None, secrets: list[str] | None = None, backoff: dict[str, Any] | None = None, json_out: bool = False) -> int:
    if action == 'add':
        payload = add_job(str(name), str(cron), str(task), kind=kind, package=package, model=model, memory=memory, obs=obs, rag_file=rag_file, retries=retries, timeout_ms=timeout_ms, parallel=parallel, sandbox=sandbox, allow_caps=allow_caps, secrets=secrets, backoff=backoff)
    elif action == 'run-due':
        payload = run_due_jobs(callback=_scheduled_job_callback)
    else:
        payload = agent_list_jobs()
    if json_out:
        _json_print(payload)
    else:
        if action == 'add' and payload.get('ok'):
            job = payload['job']
            _cli_line('Scheduled agent job created', kind='ok')
            print(f"Job ID          : {job['id']}")
            print(f"Name            : {job['name']}")
            print(f"Cron            : {job['schedule']}")
            print(f"Next run        : {job['next_run']}")
        elif action == 'run-due' and payload.get('ok'):
            _cli_line(f"Executed {payload.get('count', 0)} scheduled job(s)", kind='ok')
            for item in payload.get('items') or []:
                print(f"- {item['name']} -> {json.dumps(item.get('result'), ensure_ascii=False)}")
        else:
            _cli_line(f"Scheduled jobs: {payload.get('count', 0)}", kind='ok')
            for item in payload.get('items') or []:
                print(f"- {item['name']} [{item['kind']}] cron={item['schedule']} next={item.get('next_run')} runs={item.get('run_count', 0)}")
    return 0 if payload.get('ok') else 1


def _parse_jsonish(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else {"value": data}
    except Exception:
        return {"raw": value}


def _parse_filters(values: list[str] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in values or []:
        raw = str(item)
        if '=' in raw:
            k, v = raw.split('=', 1)
            out[k.strip()] = v.strip()
    return out


def _build_backoff(strategy: str | None, delay_ms: int | None, max_ms: int | None) -> dict[str, Any]:
    return {
        'strategy': str(strategy or 'fixed'),
        'initial_delay_ms': max(0, int(delay_ms or 0)),
        'max_delay_ms': max(0, int(max_ms or delay_ms or 0)),
    }


def _cmd_agent_trigger(action: str, *, name: str | None = None, event: str | None = None, task: str | None = None, kind: str = 'run', package: str | None = None, model: str = 'rule-based', memory: str = '.mellow/agent_memory.jsonl', obs: str = '.mellow/agent_observability.jsonl', rag_file: str | None = None, retries: int = 1, timeout_ms: int | None = None, parallel: bool = False, sandbox: bool = False, allow_caps: list[str] | None = None, secrets: list[str] | None = None, filters: list[str] | None = None, payload: str | None = None, backoff: dict[str, Any] | None = None, json_out: bool = False) -> int:
    if action == 'add':
        data = add_trigger(str(name), str(event), str(task), kind=kind, package=package, model=model, memory=memory, obs=obs, rag_file=rag_file, retries=retries, timeout_ms=timeout_ms, parallel=parallel, sandbox=sandbox, allow_caps=allow_caps, secrets=secrets, filters=_parse_filters(filters), backoff=backoff)
    elif action == 'emit':
        data = emit_event(str(event), _parse_jsonish(payload))
    else:
        data = list_triggers()
    if json_out:
        _json_print(data)
    else:
        if action == 'add' and data.get('ok'):
            trig = data['trigger']
            _cli_line('Event trigger created', kind='ok')
            print(f"Trigger ID       : {trig['id']}")
            print(f"Name             : {trig['name']}")
            print(f"Event            : {trig['event']}")
        elif action == 'emit' and data.get('ok'):
            _cli_line(f"Queued {data.get('matched', 0)} job(s) for event {data.get('event')}", kind='ok')
        else:
            _cli_line(f"Event triggers: {data.get('count', 0)}", kind='ok')
            for item in data.get('items') or []:
                print(f"- {item['name']} event={item['event']} kind={item['kind']} runs={item.get('run_count', 0)}")
    return 0 if data.get('ok') else 1


def _cmd_agent_webhook(action: str, *, name: str | None = None, event: str | None = None, task: str | None = None, token: str | None = None, kind: str = 'run', package: str | None = None, model: str = 'rule-based', memory: str = '.mellow/agent_memory.jsonl', obs: str = '.mellow/agent_observability.jsonl', rag_file: str | None = None, retries: int = 1, timeout_ms: int | None = None, parallel: bool = False, sandbox: bool = False, allow_caps: list[str] | None = None, secrets: list[str] | None = None, payload: str | None = None, host: str = '127.0.0.1', port: int = 8788, token_header: str = 'X-Mellow-Webhook-Token', enable_job_api: bool = True, backoff: dict[str, Any] | None = None, json_out: bool = False) -> int:
    if action == 'add':
        data = add_webhook(str(name), str(event), token=token, task=str(task), kind=kind, package=package, model=model, memory=memory, obs=obs, rag_file=rag_file, retries=retries, timeout_ms=timeout_ms, parallel=parallel, sandbox=sandbox, allow_caps=allow_caps, secrets=secrets, backoff=backoff)
    elif action == 'receive':
        data = receive_webhook(str(name), _parse_jsonish(payload), token=token)
    elif action == 'serve':
        data = start_webhook_server(host=host, port=port, token_header=token_header, enable_job_api=enable_job_api)
    elif action == 'status':
        data = read_webhook_server_status()
    else:
        data = list_webhooks()
    if json_out:
        _json_print(data)
    else:
        if action == 'add' and data.get('ok'):
            hook = data.get('webhook') or {}
            _cli_line('Webhook job created', kind='ok')
            print(f"Name             : {hook.get('name')}")
            print(f"Event            : {hook.get('event')}")
            print(f"Token            : {hook.get('token')}")
        elif action == 'receive' and data.get('ok'):
            _cli_line(f"Webhook accepted, queued {data.get('matched', 0)} job(s)", kind='ok')
        elif action == 'serve' and data.get('ok'):
            _cli_line(f"Webhook server stopped: {data.get('url')}", kind='ok')
        elif action == 'status' and data.get('ok'):
            _cli_line('Webhook server status', kind='ok')
            print('Status          : ' + json.dumps(data, ensure_ascii=False))
        else:
            _cli_line(f"Webhooks: {data.get('count', 0)}", kind='ok')
            for item in data.get('items') or []:
                print(f"- {item['name']} event={item['event']} token={item['token']}")
    return 0 if data.get('ok') else 1


def _cmd_agent_queue(action: str, *, limit: int | None = None, item_id: str | None = None, workers: int = 1, json_out: bool = False) -> int:
    if action == 'run':
        data = drain_queue(limit=limit, callback=_scheduled_job_callback, workers=workers)
    elif action == 'stats':
        data = queue_stats()
    elif action == 'dead-letter':
        data = list_dead_letter()
    elif action == 'retry':
        data = retry_queue_item(str(item_id))
    elif action == 'log':
        data = read_queue_log(limit=limit or 50)
    else:
        data = list_queue()
    if json_out:
        _json_print(data)
    else:
        if action == 'run' and data.get('ok'):
            _cli_line(f"Processed {data.get('count', 0)} queued job(s)", kind='ok')
        elif action == 'stats' and data.get('ok'):
            _cli_line('Queue stats', kind='ok')
            print('Status          : ' + json.dumps(data, ensure_ascii=False))
        elif action == 'dead-letter' and data.get('ok'):
            _cli_line(f"Dead-letter items: {data.get('count', 0)}", kind='ok')
            for item in data.get('items') or []:
                print(f"- {item['id']} name={item.get('name')} error={item.get('last_error')}")
        elif action == 'retry' and data.get('ok'):
            _cli_line(f"Requeued dead-letter item {data.get('item', {}).get('id')}", kind='ok')
        elif action == 'log' and data.get('ok'):
            _cli_line(f"Queue log entries: {data.get('count', 0)}", kind='ok')
            for item in data.get('items') or []:
                print(json.dumps(item, ensure_ascii=False))
        else:
            _cli_line(f"Queue items: {data.get('count', 0)} (queued={data.get('queued', 0)}, done={data.get('done', 0)}, retry={data.get('retry', 0)}, dead-letter={data.get('dead_letter', 0)})", kind='ok')
            for item in data.get('items') or []:
                print(f"- {item['name']} status={item['status']} source={item.get('source')} event={item.get('event')}")
    return 0 if data.get('ok') else 1


def _cmd_agent_jobs(action: str, *, task: str | None = None, name: str | None = None, kind: str = 'run', package: str | None = None, model: str = 'rule-based', memory: str = '.mellow/agent_memory.jsonl', obs: str = '.mellow/agent_observability.jsonl', rag_file: str | None = None, retries: int = 1, timeout_ms: int | None = None, parallel: bool = False, sandbox: bool = False, allow_caps: list[str] | None = None, secrets: list[str] | None = None, payload: str | None = None, host: str = '127.0.0.1', port: int = 8788, job_id: str | None = None, backoff: dict[str, Any] | None = None, json_out: bool = False) -> int:
    if action == 'submit':
        data = submit_job(str(task), name=name, kind=kind, package=package, model=model, memory=memory, obs=obs, rag_file=rag_file, retries=retries, timeout_ms=timeout_ms, parallel=parallel, sandbox=sandbox, allow_caps=allow_caps, secrets=secrets, backoff=backoff, payload=_parse_jsonish(payload))
    elif action == 'get':
        data = get_queue_item(str(job_id))
    elif action == 'serve':
        data = start_webhook_server(host=host, port=port, enable_job_api=True)
    elif action == 'status':
        data = read_job_api_status()
    else:
        data = list_queue()
    if json_out:
        _json_print(data)
    else:
        if action == 'submit' and data.get('ok'):
            item = data.get('item') or {}
            _cli_line(f"Job submitted: {item.get('id')}", kind='ok')
            print('Status          : ' + json.dumps(item, ensure_ascii=False))
        elif action == 'get' and data.get('ok'):
            _cli_line(f"Job {job_id}", kind='ok')
            print('Status          : ' + json.dumps(data.get('item'), ensure_ascii=False))
        elif action == 'serve' and data.get('ok'):
            _cli_line(f"Job API server stopped: {data.get('url')}", kind='ok')
        elif action == 'status' and data.get('ok'):
            _cli_line('Job API server status', kind='ok')
            print('Status          : ' + json.dumps(data, ensure_ascii=False))
        else:
            _cli_line(f"Jobs in queue: {data.get('count', 0)}", kind='ok')
            for item in data.get('items') or []:
                print(f"- {item.get('id')} name={item.get('name')} status={item.get('status')}")
    return 0 if data.get('ok') else 1


def _cmd_agent_runner(action: str, *, interval_s: float = 1.0, iterations: int = 1, queue_backed: bool = False, queue_limit: int | None = None, workers: int = 1, json_out: bool = False) -> int:
    payload = run_background_runner(interval_s=interval_s, iterations=iterations, callback=_scheduled_job_callback, queue_backed=queue_backed, queue_limit=queue_limit, workers=workers) if action == 'start' else read_runner_status()
    if json_out:
        _json_print(payload)
    else:
        if action == 'start' and payload.get('ok'):
            _cli_line('Background agent runner finished', kind='ok')
            print('Status          : ' + json.dumps(payload, ensure_ascii=False))
        else:
            _cli_line('Background agent runner status', kind='ok')
            print('Status          : ' + json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get('ok', True) else 1
