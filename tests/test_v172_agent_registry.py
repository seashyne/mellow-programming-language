from __future__ import annotations

import json
from pathlib import Path

from mellowlang.cli.main import (
    _cmd_agent_package_build,
    _cmd_agent_package_init,
    _cmd_agent_package_install,
    _cmd_agent_package_publish,
    _cmd_agent_package_search,
    _run_agent_package,
)
from mellowlang.agents.registry import AGENT_INSTALLED_ROOT, AGENT_REGISTRY_ROOT


def test_agent_registry_build_publish_install_and_run(tmp_path: Path, capsys):
    pkg = tmp_path / 'agentpkg'
    assert _cmd_agent_package_init(str(pkg), 'demo.agent', False, True) == 0
    capsys.readouterr()

    assert _cmd_agent_package_build(str(pkg), None, True) == 0
    built = json.loads(capsys.readouterr().out)
    assert built['archive'].endswith('.magent')

    assert _cmd_agent_package_publish(str(pkg), False, None, None, True) == 0
    published = json.loads(capsys.readouterr().out)
    assert published['ok'] is True
    assert (AGENT_REGISTRY_ROOT / 'demo.agent' / '0.1.0').exists()

    assert _cmd_agent_package_search('demo', False, None, True) == 0
    search = json.loads(capsys.readouterr().out)
    assert any(item['name'] == 'demo.agent' for item in search['items'])

    assert _cmd_agent_package_install('demo.agent', None, False, None, None, True) == 0
    installed = json.loads(capsys.readouterr().out)
    assert installed['ok'] is True
    assert (AGENT_INSTALLED_ROOT / 'demo.agent' / '0.1.0' / 'package' / 'agent.toml').exists()

    assert _run_agent_package('demo.agent', 'plan a launch', json_out=True) == 0
    run = json.loads(capsys.readouterr().out)
    assert run['package'] == 'demo.agent'
    assert 'plan a launch' in run['prompt']
