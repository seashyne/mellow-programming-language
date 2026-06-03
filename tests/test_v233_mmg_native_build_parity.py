from pathlib import Path

from mellowlang.mmg_runtime import parse_mmg_file
from mellowlang.mmg_gpu_runtime import export_mmg_gpu_commands, mmg_gpu_status


def test_export_native_pipeline_scene_v3_has_bridge_and_shaders(tmp_path: Path):
    src = tmp_path / "demo.mel"
    src.write_text(
        "keep count = 1\n"
        "keep app = mmg.app(title: \"Demo\", width: 800, height: 600, clear: \"#101418\")\n"
        "mmg.scene(app, \"main\")\n"
        "mmg.texture(app, \"hero\", source: \"hero.png\")\n"
        "mmg.sprite(app, texture: \"hero\", x: 10, y: 20, w: 30, h: 40)\n"
        "mmg.on(app, \"key\", \"Space\", \"inc:count\")\n"
        "mmg.frame(app, fps: 60)\n",
        encoding="utf-8",
    )
    spec = parse_mmg_file(src)
    out = tmp_path / "demo.mmgscene"
    export_mmg_gpu_commands(spec, out)
    data = out.read_text(encoding="utf-8")
    assert data.startswith("MMGSCENE 3")
    assert 'SHADER "sprite"' in data
    assert 'BRIDGE_STATE "count" int "1"' in data
    assert 'BRIDGE_EVENT "key" "Space" INC "count"' in data
    assert 'BATCH_GROUP "main" "hero" 1' in data


def test_mmg_gpu_status_has_build_scripts_and_vbo_flags():
    st = mmg_gpu_status()
    assert st["sprite_batching"] is True
    assert st["shader_pipeline"] is True
    assert st["vbo_renderer"] is True
    assert st["runtime_bridge"] is True
    assert st["build_scripts"]["windows_bat"].endswith("build_windows.bat")
