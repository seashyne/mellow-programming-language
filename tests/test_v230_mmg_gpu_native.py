from pathlib import Path

from mellowlang.mmg_runtime import parse_mmg_file
from mellowlang.mmg_gpu_runtime import export_mmg_gpu_commands, mmg_gpu_status


def test_export_native_scene(tmp_path: Path):
    src = tmp_path / "demo.mel"
    src.write_text(
        'import "pkg:core-mmg" as mmg\nkeep app = mmg.app(title: "Demo", width: 320, height: 200, clear: "#112233")\nmmg.rect(app, 10, 20, 30, 40, fill: "#ff00aa")\nmmg.on(app, "key", "Escape", "close")\n',
        encoding="utf-8",
    )
    spec = parse_mmg_file(src)
    out = export_mmg_gpu_commands(spec, tmp_path / "scene.mmgscene")
    text = out.read_text(encoding="utf-8")
    assert text.startswith("MMGSCENE 1")
    assert 'APP "Demo" 320 200' in text
    assert 'RECT 10.000 20.000 30.000 40.000' in text
    assert 'ON_KEY_ESCAPE CLOSE' in text


def test_mmg_gpu_status_shape():
    status = mmg_gpu_status()
    assert status["engine"] == "mmg-gpu-native"
    assert "binary_exists" in status
