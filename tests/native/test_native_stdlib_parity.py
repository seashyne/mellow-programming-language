from __future__ import annotations

import contextlib
import io
import os
import textwrap
from pathlib import Path

import pytest

from mellowlang.compiler import Compiler
from mellowlang.error_core import MellowLangRuntimeError
from mellowlang.vm import MellowVM, RunConfig
from mellowlang.vm.cbridge import c_vm_available, c_vm_capabilities


ROOT = Path(__file__).resolve().parents[2]
STORAGE_PROGRAM = (ROOT / "tests" / "fixtures" / "storage_core.mellow").read_text(encoding="utf-8")

STORAGE_SANDBOX_CASES = {
    "storage_traversal": (
        'let slot = storage.save("../evil", {"a": 1})\nprint(slot)\n',
        "invalid storage path",
    ),
    "storage_dir_traversal": (
        'let root = storage_dir("../outside")\nprint(root)\n',
        'storage_dir: ".." traversal is blocked',
    ),
    "fs_traversal": (
        'let body = fs_read("../secret.txt")\nprint(body)\n',
        'fs: ".." traversal is blocked',
    ),
    "missing_folder": (
        'let slot = storage.save("nodir/hero", {"a": 1})\nprint(slot)\n',
        "Folder not found:",
    ),
}


def _run(source: str, *, engine: str, cwd: Path | None = None, **config: object) -> tuple[str, MellowVM]:
    program = Compiler().compile(textwrap.dedent(source).lstrip("\n"), filename="<native-stdlib>")
    vm = MellowVM()
    output = io.StringIO()
    previous = os.getcwd()
    if cwd is not None:
        os.chdir(cwd)
    try:
        with contextlib.redirect_stdout(output):
            vm.run(
                program,
                config=RunConfig(
                    engine=engine,
                    native_allow_fallback=False,
                    native_require=(engine == "c"),
                    **config,
                ),
            )
    finally:
        if cwd is not None:
            os.chdir(previous)
    return output.getvalue(), vm


def _assert_strict_native(vm: MellowVM) -> None:
    assert c_vm_available(), "native C extension is required for v2.9.0 stdlib parity"
    assert vm.last_engine == "c"
    assert vm.last_native_result.get("used_fallback") is False


def _tree(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))


def test_native_extension_reports_data_transform_acceleration() -> None:
    assert c_vm_capabilities().get("native_data_transforms") is True
    assert c_vm_capabilities().get("native_ledger_bridge") is True


def test_native_money_matches_python() -> None:
    source = """
        let subtotal = money("100.10", "THB")
        let tax = money("7.01", "THB")
        let total = money_add(subtotal, tax)
        print(money_format(total))
        print(money_amount(total))
        print(money_gt(total, subtotal))
    """
    py_output, _ = _run(source, engine="py")
    native_output, native_vm = _run(source, engine="c")
    _assert_strict_native(native_vm)
    assert native_output == py_output


def test_native_ledger_matches_python() -> None:
    source = """
        let book = ledger_create("THB")
        let posted = ledger_post(
            book,
            "sale-001",
            [
                {"account": "cash", "amount": "125.50"},
                {"account": "revenue", "amount": "-125.50"}
            ],
            "native sale"
        )
        print(len(ledger_entries(book)))
        print(money_format(ledger_balance(posted, "cash")))
        let status = ledger_verify(posted)
        print(status["ok"])
    """
    py_output, _ = _run(source, engine="py")
    native_output, native_vm = _run(source, engine="c")
    _assert_strict_native(native_vm)
    assert native_output == py_output


def test_native_jsonl_batch_processing_matches_python() -> None:
    source = """
        let stream = data_open_jsonl("tests/data/records.jsonl", 2)
        let rows = data_next(stream)
        let sales = data_where(rows, "kind", "==", "sale")
        print(len(rows))
        print(data_sum(sales, "amount"))
        print(data_close(stream))
    """
    py_output, _ = _run(source, engine="py", data_max_batch_size=2)
    native_output, native_vm = _run(source, engine="c", data_max_batch_size=2)
    _assert_strict_native(native_vm)
    assert native_output == py_output


def test_native_data_transforms_match_python_edge_cases() -> None:
    source = """
        let rows = [
            {"id": 1, "kind": "sale", "amount": 10, "tags": ["new", "paid"]},
            {"id": 2, "kind": "refund", "amount": 2.5, "tags": ["review"]},
            {"id": 3, "kind": "sale", "amount": 7},
            "ignored"
        ]
        let projected = data.project(rows, ["id", "missing"])
        let sales = data.where(rows, "kind", "==", "sale")
        let tagged = data.where(rows, "tags", "contains", "paid")
        let large = data.where(rows, "amount", ">=", 7)
        print(len(projected))
        print(projected[0]["missing"])
        print(len(sales))
        print(len(tagged))
        print(len(large))
        print(data.sum(rows, "amount"))
    """
    py_output, _ = _run(source, engine="py")
    native_output, native_vm = _run(source, engine="c")
    _assert_strict_native(native_vm)
    assert native_output == py_output


@pytest.mark.parametrize("engine", ["py", "c"])
def test_data_where_rejects_unknown_operator_on_both_engines(engine: str) -> None:
    with pytest.raises(MellowLangRuntimeError, match="unsupported data.where operator"):
        _run(
            'let rows = [{"amount": 1}]\ndata.where(rows, "amount", "~=", 1)\n',
            engine=engine,
        )


def test_native_sqlite_lifecycle_matches_python() -> None:
    source = """
        let db = data_sqlite_open(":memory:")
        data_sqlite_execute(db, "CREATE TABLE items(id INTEGER, amount INTEGER)", [])
        data_sqlite_execute(db, "INSERT INTO items VALUES(?, ?)", [1, 25])
        let rows = data_sqlite_query(db, "SELECT amount FROM items WHERE id = ?", [1], 10)
        print(rows[0]["amount"])
        print(data_sqlite_close(db))
    """
    options = {"allow_data_write": True, "data_max_query_rows": 10}
    py_output, _ = _run(source, engine="py", **options)
    native_output, native_vm = _run(source, engine="c", **options)
    _assert_strict_native(native_vm)
    assert native_output == py_output


def test_native_storage_matches_python_write_for_write(tmp_path: Path) -> None:
    python_dir = tmp_path / "py"
    native_dir = tmp_path / "c"
    python_dir.mkdir()
    native_dir.mkdir()

    py_output, _ = _run(STORAGE_PROGRAM, engine="py", cwd=python_dir)
    native_output, native_vm = _run(STORAGE_PROGRAM, engine="c", cwd=native_dir)
    _assert_strict_native(native_vm)
    assert native_output == py_output == "storage ok\n"

    saved = Path("mellow_fixture_saves") / "profiles" / "hero.json"
    assert (native_dir / saved).read_bytes() == (python_dir / saved).read_bytes()
    assert _tree(native_dir) == _tree(python_dir)


@pytest.mark.parametrize("engine", ["py", "c"])
@pytest.mark.parametrize(
    ("case", "source", "fragment"),
    [(name, source, fragment) for name, (source, fragment) in sorted(STORAGE_SANDBOX_CASES.items())],
)
def test_native_storage_rejects_the_same_paths_as_python(
    engine: str,
    case: str,
    source: str,
    fragment: str,
    tmp_path: Path,
) -> None:
    workdir = tmp_path / f"{case}-{engine}"
    workdir.mkdir()
    with pytest.raises(MellowLangRuntimeError) as reference:
        _run(source, engine=engine, cwd=workdir)
    assert fragment in str(reference.value)
    assert list(workdir.rglob("*.json")) == []
