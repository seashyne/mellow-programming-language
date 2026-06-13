from __future__ import annotations

import contextlib
import io
import textwrap

import pytest

from mellowlang.compiler import Compiler
from mellowlang.vm import MellowVM, RunConfig
from mellowlang.vm.cbridge import c_vm_available


CORE_SNIPPETS = {
    "print_arithmetic_and_variables": """
        let score = 1
        score = score + 4
        print(score)
    """,
    "function_call": """
        def add(a, b):
            return a + b

        print(add(2, 3))
    """,
    "while_loop": """
        let i = 0
        let total = 0
        while i < 4:
            total = total + i
            i = i + 1
        print(total)
    """,
    "range_loop": """
        let total = 0
        for i in range(0, 6):
            total = total + i
        print(total)
    """,
    "list_and_map_indexing": """
        let xs = [10, 20, 30]
        let data = {"name": "mellow", "score": 20}
        print(data["name"])
        print(xs[1])
        print(data["score"])
    """,
}


def _run_source(source: str, *, engine: str) -> tuple[str, MellowVM]:
    program = Compiler().compile(textwrap.dedent(source).lstrip("\n"), filename="<native-core>")
    vm = MellowVM()
    out = io.StringIO()
    config = RunConfig(
        engine=engine,
        native_allow_fallback=False,
        native_require=(engine == "c"),
    )
    with contextlib.redirect_stdout(out):
        vm.run(program, config=config)
    return out.getvalue(), vm


@pytest.mark.parametrize("name,source", CORE_SNIPPETS.items())
def test_native_c_matches_python_vm_for_stable_core(name: str, source: str) -> None:
    assert c_vm_available(), "native C extension is required for v2.4.0 core parity"

    py_out, _ = _run_source(source, engine="py")
    c_out, c_vm = _run_source(source, engine="c")

    assert c_vm.last_engine == "c", name
    assert c_vm.last_native_result.get("used_fallback") is False, name
    assert c_out == py_out
