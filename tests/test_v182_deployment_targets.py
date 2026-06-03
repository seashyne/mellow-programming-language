
from pathlib import Path
from mellowlang.agents.packages import init_agent_package
from mellowlang.agents.deployment import write_deployment_bundle
from mellowlang.agents.control_plane import get_deployment_status, list_deployments


def test_write_docker_bundle(tmp_path: Path):
    pkg_dir = tmp_path / 'agent'
    init_agent_package(pkg_dir, name='demo.agent')
    out = tmp_path / 'deploy'
    res = write_deployment_bundle(pkg_dir, out, target='docker')
    assert Path(res['manifest_path']).exists()
    assert (out / 'Dockerfile').exists()
    assert res['manifest']['runtime']['provider'] == 'docker'


def test_control_plane_registers_on_bundle(tmp_path: Path):
    pkg_dir = tmp_path / 'agent'
    init_agent_package(pkg_dir, name='status.agent')
    out = tmp_path / 'deploy2'
    res = write_deployment_bundle(pkg_dir, out, target='vercel')
    from mellowlang.agents.control_plane import register_deployment
    reg = register_deployment(res['manifest'], out, state_dir=tmp_path / 'cp')
    dep_id = reg['deployment']['id']
    status = get_deployment_status(dep_id, state_dir=tmp_path / 'cp')
    assert status['ok'] is True
    assert status['deployment']['provider'] == 'vercel'
    listing = list_deployments(state_dir=tmp_path / 'cp')
    assert listing['count'] == 1
