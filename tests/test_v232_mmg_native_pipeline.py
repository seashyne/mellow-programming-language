from pathlib import Path

from mellowlang.mmg_runtime import parse_mmg_file
from mellowlang.mmg_gpu_runtime import export_mmg_gpu_commands, mmg_gpu_status


def test_export_native_pipeline_scene_v2(tmp_path: Path):
    src = tmp_path / "demo.mel"
    src.write_text(
        'keep count = 1\n'
        'keep app = mmg.app(title: "Demo", width: 800, height: 600, clear: "#101418")\n'
        'mmg.scene(app, "main")\n'
        'mmg.texture(app, "hero", source: "hero.png")\n'
        'mmg.sprite(app, texture: "hero", x: 10, y: 20, w: 30, h: 40)\n'
        'mmg.on(app, "key", "Escape", "close")\n'
        'mmg.frame(app, fps: 60)\n',
        encoding="utf-8",
    )
    spec = parse_mmg_file(src)
    out = tmp_path / "demo.mmgscene"
    export_mmg_gpu_commands(spec, out)
    data = out.read_text(encoding="utf-8")
    assert data.startswith("MMGSCENE 3")
    assert "PIPELINE sprite_batching=1 shader_pipeline=1 input_callbacks=1 state_callbacks=1 runtime_bridge=1" in data
    assert 'STATE "count" int "1"' in data
    assert 'ON_KEY "Escape" CLOSE ""' in data


def test_mmg_gpu_status_has_pipeline_flags():
    st = mmg_gpu_status()
    assert st["sprite_batching"] is True
    assert st["input_callbacks"] is True
