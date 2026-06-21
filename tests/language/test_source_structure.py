from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "mellowlang"


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
