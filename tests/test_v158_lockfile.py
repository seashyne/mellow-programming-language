from pathlib import Path
import json
import mellowlang.package_manager as pm
from mellowlang.package_manager import _save_import_map, _save_lockfile, _load_lockfile


def test_lockfile_roundtrip(tmp_path: Path):
    path = _save_lockfile({"lockfile_version": 1, "registry": "https://example", "packages": {}, "root": {"dependencies": {}, "imports": []}}, tmp_path)
    assert path.exists()
    data = _load_lockfile(tmp_path)
    assert data["registry"] == "https://example"


def test_import_map_written(tmp_path: Path):
    path = _save_import_map(tmp_path, [])
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "imports" in data


def test_package_update_plan_compares_installed_and_latest(tmp_path: Path, monkeypatch):
    _save_lockfile(
        {
            "lockfile_version": 1,
            "registry": "https://example.test",
            "packages": {"core-print": {"version": "0.2.0"}},
            "root": {"dependencies": {"core-print": "0.2.0"}, "imports": []},
        },
        tmp_path,
    )
    monkeypatch.setattr(pm, "_installed_version", lambda name, project_dir=None: "0.2.0")
    monkeypatch.setattr(
        pm,
        "package_info_remote",
        lambda name, registry=None: {
            "ok": True,
            "name": name,
            "latest": "0.2.1",
            "creator": "Mellow Code Team",
            "badges": ["official"],
        },
    )
    plan = pm.package_update_plan(project_dir=tmp_path)
    assert plan["ok"] is True
    assert plan["update_count"] == 1
    assert plan["updates"][0]["name"] == "core-print"


def test_update_packages_installs_planned_latest(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        pm,
        "package_update_plan",
        lambda *args, **kwargs: {
            "ok": True,
            "registry": "https://example.test",
            "items": [
                {
                    "name": "core-print",
                    "current": "0.2.0",
                    "latest": "0.2.1",
                    "needs_update": True,
                }
            ],
        },
    )
    calls = []

    def fake_install(name, version=None, registry=None, with_deps=True, project_dir=None):
        calls.append((name, version, registry, with_deps, project_dir))
        return {"ok": True, "installed": [{"name": name, "version": version}]}

    monkeypatch.setattr(pm, "install_remote", fake_install)
    result = pm.update_packages(project_dir=tmp_path, all_packages=True)
    assert result["ok"] is True
    assert result["count"] == 1
    assert calls == [("core-print", "0.2.1", "https://example.test", True, tmp_path)]
