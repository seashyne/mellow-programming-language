from __future__ import annotations

import contextlib
import io
import shutil
import textwrap
from pathlib import Path

from mellowlang.cli import main as cli_main
from mellowlang.compiler import Compiler
from mellowlang.host.modules import MODULE_ALLOWLIST
from mellowlang.vm import MellowVM, RunConfig


def run_source(source: str) -> str:
    program = Compiler().compile(textwrap.dedent(source).lstrip("\n"), filename="<money>")
    vm = MellowVM()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        vm.run(program, config=RunConfig(engine="py"))
    return out.getvalue()


def test_std_money_uses_decimal_amounts():
    out = run_source(
        """
        let a = money("0.10", "THB")
        let b = money("0.20", "THB")
        let total = money_add(a, b)
        print(money_format(total))
        print(money_amount(total))
        """
    )
    assert out.splitlines() == ["THB 0.30", "0.30"]


def test_money_module_is_allowlisted_for_get_calls():
    assert MODULE_ALLOWLIST["money"]["add"] == "std.money.add"
    out = run_source(
        """
        let total = money.add(money.of("12.345", "USD"), money.of("0.005", "USD"))
        print(total)
        """
    )
    assert out.strip() == "USD 12.36"


def test_finance_sandbox_profile_blocks_storage(tmp_path: Path):
    root = tmp_path / "finance-project"
    root.mkdir()
    script = root / "finance.mellow"
    script.write_text(
        textwrap.dedent(
            """
            save {"amount": "100.00"} into "ledger"
            """
        ).lstrip("\n"),
        encoding="utf-8",
    )
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli_main(["run", str(script), "--sandbox=finance", "--no-resolve"])
    try:
        assert code == 1
        assert "storage is disabled" in out.getvalue() or "storage is disabled" in err.getvalue()
    finally:
        shutil.rmtree(root, ignore_errors=True)
