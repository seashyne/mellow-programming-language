from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "mellowlang"
NATIVE_VM = ROOT / "native" / "mellowvm" / "src"
STANDALONE = ROOT / "native" / "standalone" / "src"
HOST_FAMILIES = SRC / "host" / "families"

# Any file longer than this must appear in LINE_CEILINGS, so a new oversized
# file is a deliberate decision instead of an accident.
FILE_LENGTH_LIMIT = 1_000

# Largest each long file may become. Lower the number when the file shrinks;
# never raise it to make this test pass - split the file instead.
LINE_CEILINGS: dict[str, int] = {
    "src/mellowlang/ai_core.py": 1_325,
    "src/mellowlang/cli/commands/agents.py": 1_150,
    "src/mellowlang/compiler/optimizer.py": 1_300,
    "src/mellowlang/package_manager.py": 1_100,
    "src/mellowlang/parser.py": 1_300,
    "src/mellowlang/vm/python_vm.py": 2_000,
    "native/mellowvm/src/mellowvm_exec.inc": 800,
    "native/mellowvm/src/mellowvm_module.c": 700,
    "native/mellowvm/src/mellowvm_storage.inc": 800,
    "native/mellowvm/src/mellowvm_syscalls.inc": 900,
    "native/standalone/src/mellowrt_core.c": 950,
    "native/standalone/src/mellowrt_ledger.c": 975,
    "native/standalone/src/mellowrt_storage.c": 1_000,
    "native/standalone/src/mellowrt_syscalls.c": 975,
    "tests/native/test_full_native_c_cli.py": 1_375,
}

LENGTH_SUFFIXES = {".py", ".c", ".h", ".inc"}
LENGTH_SCAN_ROOTS = ("src", "native", "tests", "stdlib", "benchmarks", "scripts", "sdk")
SKIP_PARTS = {"build", "node_modules", "dist", "__pycache__", ".venv"}


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _long_files() -> dict[str, int]:
    sizes: dict[str, int] = {}
    for root_name in LENGTH_SCAN_ROOTS:
        for path in (ROOT / root_name).rglob("*"):
            if not path.is_file() or path.suffix not in LENGTH_SUFFIXES:
                continue
            if SKIP_PARTS & set(path.parts):
                continue
            relative = path.relative_to(ROOT).as_posix()
            sizes[relative] = _line_count(path)
    return sizes


def test_cli_entrypoint_stays_thin() -> None:
    path = SRC / "cli" / "main.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    functions = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    assert functions == ["main"]
    assert _line_count(path) <= 600


def test_large_subsystems_have_explicit_boundaries() -> None:
    sizes = _long_files()
    undeclared = sorted(
        f"{name} ({size} lines)"
        for name, size in sizes.items()
        if size > FILE_LENGTH_LIMIT and name not in LINE_CEILINGS
    )
    assert not undeclared, (
        "split along the workspace boundaries, or add a ceiling that is a real "
        f"decision: {undeclared}"
    )
    over_budget = sorted(
        f"{name}: {sizes[name]} > {ceiling}"
        for name, ceiling in LINE_CEILINGS.items()
        if name in sizes and sizes[name] > ceiling
    )
    assert not over_budget, f"these files grew past their declared ceiling: {over_budget}"
    missing = sorted(name for name in LINE_CEILINGS if name not in sizes)
    assert not missing, f"declared ceiling points at a file that no longer exists: {missing}"
    assert (SRC / "vm" / "debugger.py").is_file()
    assert (SRC / "vm" / "storage.py").is_file()


def test_host_syscall_registry_is_split_by_family() -> None:
    """The host registry is an assembler; syscall bodies live in host/families."""
    runtime = SRC / "host" / "runtime.py"
    assert _line_count(runtime) <= 120
    assert (SRC / "host" / "base.py").is_file()
    assert (HOST_FAMILIES / "support.py").is_file(), "shared arg predicates live here"

    families = sorted(
        path.stem for path in HOST_FAMILIES.glob("*.py") if path.stem != "__init__"
    )
    assert "support" in families
    assert len(families) >= 14, "syscall families were split out of runtime.py"

    assembler = runtime.read_text(encoding="utf-8")
    for family in families:
        if family == "support":
            continue
        assert f"register_{family}_functions" in assembler, f"{family} is not assembled"
        module = (HOST_FAMILIES / f"{family}.py").read_text(encoding="utf-8")
        assert f"def register_{family}_functions(" in module
    # no syscall is registered by the assembler except the trivial echo probe
    assert assembler.count("HostFunction(") == 1


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


def test_standalone_compiler_keeps_loop_recognizers_separate() -> None:
    module = STANDALONE / "mellowc.c"
    recognizers = STANDALONE / "mellowc_fastloops.inc"
    source = module.read_text(encoding="utf-8")
    assert recognizers.is_file()
    assert '#include "mellowc_fastloops.inc"' in source
    assert _line_count(module) <= 700
    assert _line_count(recognizers) <= 650
    # the recognizers are file-static helpers with a single translation unit
    fragment = recognizers.read_text(encoding="utf-8")
    assert "mellowlang" not in fragment, "the standalone engine stays C-only"
    for name in ("expr_is_i64_literal", "emit_fast_i64_sum_loop", "emit_fast_string_append_loop"):
        assert f"static int {name}(" in fragment, f"{name} is defined outside the fragment"
        assert f"static int {name}(" not in source, f"{name} leaked back into mellowc.c"


def test_compiler_v3_has_no_legacy_compiler_or_silent_fallback() -> None:
    compiler_dir = SRC / "compiler"
    facade = (compiler_dir / "compiler.py").read_text(encoding="utf-8")
    standalone = (SRC / "standalone_image.py").read_text(encoding="utf-8")

    assert not (compiler_dir / "bytecode.py").exists()
    assert "_BytecodeCompiler" not in facade
    assert "compiler.bytecode" not in standalone
    assert "v3-ir-bytecode" in facade
