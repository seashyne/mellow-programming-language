from pathlib import Path

from mellowlang.agents.packages import init_agent_package
from mellowlang.agents.registry import (
    AGENT_INSTALLED_ROOT,
    AGENT_REGISTRY_ROOT,
    agent_dependency_graph,
    install_agent_package,
    publish_agent_from_dir,
)


def _write_dep(root: Path, deps: dict[str, str]):
    p = root / "agent.toml"
    raw = p.read_text(encoding="utf-8")
    if "[dependencies]" in raw:
        raw = raw.split("[dependencies]")[0].rstrip() + "\n"
    if deps:
        raw += "\n[dependencies]\n"
        for k, v in deps.items():
            raw += f'"{k}" = "{v}"\n'
    p.write_text(raw, encoding="utf-8")


def test_publish_install_with_signature_and_graph(tmp_path):
    AGENT_REGISTRY_ROOT.mkdir(parents=True, exist_ok=True)
    AGENT_INSTALLED_ROOT.mkdir(parents=True, exist_ok=True)
    base = init_agent_package(tmp_path / "base", name="base.agent")
    helper = init_agent_package(tmp_path / "helper", name="helper.agent")
    _write_dep(base, {"helper.agent": "^0.1.0"})
    publish_agent_from_dir(helper, signing_key="k1", signer="tester")
    publish_agent_from_dir(base, signing_key="k1", signer="tester")
    graph = agent_dependency_graph("base.agent")
    assert graph["ok"] is True
    assert graph["graph"]["dependencies"][0]["name"] == "helper.agent"
    res = install_agent_package("base.agent", verify_key="k1")
    assert res["ok"] is True
    assert (AGENT_INSTALLED_ROOT / "helper.agent" / "0.1.0" / "package").exists()


def test_install_fails_on_bad_signature(tmp_path):
    bad = init_agent_package(tmp_path / "bad", name="bad.agent")
    publish_agent_from_dir(bad, signing_key="good")
    res = install_agent_package("bad.agent", verify_key="wrong")
    assert res["ok"] is False
    assert "verification failed" in res["error"]


def test_install_fails_on_unsatisfied_dependency(tmp_path):
    app = init_agent_package(tmp_path / "app", name="app.agent")
    _write_dep(app, {"missing.agent": ">=1.0.0"})
    publish_agent_from_dir(app)
    res = install_agent_package("app.agent")
    assert res["ok"] is False
    assert "unsatisfied dependency" in res["error"]
