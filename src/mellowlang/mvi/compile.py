"""The three ways in: compile a string, compile a file to .mvi, run an image."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .format import StandaloneImage
from .binary import _standalone_binary
from .lowering import lower_compiled_to_standalone_image


def compile_source_to_standalone_image(source: str, *, filename: str | None = None, optimize: bool = True) -> StandaloneImage:
    from ..compiler import Compiler

    compiled = Compiler().compile(source, filename=filename, optimize=optimize)
    return lower_compiled_to_standalone_image(compiled, source_name=filename or '<memory>')


def compile_file_to_standalone_image(input_path: str, *, output_path: str | None = None, optimize: bool = True) -> dict[str, Any]:
    path = Path(input_path)
    source = path.read_text(encoding='utf-8')
    image = compile_source_to_standalone_image(source, filename=str(path), optimize=optimize)
    out_path = Path(output_path) if output_path else path.with_suffix('.mvi')
    out_path.write_bytes(image.to_bytes())
    return {
        'ok': True,
        'input': str(path),
        'output': str(out_path),
        'format': 'mlvi-binary-v2',
        'code_len': len(image.code),
        'const_len': len(image.consts),
        'globals': image.globals,
        'functions': [fn.__dict__ for fn in image.functions],
        'events': [ev.__dict__ for ev in image.events],
        'modules': [mod.__dict__ for mod in image.modules],
        'pipeline': image.pipeline,
    }


def run_standalone_image(image_path: str, *, binary_path: str | None = None) -> dict[str, Any]:
    binary = Path(binary_path) if binary_path else _standalone_binary()
    if not binary.exists():
        return {'ok': False, 'error': 'standalone_binary_missing', 'binary_path': str(binary)}
    proc = subprocess.run([str(binary), str(image_path)], capture_output=True, text=True, check=False)
    return {
        'ok': proc.returncode == 0,
        'returncode': proc.returncode,
        'stdout': proc.stdout,
        'stderr': proc.stderr,
        'binary_path': str(binary),
        'image_path': str(image_path),
    }
