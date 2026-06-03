import json
from pathlib import Path

from mellowlang import package_manager as pm
from mellowlang.agents.packages import init_agent_package
from mellowlang.agents.registry import (
    AGENT_INSTALLED_ROOT,
    AGENT_REGISTRY_ROOT,
    build_agent_archive,
    clear_agent_auth_token,
    generate_agent_lock,
    install_agent_with_lock,
    publish_agent_from_dir,
    read_agent_lock,
    set_agent_auth_token,
    write_agent_lock,
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


def test_reproducible_agent_archive(tmp_path):
    pkg = init_agent_package(tmp_path / "demo", name="demo.agent")
    out1 = tmp_path / "a.magent"
    out2 = tmp_path / "b.magent"
    res1 = build_agent_archive(pkg, out1)
    res2 = build_agent_archive(pkg, out2)
    assert res1["sha256"] == res2["sha256"]
    assert out1.read_bytes() == out2.read_bytes()


def test_agent_lockfile_reproducible_install(tmp_path):
    helper = init_agent_package(tmp_path / "helper", name="helper.agent")
    app = init_agent_package(tmp_path / "app", name="app.agent")
    _write_dep(app, {"helper.agent": "^0.1.0"})
    publish_agent_from_dir(helper)
    publish_agent_from_dir(app)

    lock_res = generate_agent_lock(app)
    lock_path = write_agent_lock(app, lock_res["lock"])
    lock = read_agent_lock(lock_path)
    assert any(x["name"] == "helper.agent" for x in lock["packages"])

    install = install_agent_with_lock(app, frozen=True)
    assert install["ok"] is True
    assert (AGENT_INSTALLED_ROOT / "helper.agent" / "0.1.0" / "package").exists()


def test_frozen_install_fails_when_manifest_changes(tmp_path):
    helper = init_agent_package(tmp_path / "helper2", name="helper2.agent")
    app = init_agent_package(tmp_path / "app2", name="app2.agent")
    _write_dep(app, {"helper2.agent": "^0.1.0"})
    publish_agent_from_dir(helper)
    publish_agent_from_dir(app)
    lock_res = generate_agent_lock(app)
    write_agent_lock(app, lock_res["lock"])
    _write_dep(app, {"helper2.agent": ">=9.0.0"})

    install = install_agent_with_lock(app, frozen=True)
    assert install["ok"] is False
    assert "out of date" in install["error"]


def test_private_agent_registry_auth_saved(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(pm, "CONFIG_FILE", cfg)
    monkeypatch.setattr(pm, "CONFIG_HOME", tmp_path)
    saved = set_agent_auth_token("https://agents.example.com", "secret-token", private=True)
    assert saved["ok"] is True
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["agent_private_auth"]["https://agents.example.com"] == "secret-token"
    cleared = clear_agent_auth_token("https://agents.example.com", private=True)
    assert cleared["ok"] is True
    data2 = json.loads(cfg.read_text(encoding="utf-8"))
    assert data2["agent_private_auth"] == {}
