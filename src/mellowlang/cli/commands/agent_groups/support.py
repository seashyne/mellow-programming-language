"""The helpers more than one agent command group needs: the runtime builder, the package-mode runner, the graph printer and the value parsers."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from ...common import _cli_line, _json_print
from .deps import (
    AgentRuntime, MemoryStore, ObservationLog, PolicyEngine,
    SimpleRAGIndex, builtin_tool_registry, resolve_model_adapter, render_prompt_file,
    load_tool_manifest, load_agent_package, apply_tool_manifest, load_installed_agent,
    SandboxConfig, load_signed_policy,
)

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

def _resolve_agent_package_ref(package_or_dir: str) -> str:
    p = Path(package_or_dir)
    if p.exists():
        return str(p)
    installed = load_installed_agent(package_or_dir)
    if installed:
        return str(installed.root)
    return package_or_dir

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
