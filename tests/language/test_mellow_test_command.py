from __future__ import annotations

import contextlib
import io
from pathlib import Path

from mellowlang.cli.main import main


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "language" / "fixtures" / "golden_core.mellow"


def test_mellow_test_checks_golden_output_py_engine() -> None:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(["test", str(FIXTURE), "--engine", "py"])
    assert code == 0
    assert "[PASS]" in out.getvalue()


def test_mellow_test_reports_json_summary() -> None:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(["test", str(FIXTURE), "--engine", "py", "--json"])
    assert code == 0
    text = out.getvalue()
    assert '"ok": true' in text
    assert '"passed": 1' in text
