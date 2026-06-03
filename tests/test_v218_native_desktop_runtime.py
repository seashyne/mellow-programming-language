from pathlib import Path

from mellowlang.desktop_host import parse_window_spec, build_desktop_bundle, desktop_status
from mellowlang.package_manager import scaffold_project


def test_parser_supports_slider_and_listbox():
    source = '''import "pkg:core-window" as win
keep volume = 25
keep picked = ""
keep app = win.window(title: "Demo", width: 900, height: 600, layout: "grid")
win.label(app, "Volume")
win.slider(app, "Level", min: 0, max: 100, bind: volume)
win.listbox(app, "Pick", ["A", "B", "C"], bind: picked)
win.run(app)
'''
    spec = parse_window_spec(source)
    assert spec["layout"] == "grid"
    assert any(w["type"] == "slider" for w in spec["widgets"])
    assert any(w["type"] == "listbox" for w in spec["widgets"])


def test_portable_bundle_is_created_without_pyinstaller(tmp_path: Path):
    project = tmp_path / "app"
    res = scaffold_project(project, with_core=True, preset="app")
    assert res["ok"] is True
    entry = project / "src" / "main.mel"
    out = tmp_path / "dist"
    bundle = build_desktop_bundle(entry, out_dir=out, name="DemoPortable")
    assert bundle["builder"] == "portable-bundle"
    assert bundle["requires_pyinstaller"] is False
    bundle_dir = Path(bundle["bundle_dir"])
    assert (bundle_dir / "run_app.py").exists()
    assert (bundle_dir / "run_linux.sh").exists()
    assert (bundle_dir / "run_windows.bat").exists()
    assert (bundle_dir / "runtime" / "src" / "mellowlang" / "desktop_host.py").exists()


def test_status_exposes_native_runtime_label():
    payload = desktop_status()
    assert payload["engine"] == "native-ui-runtime"
    assert payload["requires_pyinstaller"] is False
    assert payload["builder"] == "portable-bundle"
