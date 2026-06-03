from pathlib import Path

from mellowlang.desktop_host import parse_window_spec
from mellowlang.package_manager import scaffold_project


def test_app_preset_scaffold(tmp_path: Path):
    out = tmp_path / "hello_app"
    res = scaffold_project(out, with_core=True, preset="app")
    assert res["ok"] is True
    assert (out / "src" / "main.mel").exists()
    text = (out / "src" / "main.mel").read_text(encoding="utf-8")
    assert 'pkg:core-window' in text
    assert (out / "desktop" / "window.json").exists()


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
