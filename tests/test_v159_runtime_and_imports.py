import json
from pathlib import Path

from mellowlang import __version__
from mellowlang.package_manager import init_package, resolve_project_runtime, _scan_imports
from mellowlang.parser import parse_program


def test_scan_import_aliases(tmp_path: Path):
    p = tmp_path / "main.mellow"
    p.write_text('use core-ai as ai\nneed core-gamekit as gamekit\n', encoding='utf-8')
    imports = _scan_imports(tmp_path)
    assert 'core-ai' in imports
    assert 'core-gamekit' in imports


def test_scan_imports_ignores_installed_package_cache(tmp_path: Path):
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src' / 'main.mel').write_text('import "pkg:core-print" as out\n', encoding='utf-8')
    package_src = tmp_path / 'mellow_packages' / 'installed' / 'core-ai' / 'current' / 'package' / 'src'
    package_src.mkdir(parents=True)
    (package_src / 'main.mel').write_text('import "pkg:core-ai" as ai\n', encoding='utf-8')

    assert _scan_imports(tmp_path) == ['core-print']


def test_scan_imports_uses_manifest_entry_source_scope(tmp_path: Path):
    init_package(tmp_path, name='demo-app', entry='main.mel')
    (tmp_path / 'src' / 'main.mel').write_text('import "pkg:core-print" as out\n', encoding='utf-8')
    (tmp_path / 'scripts').mkdir()
    (tmp_path / 'scripts' / 'main.mellow').write_text('import "ai" as ai\n', encoding='utf-8')

    assert _scan_imports(tmp_path) == ['core-print']


def test_parser_accepts_use_and_need():
    prog = parse_program('use core-ai as ai\nneed core-gamekit as gamekit\n'.splitlines())
    assert len(prog.body) == 2


def test_resolve_runtime_writes_file(tmp_path: Path):
    init_package(tmp_path, name='demo-app')
    (tmp_path / 'src' / 'main.mellow').write_text('import math as math\n', encoding='utf-8')
    res = resolve_project_runtime(tmp_path, install_missing=False)
    assert res['ok']
    runtime_map = json.loads((tmp_path / '.mellow_runtime.json').read_text(encoding='utf-8'))
    import_map = json.loads((tmp_path / '.mellow_imports.json').read_text(encoding='utf-8'))
    assert runtime_map['generated_by'] == f'mellow-{__version__}'
    assert import_map['generated_by'] == f'mellow-{__version__}'


def test_resolve_runtime_skips_plain_directory_without_imports(tmp_path: Path):
    (tmp_path / 'main.mellow').write_text('print(3)\n', encoding='utf-8')
    lock_path = tmp_path / 'mellow.lock'
    existing_lock = '{"keep": true}\n'
    lock_path.write_text(existing_lock, encoding='utf-8')

    res = resolve_project_runtime(tmp_path, install_missing=False)

    assert res['ok']
    assert res['skipped'] is True
    assert not (tmp_path / '.mellow_runtime.json').exists()
    assert not (tmp_path / '.mellow_imports.json').exists()
    assert lock_path.read_text(encoding='utf-8') == existing_lock
