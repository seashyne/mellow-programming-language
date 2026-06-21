from __future__ import annotations

from pathlib import Path

from mellowlang.compiler import Compiler
from mellowlang.host.runtime import MODULE_ALLOWLIST
from mellowlang.package_manager import _scan_imports, init_package, resolve_project_runtime
from mellowlang.parser import parse_program


def test_stable_host_modules_are_classified() -> None:
    for name in ("math", "string", "list", "map", "json", "money", "data", "ledger", "interop"):
        assert name in MODULE_ALLOWLIST
        assert MODULE_ALLOWLIST[name]


def test_use_and_need_are_package_import_syntax() -> None:
    program = parse_program(
        [
            "use core-json as jsonx",
            "need core-print as out",
        ]
    )
    assert len(program.body) == 2


def test_project_runtime_records_package_imports(tmp_path: Path) -> None:
    init_package(tmp_path, name="demo-app")
    src = tmp_path / "src" / "main.mellow"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("use core-json as jsonx\nneed core-print as out\n", encoding="utf-8")
    assert _scan_imports(tmp_path) == ["core-json", "core-print"]
    res = resolve_project_runtime(tmp_path, install_missing=False)
    assert res["ok"] is True
    assert (tmp_path / ".mellow_runtime.json").exists()


def test_compiler_accepts_allowlisted_module_call_syntax() -> None:
    program = Compiler().compile('let x = get math.sqrt(9)\nprint(x)\n', filename="<module>")
    assert program.bytecode
