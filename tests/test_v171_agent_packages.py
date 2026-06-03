
from __future__ import annotations

import json
from pathlib import Path

from mellowlang.cli.main import _cmd_agent_package_init, _run_agent_package, _cmd_agent_prompt, _cmd_agent_run


def test_agent_package_init_and_run(tmp_path: Path, capsys):
    pkg = tmp_path / 'agentpkg'
    assert _cmd_agent_package_init(str(pkg), 'demo.agent', False, True) == 0
    init_payload = json.loads(capsys.readouterr().out)
    assert init_payload['ok'] is True
    assert (pkg / 'agent.toml').exists()
    assert _run_agent_package(str(pkg), 'plan a workflow', json_out=True) == 0
    run_payload = json.loads(capsys.readouterr().out)
    assert run_payload['package'] == 'demo.agent'
    assert 'Tools available' in run_payload['prompt']


def test_prompt_dsl_render(tmp_path: Path, capsys):
    prompt = tmp_path / 'demo.prompt'
    prompt.write_text('Task={{ task }}\n{% if tools %}{% for tool in tools %}{{ tool.name }} {% endfor %}{% endif %}', encoding='utf-8')
    assert _cmd_agent_prompt(str(prompt), 'ship agent package', True) == 0
    payload = json.loads(capsys.readouterr().out)
    assert 'Task=ship agent package' in payload['rendered']
    assert 'search.docs' in payload['rendered']


def test_agent_run_with_manifest_and_prompt(tmp_path: Path, capsys):
    prompt = tmp_path / 'demo.prompt'
    prompt.write_text('Package prompt for {{ task }}', encoding='utf-8')
    manifest = tmp_path / 'manifest.toml'
    manifest.write_text('''[[tools]]
name="docs"
description="Docs search"
builtin="search.docs"
policy="allow"
''', encoding='utf-8')
    memory = tmp_path / 'memory.jsonl'
    obs = tmp_path / 'obs.jsonl'
    assert _cmd_agent_run('retrieve docs', 'rule-based', str(memory), str(obs), ['docs'], ['docs'], [], None, str(prompt), str(manifest), None, 'auto', True) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['tool_manifest'] == str(manifest)
    assert payload['prompt'] == 'Package prompt for retrieve docs'
