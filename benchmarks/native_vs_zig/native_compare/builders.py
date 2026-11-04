from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _build_zig(zig: str, source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    cache_root = Path(os.environ.get("TEMP") or os.environ.get("TMP") or str(output.parent)) / "mellow-zig-cache"
    local_cache = cache_root / "local"
    global_cache = cache_root / "global"
    local_cache.mkdir(parents=True, exist_ok=True)
    global_cache.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    subprocess.run(
        [
            zig,
            "build-exe",
            str(source),
            "-O",
            "ReleaseFast",
            "-fstrip",
            "--cache-dir",
            str(local_cache),
            "--global-cache-dir",
            str(global_cache),
            "--name",
            output.stem,
            "-femit-bin",
        ],
        cwd=output.parent,
        capture_output=True,
        text=True,
        check=True,
    )
    produced = output.parent / (output.stem + ".exe")
    if not produced.exists():
        produced = output.parent / output.stem
    if not produced.exists():
        raise RuntimeError(f"Zig did not produce expected binary for {output.stem}")
    if produced.resolve() != output.resolve():
        shutil.move(str(produced), str(output))


def _find_c_compiler(zig: str | None) -> tuple[str, str] | None:
    for name in ("cc", "gcc", "clang", "cl"):
        path = shutil.which(name)
        if path:
            return name, path
    if zig:
        return "zig cc", zig
    return None


def _build_c(compiler_kind: str, compiler_path: str, source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    if compiler_kind == "cl":
        command = [
            compiler_path,
            "/nologo",
            "/O2",
            str(source),
            f"/Fe:{output}",
        ]
    elif compiler_kind == "zig cc":
        command = [
            compiler_path,
            "cc",
            "-O3",
            str(source),
            "-o",
            str(output),
        ]
    else:
        command = [
            compiler_path,
            "-O3",
            str(source),
            "-o",
            str(output),
        ]
    subprocess.run(command, cwd=output.parent, capture_output=True, text=True, check=True)
    if not output.exists():
        raise RuntimeError(f"C compiler did not produce expected binary: {output}")
