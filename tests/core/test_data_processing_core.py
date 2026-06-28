from __future__ import annotations

import contextlib
import io
import textwrap

import pytest

from mellowlang.compiler import Compiler
from mellowlang.data_core import DataCoreError, DataStreamManager
from mellowlang.error_core import MellowLangRuntimeError
from mellowlang.host.modules import MODULE_ALLOWLIST
from mellowlang.vm import MellowVM, RunConfig


def run_source(source: str, **config) -> tuple[str, MellowVM]:
    program = Compiler().compile(textwrap.dedent(source).lstrip("\n"), filename="<data-core>")
    vm = MellowVM()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        vm.run(program, config=RunConfig(**config))
    return out.getvalue(), vm


def test_jsonl_streaming_is_bounded():
    out, vm = run_source(
        """
        let stream = data_open_jsonl("tests/data/records.jsonl", 2)
        let first = data_next(stream)
        let sales = data_where(first, "kind", "==", "sale")
        print(len(first))
        print(data_sum(sales, "amount"))
        let second = data_next(stream)
        print(len(second))
        print(data_sum(second, "amount"))
        """,
        engine="py",
        data_max_batch_size=2,
    )
    assert out.splitlines() == ["2", "10", "2", "12"]
    assert vm.last_engine == "py"


def test_csv_streaming_and_projection():
    out, _ = run_source(
        """
        let stream = data.open_csv("tests/data/records.csv", 3)
        let rows = data.next(stream)
        let projected = data.project(rows, ["id", "kind"])
        print(len(projected))
        print(projected[0]["kind"])
        """,
        engine="py",
        data_max_batch_size=3,
    )
    assert out.splitlines() == ["3", "sale"]


def test_parameterized_sqlite_and_write_permission():
    source = """
        let db = data_sqlite_open(":memory:")
        data_sqlite_execute(db, "CREATE TABLE items(id INTEGER, name TEXT)", [])
        data_sqlite_execute(db, "INSERT INTO items VALUES(?, ?)", [1, "alpha"])
        let injected = data_sqlite_query(db, "SELECT name FROM items WHERE name = ?", ["alpha' OR 1=1 --"], 10)
        let rows = data_sqlite_query(db, "SELECT name FROM items WHERE id = ?", [1], 10)
        print(len(injected))
        print(rows[0]["name"])
        data_sqlite_close(db)
    """
    out, _ = run_source(source, engine="py", allow_data_write=True, data_max_query_rows=10)
    assert out.splitlines() == ["0", "alpha"]


def test_data_module_is_allowlisted():
    assert MODULE_ALLOWLIST["data"]["open_jsonl"] == "std.data.open_jsonl"
    assert MODULE_ALLOWLIST["data"]["sqlite_query"] == "std.data.sqlite_query"


def test_data_stream_honors_cancellation_callback():
    def cancelled() -> None:
        raise DataCoreError("cancelled")

    manager = DataStreamManager(
        resolve_read=str,
        resolve_write=str,
        check_cancelled=cancelled,
    )
    stream = manager.open_iterable(iter([{"id": 1}]), 1)
    with pytest.raises(DataCoreError, match="cancelled"):
        manager.next_batch(stream)


def test_sqlite_writes_are_explicitly_denied_by_default():
    with pytest.raises(MellowLangRuntimeError, match="data writes are disabled"):
        run_source(
            """
            let db = data_sqlite_open(":memory:")
            data_sqlite_execute(db, "CREATE TABLE items(id INTEGER)", [])
            """,
            engine="py",
        )
