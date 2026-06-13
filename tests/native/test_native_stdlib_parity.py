from __future__ import annotations

import contextlib
import io
import textwrap

from mellowlang.compiler import Compiler
from mellowlang.vm import MellowVM, RunConfig
from mellowlang.vm.cbridge import c_vm_available


def _run(source: str, *, engine: str, **config: object) -> tuple[str, MellowVM]:
    program = Compiler().compile(textwrap.dedent(source).lstrip("\n"), filename="<native-stdlib>")
    vm = MellowVM()
    output = io.StringIO()
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
    return output.getvalue(), vm


def _assert_strict_native(vm: MellowVM) -> None:
    assert c_vm_available(), "native C extension is required for v2.7.0 stdlib parity"
    assert vm.last_engine == "c"
    assert vm.last_native_result.get("used_fallback") is False


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
