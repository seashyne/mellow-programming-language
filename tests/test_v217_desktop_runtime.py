from pathlib import Path

from mellowlang.desktop_host import parse_window_spec, build_desktop_bundle, desktop_status
from mellowlang.package_manager import scaffold_project


def test_desktop_parser_layout_menu_and_state():
    source = '''import "pkg:core-window" as win
keep count = 0
keep name = "Mellow"
keep app = win.window(title: "Demo", width: 800, height: 500, layout: "vstack")
win.menu(app, "File", ["About"])
win.menu_item(app, "File", "Quit", "close")
win.label(app, "Hello {{state.name}}")
win.input(app, "Type", bind: name)
win.button(app, "Count +1", "inc:count")
win.label(app, "Count = {{state.count}}")
win.run(app)
'''
    spec = parse_window_spec(source)
    assert spec["title"] == "Demo"
    assert spec["layout"] == "vstack"
    assert spec["state"]["count"] == 0
    assert spec["state"]["name"] == "Mellow"
    assert spec["menus"][0]["label"] == "File"
    assert any(w.get("bind") == "name" for w in spec["widgets"])
    assert any(e.get("action") == "inc:count" for e in spec["events"])


def test_desktop_build_scaffolds_bundle(tmp_path: Path):
    project = tmp_path / "app"
    res = scaffold_project(project, with_core=True, preset="app")
    assert res["ok"] is True
    entry = project / "src" / "main.mel"
    out = tmp_path / "dist"
    bundle = build_desktop_bundle(entry, out_dir=out, name="DemoApp", onefile=True)
    assert bundle["name"] == "DemoApp"
    assert Path(bundle["spec_file"]).exists()
    assert Path(bundle["launcher"]).exists()
    assert Path(bundle["scripts"]["linux"]).exists()
    assert Path(bundle["scripts"]["windows"]).exists()
    assert Path(bundle["out_dir"]).exists()


def test_desktop_status_cross_platform():
    payload = desktop_status()
    assert payload["ok"] is True
    assert "windows" in payload["cross_platform"]
    assert "linux" in payload["cross_platform"]
