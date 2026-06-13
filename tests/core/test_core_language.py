from __future__ import annotations

import contextlib
import io
import textwrap
from pathlib import Path

from mellowlang import __version__
from mellowlang.cli import main as cli_main
from mellowlang.compiler import Compiler
from mellowlang.vm import MellowVM, RunConfig


def run_source(source: str) -> str:
    program = Compiler().compile(textwrap.dedent(source).lstrip("\n"), filename="<core>")
    vm = MellowVM()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        vm.run(program, config=RunConfig())
    return out.getvalue()


def test_version_matches_core_release():
    assert __version__ == "2.7.0"


def test_print_arithmetic_and_variables():
    out = run_source(
        """
        let score = 1
        score = score + 4
        print(score)
        """
    )
    assert out.strip() == "5"


def test_function_call_is_stable_core_syntax():
    out = run_source(
        """
        def add(a, b):
            return a + b

        print(add(2, 3))
        """
    )
    assert out.strip() == "5"


def test_while_loop_is_stable_core_syntax():
    out = run_source(
        """
        let i = 0
        let total = 0
        while i < 4:
            total = total + i
            i = i + 1
        print(total)
        """
    )
    assert out.strip() == "6"


def test_range_function_is_stable_core_syntax():
    out = run_source(
        """
        let total = 0
        for i in range(0, 6):
            total = total + i
        print(total)
        """
    )
    assert out.strip() == "15"


def test_list_and_map_literals_print_values():
    out = run_source(
        """
        let xs = [10, 20, 30]
        let data = {"name": "mellow", "score": 20}
        print(data["name"])
        print(xs[1])
        print(data["score"])
        """
    )
    assert out.splitlines() == ["mellow", "20", "20"]


def test_cli_run_and_check_core_script():
    script = Path(__file__).resolve().parents[2] / "examples" / "hello.mellow"
    run_out = io.StringIO()
    with contextlib.redirect_stdout(run_out):
        assert cli_main(["run", str(script)]) == 0
    assert "Hello from MellowLang!" in run_out.getvalue()

    check_out = io.StringIO()
    with contextlib.redirect_stdout(check_out):
        assert cli_main(["check", str(script)]) == 0
    assert "OK ok" in check_out.getvalue()
