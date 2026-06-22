from __future__ import annotations

import io
from contextlib import redirect_stdout

import mellowlang.cli.main as cli_main
from mellowlang.cli.main import main


def test_top_level_registry_command_updates_config(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "cfg"
    monkeypatch.setenv("MELLOW_CONFIG_DIR", str(cfg_dir))
    monkeypatch.chdir(tmp_path)
    import mellowlang.package_manager as pm

    out = io.StringIO()
    with redirect_stdout(out):
        code = main(["registry", "https://registry.example.test"])
    assert code == 0
    assert "default registry" in out.getvalue()
    assert pm.load_config()["registry"] == "https://registry.example.test"
    assert not (tmp_path / "mellow_packages").exists()


def test_help_mentions_registry_and_login(capsys):
    code = main([])
    assert code == 0
    out = capsys.readouterr().out
    assert "install <pkg>" in out or "search <query>" in out
    full = io.StringIO()
    with redirect_stdout(full):
        code_full = main(["help", "--full"])
    assert code_full == 0
    full_out = full.getvalue()
    assert "login --token <token>" in full_out or "login" in full_out
    assert "registry <url>" in full_out or "registry" in full_out


def test_search_displays_latest_when_versions_are_empty(monkeypatch):
    def fake_search(query, registry=None):
        return {
            "ok": True,
            "items": [
                {
                    "name": "core-print",
                    "latest": "0.2.0",
                    "versions": [],
                    "authors": ["Mellow Code Team"],
                    "description": "Console output helpers.",
                }
            ],
        }

    monkeypatch.setattr(cli_main, "pkg_search_remote", fake_search)
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(["search", "core"])
    assert code == 0
    text = out.getvalue()
    assert "core-print" in text
    assert "latest=0.2.0" in text
    assert "creator=Mellow Code Team" in text
    assert "versions=0.2.0" in text


def test_info_command_prints_package_details(monkeypatch):
    def fake_info(name, registry=None):
        return {
            "ok": True,
            "name": name,
            "latest": "0.2.0",
            "versions": ["0.1.0", "0.2.0"],
            "entry": "src/main.mel",
            "authors": ["Mellow Code Team"],
            "description": "Console output helpers.",
            "registry": "https://registry.example.test",
        }

    monkeypatch.setattr(cli_main, "pkg_package_info_remote", fake_info)
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(["info", "core-print"])
    assert code == 0
    text = out.getvalue()
    assert "name       : core-print" in text
    assert "versions   : 0.1.0, 0.2.0" in text
    assert "creator    : Mellow Code Team" in text
    assert "entry      : src/main.mel" in text
    assert "install    : mellow install core-print" in text


def test_install_output_shows_entry_and_lockfile(monkeypatch):
    def fake_install(name, version=None, registry=None, project_dir=None, with_deps=True):
        return {
            "ok": True,
            "name": name,
            "version": "0.2.0",
            "installed_to": "mellow_packages/installed/core-print",
            "entry": "src/main.mel",
            "authors": ["Mellow Code Team"],
            "lockfile": "mellow.lock",
            "alias": "print",
        }

    monkeypatch.setattr(cli_main, "pkg_install_remote", fake_install)
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(["install", "core-print"])
    assert code == 0
    text = out.getvalue()
    assert "package installed: core-print@0.2.0" in text
    assert "creator : Mellow Code Team" in text
    assert "entry   : src/main.mel" in text
    assert "path    : mellow_packages/installed/core-print" in text
    assert "lockfile: mellow.lock" in text


def test_author_profile_command_lists_creator_packages(monkeypatch):
    def fake_profile(author, registry=None):
        return {
            "ok": True,
            "author": author,
            "items": [
                {
                    "name": "core-print",
                    "latest": "0.2.0",
                    "creator": "jirayut",
                    "downloads": 42,
                    "badges": ["official", "verified"],
                    "license": "MIT",
                    "keywords": ["console"],
                    "published_at": "2026-06-14T00:00:00Z",
                    "description": "Console output helpers.",
                }
            ],
        }

    monkeypatch.setattr(cli_main, "pkg_author_profile_remote", fake_profile)
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(["author", "jirayut"])
    assert code == 0
    text = out.getvalue()
    assert "Packages by jirayut: 1" in text
    assert "core-print" in text
    assert "downloads=42" in text
    assert "official, verified" in text


def test_verify_command_prints_signature_status(monkeypatch):
    def fake_signature(name, registry=None):
        return {
            "ok": True,
            "name": name,
            "version": "0.2.0",
            "creator": "jirayut",
            "sha256": "a" * 64,
            "signed": True,
            "verified": True,
            "algorithm": "ed25519",
            "registry": "https://registry.example.test",
        }

    monkeypatch.setattr(cli_main, "pkg_package_signature_remote", fake_signature)
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(["verify", "core-print"])
    assert code == 0
    text = out.getvalue()
    assert "package verified: core-print@0.2.0" in text
    assert "signed    : yes" in text
    assert "algorithm : ed25519" in text


def test_trust_then_strict_verify_accepts_creator(tmp_path, monkeypatch):
    monkeypatch.setenv("MELLOW_CONFIG_DIR", str(tmp_path / "cfg"))

    def fake_signature(name, registry=None):
        return {
            "ok": True,
            "name": name,
            "version": "0.2.1",
            "creator": "Mellow Code Team",
            "sha256": "b" * 64,
            "signed": True,
            "verified": True,
            "algorithm": "ed25519",
        }

    monkeypatch.setattr(cli_main, "pkg_package_signature_remote", fake_signature)
    assert main(["trust", "Mellow Code Team"]) == 0

    out = io.StringIO()
    with redirect_stdout(out):
        code = main(["verify", "core-print", "--strict"])
    assert code == 0
    assert "trusted   : yes" in out.getvalue()


def test_strict_verify_rejects_untrusted_creator(tmp_path, monkeypatch):
    monkeypatch.setenv("MELLOW_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setattr(
        cli_main,
        "pkg_package_signature_remote",
        lambda name, registry=None: {
            "ok": True,
            "name": name,
            "version": "0.2.1",
            "creator": "Unknown Publisher",
            "signed": True,
            "verified": True,
        },
    )
    assert main(["verify", "core-print", "--strict"]) == 1


def test_update_check_prints_available_versions(monkeypatch):
    monkeypatch.setattr(
        cli_main,
        "pkg_update_packages",
        lambda *args, **kwargs: {
            "ok": True,
            "update_count": 1,
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
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(["update", "--check"])
    assert code == 0
    assert "[UPDATE] core-print 0.2.0 -> 0.2.1" in out.getvalue()
