from __future__ import annotations

import json
import sys

from ..common import _cli_line, _lazy_attr

standalone_runtime_status = _lazy_attr("mellowlang.standalone_runtime", "standalone_runtime_status")
build_standalone_runtime = _lazy_attr("mellowlang.standalone_runtime", "build_standalone_runtime")
compile_standalone_image = _lazy_attr("mellowlang.standalone_runtime", "compile_standalone_image")
standalone_run_image = _lazy_attr("mellowlang.standalone_runtime", "standalone_run_image")

def _cmd_standalone_compile(input_path: str, out_path: str | None, json_out: bool, optimize: bool = True) -> int:
    try:
        res = compile_standalone_image(input_path, output_path=out_path, optimize=optimize)
    except Exception as e:
        res = {'ok': False, 'error': str(e), 'input': input_path}
    if json_out:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res.get('ok') else 1
    if res.get('ok'):
        _cli_line('Standalone image compiled.', kind='ok')
        print(f"Input           : {res.get('input')}")
        print(f"Output          : {res.get('output')}")
        print(f"Instructions    : {res.get('code_len')}")
        print(f"Constants       : {res.get('const_len')}")
        return 0
    _cli_line(f"Standalone compile failed: {res.get('error')}", kind='error')
    return 1


def _cmd_standalone_run(image_path: str, binary_path: str | None, json_out: bool) -> int:
    res = standalone_run_image(image_path, binary_path=binary_path)
    if json_out:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res.get('ok') else 1
    if res.get('stdout'):
        print(res['stdout'], end='')
    if res.get('stderr'):
        print(res['stderr'], end='', file=sys.stderr)
    if not res.get('ok'):
        _cli_line(f"Standalone runtime failed: {res.get('error') or 'run_failed'}", kind='error', file=sys.stderr)
        return 1
    return 0


def _cmd_standalone_status(json_out: bool) -> int:
    info = standalone_runtime_status()
    if json_out:
        print(json.dumps(info, indent=2))
        return 0
    _cli_line(f"Standalone runtime root: {info.get('root')}")
    if info.get('binary_exists'):
        _cli_line(f"Standalone binary: {info.get('binary_path')}", kind='ok')
    else:
        _cli_line('Standalone binary not built yet.', kind='warn')
    _cli_line(f"CMake available: {info.get('cmake_available')}")
    _cli_line(f"C compiler available: {info.get('compiler_available')}")
    return 0


def _cmd_standalone_build(json_out: bool, build_dir: str | None = None) -> int:
    res = build_standalone_runtime(build_dir=build_dir)
    if json_out:
        print(json.dumps(res, indent=2))
        return 0 if res.get('ok') else 1
    if res.get('ok'):
        _cli_line('Standalone runtime build succeeded.', kind='ok')
        return 0
    _cli_line(f"Standalone runtime build failed: {res.get('error', 'build_failed')}", kind='error')
    hint = res.get('hint')
    if hint:
        _cli_line(hint, kind='hint')
    return 1


def _cmd_standalone_doctor(json_out: bool) -> int:
    info = standalone_runtime_status()
    checks = {
        'runtime_sources': info.get('exists'),
        'cmake_available': info.get('cmake_available'),
        'compiler_available': info.get('compiler_available'),
    }
    payload = {'ok': all(checks.values()), 'checks': checks, 'status': info}
    if json_out:
        print(json.dumps(payload, indent=2))
        return 0 if payload['ok'] else 1
    for name, ok in checks.items():
        _cli_line(f"{name}: {'ok' if ok else 'missing'}", kind='ok' if ok else 'warn')
    return 0 if payload['ok'] else 1
