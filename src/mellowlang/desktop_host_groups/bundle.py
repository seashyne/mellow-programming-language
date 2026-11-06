"""Build a portable desktop bundle: copy the runtime and the app, write
the launcher and the platform scripts, and record the manifest."""

from __future__ import annotations

import json
import os
import shutil
import textwrap
from pathlib import Path
from typing import Any, Dict

# `build_desktop_bundle` bundles the package it lives in
# (`Path(__file__).resolve().parent`). From this subpackage that resolves to
# the group directory, so point `__file__` back at the facade's directory -
# the package the monolith bundled.
__file__ = str(Path(__file__).resolve().parents[1] / "desktop_host.py")


def _portable_launcher_py(entry_rel: str) -> str:
    return textwrap.dedent(f'''
    from pathlib import Path
    import sys

    ROOT = Path(__file__).resolve().parent
    VENDORED_SRC = ROOT / "runtime" / "src"
    if str(VENDORED_SRC) not in sys.path:
        sys.path.insert(0, str(VENDORED_SRC))

    from mellowlang.desktop_host import parse_window_file, launch_window

    entry = (ROOT / {entry_rel!r}).resolve()
    raise SystemExit(launch_window(parse_window_file(entry)))
    ''').strip() + '\n'


def build_desktop_bundle(entry_file: str | Path, *, out_dir: str | Path = 'dist', name: str | None = None, onefile: bool = False, windowed: bool = True) -> Dict[str, Any]:
    entry = Path(entry_file).resolve()
    project_root = entry.parent.parent if entry.parent.name == 'src' else entry.parent
    build_dir = Path(out_dir).resolve()
    app_name = name or project_root.name.replace('-', '_')
    bundle_root = build_dir / app_name
    runtime_src = bundle_root / 'runtime' / 'src'
    app_src = bundle_root / 'app'
    for folder in (runtime_src, app_src):
        folder.mkdir(parents=True, exist_ok=True)

    mellow_src = Path(__file__).resolve().parent
    shutil.copytree(mellow_src, runtime_src / 'mellowlang', dirs_exist_ok=True)
    shutil.copytree(project_root / 'src', app_src / 'src', dirs_exist_ok=True)
    for optional in ('mellow.json', 'mellow.toml', 'README.md'):
        src = project_root / optional
        if src.exists():
            shutil.copy2(src, bundle_root / optional)

    launcher_py = bundle_root / 'run_app.py'
    entry_rel = str(Path('app') / 'src' / entry.name).replace('\\', '/')
    launcher_py.write_text(_portable_launcher_py(entry_rel), encoding='utf-8')

    linux_sh = bundle_root / 'run_linux.sh'
    linux_sh.write_text('#!/usr/bin/env bash\nset -e\nPYTHON_BIN=${PYTHON_BIN:-python3}\n"$PYTHON_BIN" "$(dirname "$0")/run_app.py"\n', encoding='utf-8')
    os.chmod(linux_sh, 0o755)
    windows_bat = bundle_root / 'run_windows.bat'
    windows_bat.write_text('@echo off\r\nset PYTHON_BIN=%PYTHON_BIN%\r\nif "%PYTHON_BIN%"=="" set PYTHON_BIN=python\r\n%PYTHON_BIN% "%~dp0run_app.py"\r\n', encoding='utf-8')

    manifest = {
        'name': app_name,
        'entry': str(entry),
        'bundle_dir': str(bundle_root),
        'out_dir': str(build_dir),
        'launcher': str(launcher_py),
        'spec_file': str(bundle_root / 'bundle.spec.json'),
        'scripts': {'linux': str(linux_sh), 'windows': str(windows_bat)},
        'platforms': ['windows', 'linux'],
        'builder': 'portable-bundle',
        'windowed': windowed,
        'onefile': False,
        'requires_pyinstaller': False,
        'note': 'Portable bundle generated. Target machine needs Python 3 + Tk installed.',
        'runtime': {'engine': 'native-ui-runtime', 'backend': 'ttk'},
    }
    (bundle_root / 'bundle.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    (bundle_root / 'bundle.spec.json').write_text(json.dumps({'entry': str(entry), 'runtime': manifest['runtime'], 'builder': manifest['builder']}, ensure_ascii=False, indent=2), encoding='utf-8')
    return manifest
