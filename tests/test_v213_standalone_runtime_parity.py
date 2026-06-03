from __future__ import annotations

from pathlib import Path

from mellowlang.standalone_runtime import build_standalone_runtime, compile_standalone_image, standalone_run_image


def test_standalone_runtime_parity_pack(tmp_path: Path):
    src = Path('examples/hello.mellow')
    out = tmp_path / 'hello.mvi'
    build = build_standalone_runtime()
    assert build['ok']
    compiled = compile_standalone_image(str(src), output_path=str(out))
    assert compiled['ok']
    assert compiled['format'] == 'mlvi-binary-v2'
    assert compiled['modules']
    assert out.read_bytes()[:8] == b'MLVI0200'
    ran = standalone_run_image(str(out))
    assert ran['ok']
    assert 'Hello from MellowLang!' in ran['stdout']
