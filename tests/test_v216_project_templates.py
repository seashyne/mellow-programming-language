import json
import os
from pathlib import Path

from mellowlang.compiler import Compiler
from mellowlang.cli.main import main
from mellowlang.desktop_host import parse_window_spec
from mellowlang.package_manager import scaffold_project
from mellowlang.web import parse_web_source


def test_app_preset_scaffold(tmp_path: Path):
    out = tmp_path / "hello_app"
    res = scaffold_project(out, with_core=True, preset="app")
    assert res["ok"] is True
    assert (out / "src" / "main.mel").exists()
    text = (out / "src" / "main.mel").read_text(encoding="utf-8")
    assert 'pkg:core-window' in text
    Compiler().compile(text, filename=str(out / "src" / "main.mel"))
    assert (out / "desktop" / "window.json").exists()
    spec = parse_window_spec(text)
    assert spec["title"] == "Mellow Desktop App"
    assert spec["width"] == 960
    assert spec["height"] == 640


def test_all_project_presets_compile(tmp_path: Path):
    for preset in ("starter", "app", "automation", "ai-agent", "gamekit", "api-webhook", "finance", "data"):
        out = tmp_path / preset
        res = scaffold_project(out, with_core=True, preset=preset)
        assert res["ok"] is True
        entry = out / "src" / "main.mel"
        Compiler().compile(entry.read_text(encoding="utf-8"), filename=str(entry))


def test_no_core_project_is_minimal_and_runnable(tmp_path: Path):
    out = tmp_path / "plain"
    res = scaffold_project(out, with_core=False)
    assert res["ok"] is True
    entry = out / "src" / "main.mel"
    text = entry.read_text(encoding="utf-8")
    assert "pkg:" not in text
    assert not (out / "mellow_packages").exists()
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert "mellow run src/main.mel" in readme
    assert "--with-core" in readme
    assert "mellow add core-print" in readme
    assert "mellow search core" in readme
    assert "mellow sync-imports ." in readme
    Compiler().compile(text, filename=str(entry))


def test_web_preset_works_with_mellow_web_defaults(tmp_path: Path):
    out = tmp_path / "webapp"
    res = scaffold_project(out, with_core=False, preset="web")
    assert res["ok"] is True
    entry = out / "src" / "App.mellow"
    assert entry.exists()
    parse_web_source(entry.read_text(encoding="utf-8"), filename=str(entry))
    mellow_json = json.loads((out / "mellow.json").read_text(encoding="utf-8"))
    assert mellow_json["web"]["entry"] == "src/App.mellow"
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert "mellow web dev" in readme

    old_cwd = Path.cwd()
    try:
        os.chdir(out)
        assert main(["web", "dev", "--prepare-only"]) == 0
    finally:
        os.chdir(old_cwd)
    assert (out / ".mellow" / "web-dev" / "MellowApp.tsx").exists()


def test_desktop_parser_reads_window_spec():
    source = (
        'import "pkg:core-window" as win\n'
        'keep app = win.window(title: "Demo", width: 800, height: 500)\n'
        'win.label(app, "Hello")\n'
        'win.button(app, "Close", "close")\n'
        'win.run(app)'
    )
    spec = parse_window_spec(source)
    assert spec["title"] == "Demo"
    assert spec["width"] == 800
    assert spec["height"] == 500
    assert len(spec["widgets"]) == 2
