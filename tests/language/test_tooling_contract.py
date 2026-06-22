from __future__ import annotations

import contextlib
import io

from mellowlang.cli.main import main


def test_lsp_help_is_available() -> None:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            main(["lsp", "--help"])
        except SystemExit as exc:
            assert exc.code == 0
    text = out.getvalue()
    assert "Language Server" in text
    assert "--stdio" in text
