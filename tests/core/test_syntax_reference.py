from __future__ import annotations

import contextlib
import io
from pathlib import Path

from mellowlang.compiler import Compiler
from mellowlang.lint import lint_source
from mellowlang.vm import MellowVM, RunConfig


def test_syntax_tour_is_runnable_reference():
    root = Path(__file__).resolve().parents[2]
    script = root / "examples" / "syntax_tour_v280.mellow"
    program = Compiler().compile(script.read_text(encoding="utf-8"), filename=str(script))
    output = io.StringIO()

    with contextlib.redirect_stdout(output):
        MellowVM().run(program, config=RunConfig(engine="py"))

    assert output.getvalue().splitlines() == [
        "Mellow 2.8",
        "Mali 4 [2, 3]",
        "[0, 2, 4]",
        "5 10",
        "7",
        "0",
        "2",
        "caught",
        "finished",
        "THB 0.30",
        "True",
    ]


def test_syntax_tour_passes_static_check():
    root = Path(__file__).resolve().parents[2]
    script = root / "examples" / "syntax_tour_v280.mellow"
    assert lint_source(script.read_text(encoding="utf-8")) == []
