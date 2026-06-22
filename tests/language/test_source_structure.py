from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "mellowlang"
NATIVE_VM = ROOT / "native" / "mellowvm" / "src"


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_cli_entrypoint_stays_thin() -> None:
    path = SRC / "cli" / "main.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    functions = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    assert functions == ["main"]
    assert _line_count(path) <= 600


def test_large_subsystems_have_explicit_boundaries() -> None:
    assert _line_count(SRC / "package_manager.py") <= 1_100
    assert _line_count(SRC / "vm" / "python_vm.py") <= 2_000
    assert (SRC / "vm" / "debugger.py").is_file()
    assert (SRC / "vm" / "storage.py").is_file()


def test_package_facade_uses_focused_modules() -> None:
    source = (SRC / "package_manager.py").read_text(encoding="utf-8")
    for module in ("config", "metadata", "manifest", "lockfile", "project"):
        assert f"from .packages.{module} import" in source


def test_native_vm_dispatch_and_syscalls_have_explicit_boundaries() -> None:
    module = NATIVE_VM / "mellowvm_module.c"
    syscalls = NATIVE_VM / "mellowvm_syscalls.inc"
    executor = NATIVE_VM / "mellowvm_exec.inc"
    assert syscalls.is_file()
    assert executor.is_file()
    assert '#include "mellowvm_syscalls.inc"' in module.read_text(encoding="utf-8")
    assert '#include "mellowvm_exec.inc"' in module.read_text(encoding="utf-8")
    assert _line_count(module) <= 700
    assert _line_count(syscalls) <= 900
    assert _line_count(executor) <= 800


def test_compiler_v3_has_no_legacy_compiler_or_silent_fallback() -> None:
    compiler_dir = SRC / "compiler"
    facade = (compiler_dir / "compiler.py").read_text(encoding="utf-8")
    standalone = (SRC / "standalone_image.py").read_text(encoding="utf-8")

    assert not (compiler_dir / "bytecode.py").exists()
    assert "_BytecodeCompiler" not in facade
    assert "compiler.bytecode" not in standalone
    assert "v3-ir-bytecode" in facade
