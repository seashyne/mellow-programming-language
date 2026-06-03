from pathlib import Path

from mellowlang.package_manager import init_package, resolve_project_runtime, _scan_imports
from mellowlang.parser import parse_program


def test_scan_import_aliases(tmp_path: Path):
    p = tmp_path / "main.mellow"
    p.write_text('use core-ai as ai\nneed core-gamekit as gamekit\n', encoding='utf-8')
    imports = _scan_imports(tmp_path)
    assert 'core-ai' in imports
    assert 'core-gamekit' in imports


def test_parser_accepts_use_and_need():
    prog = parse_program('use core-ai as ai\nneed core-gamekit as gamekit\n'.splitlines())
    assert len(prog.body) == 2


def test_resolve_runtime_writes_file(tmp_path: Path):
    init_package(tmp_path, name='demo-app')
    (tmp_path / 'src' / 'main.mellow').write_text('import math as math\n', encoding='utf-8')
    res = resolve_project_runtime(tmp_path, install_missing=False)
    assert res['ok']
    assert (tmp_path / '.mellow_runtime.json').exists()
