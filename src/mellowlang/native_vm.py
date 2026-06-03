from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Any

EXTENSION_SUFFIXES = tuple(importlib.machinery.EXTENSION_SUFFIXES)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def extension_candidates() -> list[Path]:
    root = _project_root()
    candidates: list[Path] = []
    package_dir = root / 'src' / 'mellowlang'
    for suffix in EXTENSION_SUFFIXES:
        for name in ('_mellowvm' + suffix, 'mellowlang/_mellowvm' + suffix):
            p = package_dir / Path(name).name
            if p.exists():
                candidates.append(p)
    # Also scan package dir for stale/other-ABI builds.
    if package_dir.exists():
        for p in package_dir.glob('_mellowvm*.so'):
            if p not in candidates:
                candidates.append(p)
        for p in package_dir.glob('_mellowvm*.pyd'):
            if p not in candidates:
                candidates.append(p)
    return candidates


def _python_header_candidates() -> list[Path]:
    paths: list[Path] = []
    cfg = sysconfig.get_paths()
    for key in ('include', 'platinclude'):
        raw = cfg.get(key)
        if raw:
            paths.append(Path(raw) / 'Python.h')
    prefix = Path(sys.prefix)
    ver = f'python{sys.version_info.major}.{sys.version_info.minor}'
    paths.append(prefix / 'include' / ver / 'Python.h')
    paths.append(Path('/usr/include') / ver / 'Python.h')
    return paths


def current_extension_path() -> Path | None:
    for p in extension_candidates():
        if p.suffix.lower() not in {'.so', '.pyd'}:
            continue
        stem = p.name
        if f'cpython-{sys.version_info.major}{sys.version_info.minor}' in stem or '.abi3.' in stem:
            return p
    return extension_candidates()[0] if extension_candidates() else None


def _extension_load_error() -> str | None:
    try:
        import importlib
        importlib.import_module('mellowlang._mellowvm')
        return None
    except Exception as e:
        return str(e)


def source_files() -> list[Path]:
    root = _project_root()
    return [
        root / 'native' / 'mellowvm' / 'include' / 'mellowvm.h',
        root / 'native' / 'mellowvm' / 'src' / 'mellowvm_module.c',
    ]


def native_vm_status() -> dict[str, Any]:
    ext = current_extension_path()
    header_candidates = _python_header_candidates()
    header = next((p for p in header_candidates if p.exists()), None)
    build_tool = shutil.which('gcc') or shutil.which('clang') or shutil.which('cl')
    load_error = _extension_load_error()
    abi_tag = None
    if ext:
        name = ext.name
        marker = 'cpython-'
        if marker in name:
            abi_tag = name.split(marker, 1)[1].split('-', 1)[0]
    current_abi = f"{sys.version_info.major}{sys.version_info.minor}"
    return {
        'available': load_error is None,
        'load_error': load_error,
        'extension_path': str(ext) if ext else None,
        'extension_exists': bool(ext and ext.exists()),
        'extension_abi_tag': abi_tag,
        'current_python_abi': current_abi,
        'abi_matches': (abi_tag == current_abi) if abi_tag else None,
        'extension_suffixes': list(EXTENSION_SUFFIXES),
        'python': sys.version.split()[0],
        'platform': platform.platform(),
        'python_include': str(header) if header else None,
        'python_header_candidates': [str(p) for p in header_candidates],
        'python_headers_found': bool(header),
        'compiler': build_tool,
        'compiler_found': bool(build_tool),
        'source_files': [str(p) for p in source_files()],
        'source_files_present': all(p.exists() for p in source_files()),
        'build_ready': bool(build_tool and header and all(p.exists() for p in source_files())),
        'build_command': f"{sys.executable} setup.py build_ext --inplace",
        'recommended_run_mode': 'engine=c,native_allow_fallback=false' if load_error is None else 'build-native-first',
        'python_vm_still_needed_for': ['record/replay', 'event handlers', 'debugger parity'] if load_error is None else ['all execution until native extension is rebuilt'],
    }


def build_native_vm(*, inplace: bool = True) -> dict[str, Any]:
    root = _project_root()
    cmd = [sys.executable, 'setup.py', 'build_ext']
    if inplace:
        cmd.append('--inplace')
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    status = native_vm_status()
    return {
        'ok': proc.returncode == 0 and bool(status.get('available')),
        'returncode': proc.returncode,
        'stdout': proc.stdout,
        'stderr': proc.stderr,
        'status': status,
        'command': cmd,
    }
