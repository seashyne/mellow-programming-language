"""The MellowLang linter: undefined, shadowed and unused names plus style noise.

The machinery lives in `mellowlang/lint_groups/`, one module per subject; this
module keeps the import path `mellowlang.lint` that `diagnostics.py`, the LSP
server, the CLI and the tests already use."""

from __future__ import annotations

from .lint_groups.issues import (
    LintIssue,
)

from .lint_groups.api import (
    format_source,
    lint_source,
)
