from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mellowlang.package_manager import scaffold_project, resolve_import_entry, resolve_project_runtime


def test_scaffold_project_preloads_core_packages(tmp_path: Path):
    dest = tmp_path / 'demo_app'
    res = scaffold_project(dest, force=False, with_core=True)
    assert res.get('ok') is True
    assert (dest / 'src' / 'main.mel').exists()
    assert (dest / 'mellow.toml').exists()
    assert (dest / '.mellow_runtime.json').exists()
    assert (dest / 'mellow_packages' / 'installed' / 'core-print' / 'current' / 'manifest.json').exists()


def test_resolve_import_entry_uses_project_root(tmp_path: Path):
    dest = tmp_path / 'demo_app'
    res = scaffold_project(dest, force=False, with_core=True)
    assert res.get('ok') is True
    runtime = resolve_project_runtime(dest, install_missing=False, strict=False)
    assert runtime.get('ok') is True
    entry = resolve_import_entry('core-print', dest)
    assert entry is not None
    assert entry.endswith('main.mel') or entry.endswith('main.mellow')
    assert 'demo_app/mellow_packages/installed/core-print/current/package/src/' in entry.replace('\\', '/')
