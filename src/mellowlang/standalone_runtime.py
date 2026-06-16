from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .standalone_image import compile_file_to_standalone_image, run_standalone_image


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _standalone_root() -> Path:
    return _project_root() / "native" / "standalone"


def _core_module_paths() -> list[Path]:
    root = _project_root()
    return [
        root / 'stdlib' / 'core.mellow',
        root / 'stdlib' / 'core.mel',
    ]


def standalone_runtime_status() -> dict[str, Any]:
    root = _standalone_root()
    build_dir = root / 'build'
    native_cli = build_dir / ('mellow.exe' if os.name == 'nt' else 'mellow')
    compatibility_cli = build_dir / ('mellowrt.exe' if os.name == 'nt' else 'mellowrt')
    binary = native_cli if native_cli.exists() else compatibility_cli
    source_files = sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()) if root.exists() else []
    cc = shutil.which('cc') or shutil.which('clang') or shutil.which('gcc')
    cmake = shutil.which('cmake')
    core_paths = _core_module_paths()
    existing_core = [str(p) for p in core_paths if p.exists()]
    return {
        'available': binary.exists(),
        'binary_exists': binary.exists(),
        'binary_path': str(binary),
        'root': str(root),
        'exists': root.exists(),
        'source_files': source_files,
        'cmake_available': bool(cmake),
        'cmake_path': cmake,
        'compiler_available': bool(cc),
        'compiler_path': cc,
        'platform': platform.platform(),
        'python_dependency_free_goal': True,
        'full_native_source_frontend': True,
        'native_cli_name': native_cli.name,
        'standalone_image_support': True,
        'image_format': 'mlvi-binary-v2',
        'opcode_migration': {
            'arithmetic': True,
            'locals': True,
            'call_return': True,
            'list_map': True,
            'compare': True,
            'jump': True,
            'syscall_bridge': True,
        },
        'core_module_present': bool(existing_core),
        'core_module_candidates': [str(p) for p in core_paths],
        'core_module_existing': existing_core,
        'notes': [
            'Standalone runtime core no longer needs Python.h.',
            'Mellow 2.9.2 includes a C lexer/compiler frontend that runs .mellow source directly without CPython.',
            'The mellow executable accepts source files and MLVI binary images; mellowrt remains as a compatibility executable.',
            'Runtime metadata now includes function/event/module tables and optional core-module loading hints.',
            'The native syscall surface now includes print/len/type/str/clock_ms/getenv builtins.',
            'A stdlib core.mellow/core.mel file is recommended for language-level helpers, but it is not required for the C VM itself.',
        ],
    }


def build_standalone_runtime(*, build_dir: str | None = None) -> dict[str, Any]:
    root = _standalone_root()
    build_path = Path(build_dir) if build_dir else root / 'build'
    build_path.mkdir(parents=True, exist_ok=True)
    cmake = shutil.which('cmake')
    cc = shutil.which('cc') or shutil.which('clang') or shutil.which('gcc')
    result: dict[str, Any] = {
        'ok': False,
        'root': str(root),
        'build_dir': str(build_path),
        'cmake_available': bool(cmake),
        'compiler_available': bool(cc),
        'commands': [],
    }
    if not root.exists():
        result['error'] = 'standalone_runtime_missing'
        return result
    if cmake:
        cache = build_path / 'CMakeCache.txt'
        if cache.exists():
            text = cache.read_text(encoding='utf-8', errors='ignore')
            if str(root) not in text:
                shutil.rmtree(build_path, ignore_errors=True)
                build_path.mkdir(parents=True, exist_ok=True)
        cfg = [cmake, '-S', str(root), '-B', str(build_path)]
        bld = [cmake, '--build', str(build_path)]
        result['commands'] = [' '.join(cfg), ' '.join(bld)]
        try:
            c1 = subprocess.run(cfg, capture_output=True, text=True, check=False)
            c2 = subprocess.run(bld, capture_output=True, text=True, check=False) if c1.returncode == 0 else None
            result['configure'] = {'returncode': c1.returncode, 'stdout': c1.stdout, 'stderr': c1.stderr}
            if c2 is not None:
                result['build'] = {'returncode': c2.returncode, 'stdout': c2.stdout, 'stderr': c2.stderr}
                result['ok'] = c2.returncode == 0
            else:
                result['ok'] = False
            if result['ok']:
                return result
            result['cmake_error'] = 'cmake_build_failed'
        except Exception as exc:
            result['cmake_error'] = str(exc)
    if not cc:
        result['error'] = 'compiler_not_found'
        result['hint'] = 'Install CMake or a C compiler, then run `mellow standalone build` again.'
        return result
    out_bin = build_path / ('mellowrt.exe' if os.name == 'nt' else 'mellowrt')
    srcs = [
        root / 'src' / 'mellowrt_core.c',
        root / 'src' / 'mellowrt_debug.c',
        root / 'src' / 'mellowc.c',
        root / 'src' / 'mellowrt_main.c',
    ]
    cmd = [cc, '-std=c99', '-I', str(root / 'include'), *map(str, srcs), '-o', str(out_bin), '-lm']
    result['commands'].append(' '.join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    result['build'] = {'returncode': proc.returncode, 'stdout': proc.stdout, 'stderr': proc.stderr}
    result['ok'] = proc.returncode == 0
    if result['ok']:
        native_cli = build_path / ('mellow.exe' if os.name == 'nt' else 'mellow')
        shutil.copy2(out_bin, native_cli)
        result['binary_path'] = str(native_cli)
    if not result['ok']:
        result['error'] = 'compiler_build_failed'
    return result



def compile_standalone_image(input_path: str, *, output_path: str | None = None, optimize: bool = True) -> dict[str, Any]:
    return compile_file_to_standalone_image(input_path, output_path=output_path, optimize=optimize)


def standalone_run_image(image_path: str, *, binary_path: str | None = None) -> dict[str, Any]:
    return run_standalone_image(image_path, binary_path=binary_path)
