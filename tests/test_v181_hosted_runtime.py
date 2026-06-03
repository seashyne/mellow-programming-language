from pathlib import Path

from mellowlang.agents import (
    PolicyEngine,
    build_deployment_manifest,
    init_agent_package,
    list_secrets,
    load_signed_policy,
    set_secret,
    sign_capability_policy,
    verify_capability_policy,
    write_deployment_bundle,
)


def test_secret_scopes_roundtrip(tmp_path, monkeypatch):
    import mellowlang.agents.secrets as sec
    monkeypatch.setattr(sec, 'SECRET_FILE', tmp_path / 'agent_secrets.json')
    set_secret('OPENAI_API_KEY', 'sk-demo-secret', scopes=['agent.run'])
    items = list_secrets()
    assert items[0]['name'] == 'OPENAI_API_KEY'
    assert items[0]['scopes'] == ['agent.run']
    assert sec.resolve_secret_env('OPENAI_API_KEY', scope='agent.run') == 'sk-demo-secret'
    assert sec.resolve_secret_env('OPENAI_API_KEY', scope='tool.search.docs') is None


def test_signed_capability_policy_enforced(tmp_path):
    policy_path = tmp_path / 'capabilities.json'
    signed = sign_capability_policy({
        'capabilities': {'allow': ['tools.search.docs'], 'deny': []},
        'tools': {'allow': ['search.docs'], 'deny': ['time.now']},
    }, 'secret', signer='tester')
    policy_path.write_text(__import__('json').dumps(signed), encoding='utf-8')
    loaded = load_signed_policy(policy_path, verify_key='secret')
    assert verify_capability_policy(loaded, 'secret') is True
    engine = PolicyEngine(signed_policy=loaded)
    assert engine.check_tool('search.docs', ['tools.search.docs']).allowed is True
    assert engine.check_tool('time.now', ['tools.time.now']).allowed is False


def test_deployment_manifest_bundle(tmp_path):
    pkg_root = init_agent_package(tmp_path / 'demo-agent', name='demo.agent', force=True)
    manifest = build_deployment_manifest(pkg_root, public_url='https://agents.example.com/demo')
    assert manifest['package']['name'] == 'demo.agent'
    assert manifest['runtime']['public_url'] == 'https://agents.example.com/demo'
    assert 'OPENAI_API_KEY' in manifest['security']['required_secrets']
    bundle = write_deployment_bundle(pkg_root, tmp_path / 'deploy-out')
    assert Path(bundle['manifest_path']).exists()
    assert Path(bundle['start_script']).exists()
