from pathlib import Path
import sys
import os

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from mellowlang.standalone_image import compile_file_to_standalone_image
from mellowlang.standalone_runtime import build_standalone_runtime, standalone_run_image


def test_standalone_image_compile_and_run(tmp_path: Path):
    src = ROOT / 'examples' / 'hello.mellow'
    out = tmp_path / 'hello.mvi'
    res = compile_file_to_standalone_image(str(src), output_path=str(out))
    assert res['ok'] is True
    assert out.exists()

    build_dir = tmp_path / 'build'
    build = build_standalone_runtime(build_dir=str(build_dir))
    assert build['ok'] is True

    binary = build_dir / ('mellowrt.exe' if os.name == 'nt' else 'mellowrt')
    run = standalone_run_image(str(out), binary_path=str(binary))
    assert run['ok'] is True, run
    assert 'Hello from MellowLang!' in run['stdout']
    assert 'score = 1' in run['stdout']
