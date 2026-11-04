"""Reading an agent definition back: prompt render, prompt debug, trace and preview."""

from __future__ import annotations

import json

from ...common import _cli_line, _json_print
from .deps import (
    render_prompt_file, load_agent_package, read_observation_file,
)
from .support import _agent_prompt_context, _make_agent_runtime, _resolve_agent_package_ref

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
