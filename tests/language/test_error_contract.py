from __future__ import annotations

import pytest

from mellowlang.compiler import Compiler
from mellowlang.error_core import MellowLangRuntimeError
from mellowlang.vm import MellowVM, RunConfig


def test_syntax_error_has_type_line_and_message() -> None:
    with pytest.raises(MellowLangRuntimeError) as exc:
        Compiler().compile("let = 1\n", filename="bad.mellow")
    err = exc.value
    assert err.error_type == "SYNTAX"
    assert err.line_num >= 1
    assert err.message


def test_runtime_error_has_type_and_trace_context() -> None:
    program = Compiler().compile("print(1 / 0)\n", filename="bad_runtime.mellow")
    with pytest.raises(MellowLangRuntimeError) as exc:
        MellowVM().run(program, config=RunConfig(engine="py"))
    err = exc.value
    assert err.error_type in {"RUNTIME", "MATH"}
    assert err.message
    assert err.filename in {None, "bad_runtime.mellow"}


def test_undefined_name_raises_runtime_error() -> None:
    program = Compiler().compile("print(missing_name)\n", filename="bad_runtime.mellow")
    with pytest.raises(MellowLangRuntimeError) as exc:
        MellowVM().run(program, config=RunConfig(engine="py"))
    assert exc.value.error_type in {"RUNTIME", "UNDEFINED"}
    assert "undefined name" in str(exc.value)


def test_project_interop_is_denied_without_permission(tmp_path) -> None:
    program = Compiler().compile('get interop.run("python", [], {})\n', filename="interop.mellow")
    with pytest.raises(MellowLangRuntimeError) as exc:
        MellowVM().run(
            program,
            config=RunConfig(engine="py", project_mode=True, project_root=str(tmp_path)),
        )
    assert "allowlisted" in str(exc.value)
