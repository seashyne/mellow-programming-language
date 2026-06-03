from __future__ import annotations

import json
from pathlib import Path

from mellowlang.cli.main import _cmd_agent_demo, _cmd_agent_inspect_log, _cmd_agent_run, _cmd_agent_workflow


def test_agent_demo_json(capsys):
    assert _cmd_agent_demo(True) == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data['version'] in {'1.7.4', '1.8.0'}
    assert data['focus']['agent_system'] == 5


def test_agent_run_and_observability(tmp_path: Path):
    memory = tmp_path / 'memory.jsonl'
    obs = tmp_path / 'obs.jsonl'
    rag = tmp_path / 'rag.txt'
    rag.write_text('Mellow agents use retrieval and tools.\n', encoding='utf-8')
    code = _cmd_agent_run('plan a workflow with tools', 'rule-based', str(memory), str(obs), ['search.docs'], [], [], str(rag), 'auto', True)
    assert code == 0
    assert obs.exists()
    rows = [json.loads(line) for line in obs.read_text(encoding='utf-8').splitlines() if line.strip()]
    assert any(row['kind'] == 'agent.start' for row in rows)
    assert any(row['kind'] == 'tool.call' for row in rows)


def test_agent_workflow_and_inspect_log(tmp_path: Path, capsys):
    memory = tmp_path / 'memory.jsonl'
    obs = tmp_path / 'obs.jsonl'
    rag = tmp_path / 'rag.txt'
    rag.write_text('Workflow retrieval should provide context.\n', encoding='utf-8')
    assert _cmd_agent_workflow('design an agent workflow', 'rule-based', str(memory), str(obs), str(rag), True) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['workflow'] == 'default-agent-workflow'
    # create a small log file and inspect it
    obs.write_text('\n'.join([
        json.dumps({'kind': 'agent.start', 'payload': {'task': 'x'}}),
        json.dumps({'kind': 'agent.finish', 'payload': {'answer': 'y'}}),
    ]), encoding='utf-8')
    assert _cmd_agent_inspect_log(str(obs), True) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected['count'] == 2
