from __future__ import annotations

import contextlib
import io
from pathlib import Path

from mellowlang.compiler import Compiler
from mellowlang.parser import parse_program
from mellowlang.vm import MellowVM, RunConfig


ROOT = Path(__file__).resolve().parents[2]


def run_example(name: str) -> list[str]:
    script = ROOT / "examples" / name
    program = Compiler().compile(script.read_text(encoding="utf-8"), filename=str(script))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        MellowVM().run(program, config=RunConfig(engine="py"))
    return out.getvalue().splitlines()


def test_v3_cli_automation_demo_runs() -> None:
    assert run_example("v3_cli_automation.mellow") == [
        "task 0 check",
        "task 1 test",
        "task 2 package",
    ]


def test_v3_finance_ledger_demo_runs() -> None:
    assert run_example("v3_finance_ledger.mellow") == ["USD 125.00"]


def test_v3_game_script_demo_runs() -> None:
    assert run_example("v3_game_script.mellow") == [
        "tick 0 x 2",
        "tick 1 x 4",
        "tick 2 x 6",
        "tick 3 x 8",
    ]


def test_v3_package_demo_compiles() -> None:
    script = ROOT / "examples" / "v3_package_core_usage.mellow"
    parsed = parse_program(script.read_text(encoding="utf-8").splitlines(), filename=str(script))
    assert parsed.body


def test_v3_interop_demo_compiles() -> None:
    script = ROOT / "examples" / "v3_interop_node.mellow"
    program = Compiler().compile(script.read_text(encoding="utf-8"), filename=str(script))
    assert program.bytecode
