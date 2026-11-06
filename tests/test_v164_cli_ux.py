from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import mellowlang.cli.commands.packages as pkg_cmds
import mellowlang.cli.main as cli
import mellowlang.package_manager as pm
from mellowlang.cli.main import main


def test_direct_script_path_is_rejected_with_run_hint(capsys):
    code = main(["demo.mellow"])
    assert code == 2
    err = capsys.readouterr().err
    assert "direct script mode has been removed" in err
    assert "Use `mellow run demo.mellow`." in err


def test_unknown_command_shows_suggestion(capsys):
    code = main(["serch", "ai"])
    assert code == 2
    err = capsys.readouterr().err
    assert "unknown command 'serch'" in err
    assert "Did you mean `mellow search`?" in err


def test_add_dependency_accepts_alias_and_persists_it(tmp_path: Path, monkeypatch):
    project = tmp_path / "proj"
    project.mkdir()

    monkeypatch.setattr(pm, "get_registry_url", lambda explicit=None: "https://registry.example.test")
    monkeypatch.setattr(pm, "get_auth_token", lambda registry=None: None)
    monkeypatch.setattr(pm, "_select_meta_candidate", lambda reg, auth, dep: ({"ok": True, "versions": ["1.2.3"]}, "@ai/openai"))

    def fake_install_remote(name, version=None, registry=None, with_deps=True, project_dir=None, _visited=None):
        return {"ok": True, "name": name, "version": "1.2.3", "installed": [{"name": name, "version": "1.2.3"}]}

    monkeypatch.setattr(pm, "install_remote", fake_install_remote)

    res = pm.add_dependency("openai", project_dir=project, alias="gpt")
    assert res["ok"] is True
    assert res["alias"] == "gpt"
    aliases = pm.load_aliases(project)
    assert aliases["aliases"]["gpt"] == "@ai/openai"



def test_interactive_search_can_install_selection(monkeypatch):
    # main pushes its pkg_* aliases into the packages command module on dispatch,
    # so those are patched on main; the prompt helpers are owned by packages only.
    monkeypatch.setattr(cli, "pkg_search_remote", lambda query, registry=None: {
        "ok": True,
        "items": [
            {"name": "@ai/openai", "latest": "1.2.3", "versions": ["1.2.3"], "description": "OpenAI SDK"},
            {"name": "@ai/llama", "latest": "0.9.0", "versions": ["0.9.0"], "description": "Llama SDK"},
        ],
    })
    monkeypatch.setattr(cli, "pkg_install_remote", lambda name, registry=None, project_dir=None: {"ok": True, "name": name, "version": "1.2.3"})
    monkeypatch.setattr(pkg_cmds, "_prompt_choice", lambda items, title="": "@ai/openai")
    answers = iter([False, True])
    monkeypatch.setattr(pkg_cmds, "_prompt_yes_no", lambda prompt, default=True: next(answers))

    out = io.StringIO()
    with redirect_stdout(out):
        code = main(["search", "openai", "--interactive"])
    text = out.getvalue()
    assert code == 0
    assert "package installed: @ai/openai@1.2.3" in text
