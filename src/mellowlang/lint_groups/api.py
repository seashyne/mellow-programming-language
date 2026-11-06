"""The two entry points: `lint_source` parses and reports, `format_source`
rewrites whitespace."""

from __future__ import annotations

from typing import List

from ..parser import parse_program, ParseError
from .issues import LintIssue
from .linter import _Linter


def lint_source(src: str) -> List[LintIssue]:
    issues: List[LintIssue] = []
    lines = src.splitlines()
    try:
        program = parse_program(lines)
    except ParseError as e:
        issues.append(LintIssue("SYNTAX", str(e)))
        return issues

    for i, ln in enumerate(lines, start=1):
        if "\t" in ln:
            issues.append(LintIssue("STYLE", "tab character found; use spaces", i))
        if ln.rstrip("\n") != ln.rstrip("\n").rstrip(" "):
            issues.append(LintIssue("STYLE", "trailing spaces", i))

    try:
        linter = _Linter()
        linter.run(program)
        issues.extend(linter.issues)
    except Exception:
        pass

    issues.sort(key=lambda x: (x.line or 0, x.kind))
    return issues


def format_source(src: str) -> str:
    out_lines: List[str] = []
    blank_run = 0
    for ln in src.splitlines():
        ln = ln.replace("\t", "    ").rstrip()
        if ln.strip() == "":
            blank_run += 1
            if blank_run <= 2:
                out_lines.append("")
            continue
        blank_run = 0
        out_lines.append(ln)
    return "\n".join(out_lines) + ("\n" if src.endswith("\n") else "")
