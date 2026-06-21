from __future__ import annotations

import contextlib
import io
import textwrap

import pytest

from mellowlang.compiler import Compiler
from mellowlang.vm import MellowVM, RunConfig
from mellowlang.vm.cbridge import c_vm_available, c_vm_capabilities


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
    "keep_if_else_and_boolean_logic": """
        keep enabled = true
        let disabled = false
        if enabled and not disabled:
            print("stable")
        else:
            print("broken")
    """,
    "negative_index_and_core_builtins": """
        let values = [9, -4, 16]
        print(values[-1])
        print(len(values))
        print(str(abs(values[1])))
        print(type(values))
        print(floor(2.8))
        print(ceil(2.1))
        print(sqrt(16))
        print(min(3, 7))
        print(max(3, 7))
    """,
}

CORE_ERROR_SNIPPETS = {
    "undefined_name": "print(missing_name)\n",
    "list_index_out_of_range": "let xs = [1]\nprint(xs[2])\n",
    "string_index_out_of_range": 'let value = "mellow"\nprint(value[20])\n',
    "missing_map_key": 'let item = {"name": "mellow"}\nprint(item["version"])\n',
    "non_indexable_value": "let value = 42\nprint(value[0])\n",
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


def test_native_c_is_the_default_engine() -> None:
    assert RunConfig().engine == "c"
    output, vm = _run_source(CORE_SNIPPETS["print_arithmetic_and_variables"], engine=RunConfig().engine)
    assert output.strip() == "5"
    assert vm.last_engine == "c"
    assert vm.last_native_result.get("used_fallback") is False


def test_native_capabilities_claim_complete_core_without_claiming_tooling_parity() -> None:
    capabilities = c_vm_capabilities()
    assert capabilities["native_parity_level"] == "core-complete+money+data+ledger"
    assert capabilities["source_span_parity"] is False


@pytest.mark.parametrize("name,source", CORE_SNIPPETS.items())
def test_native_c_matches_python_vm_for_stable_core(name: str, source: str) -> None:
    assert c_vm_available(), "native C extension is required for v2.4.0 core parity"

    py_out, _ = _run_source(source, engine="py")
    c_out, c_vm = _run_source(source, engine="c")

    assert c_vm.last_engine == "c", name
    assert c_vm.last_native_result.get("used_fallback") is False, name
    assert c_out == py_out


@pytest.mark.parametrize("name,source", CORE_ERROR_SNIPPETS.items())
def test_native_c_matches_python_vm_for_core_runtime_errors(name: str, source: str) -> None:
    assert c_vm_available(), "native C extension is required for core error parity"

    errors = []
    for engine in ("py", "c"):
        with pytest.raises(Exception) as exc:
            _run_source(source, engine=engine)
        errors.append(str(exc.value).lower())

    expected_fragment = {
        "undefined_name": "undefined name",
        "list_index_out_of_range": "index out of range",
        "string_index_out_of_range": "index out of range",
        "missing_map_key": "missing map key",
        "non_indexable_value": "not indexable",
    }[name]
    assert expected_fragment in errors[0]
    assert expected_fragment in errors[1]
