from __future__ import annotations

import contextlib
import io
import textwrap

from mellowlang.compiler import Compiler
from mellowlang.vm import MellowVM, RunConfig


def run_py(source: str) -> list[str]:
    program = Compiler().compile(textwrap.dedent(source).lstrip("\n"), filename="<language>")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        MellowVM().run(program, config=RunConfig(engine="py"))
    return out.getvalue().splitlines()


def test_assignment_functions_and_return_values() -> None:
    assert run_py(
        """
        let base = 10
        keep bonus = 5

        def score(x):
            return base + bonus + x

        print(score(7))
        """
    ) == ["22"]


def test_if_else_semantics() -> None:
    assert run_py(
        """
        let score = 7
        if score > 5:
            print("high")
        else:
            print("low")
        """
    ) == ["high"]


def test_while_loop_semantics() -> None:
    assert run_py(
        """
        let i = 0
        let total = 0
        while i < 5:
            if i < 3:
                total = total + i
            else:
                total = total + 10
            i = i + 1
        print(total)
        """
    ) == ["23"]


def test_for_range_semantics_are_end_exclusive() -> None:
    assert run_py(
        """
        let total = 0
        for i in range(0, 5):
            total = total + i
        print(total)
        """
    ) == ["10"]


def test_list_map_indexing_and_boolean_logic() -> None:
    assert run_py(
        """
        let xs = [2, 4, 6]
        let user = {"name": "Mellow", "active": true}
        if user["active"] and xs[2] == 6:
            print(user["name"])
        else:
            print("bad")
        """
    ) == ["Mellow"]


def test_string_comment_and_multiline_literals() -> None:
    assert run_py(
        """
        let profile = {
            "name": "Mellow",
            "url": "https://example.test/a//b",
            "skills": [
                "tools",
                "games"
            ]
        }
        print(profile["url"]) # comment after string
        print(profile["skills"][1])
        """
    ) == ["https://example.test/a//b", "games"]
