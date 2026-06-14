from __future__ import annotations

import contextlib
from copy import deepcopy
import io
import textwrap

import pytest

from mellowlang.compiler import Compiler
from mellowlang.ledger_core import LedgerError, balance, create, post, verify
from mellowlang.vm import MellowVM, RunConfig


def run_source(source: str, *, engine: str = "py") -> str:
    program = Compiler().compile(textwrap.dedent(source).lstrip("\n"), filename="<ledger-core>")
    vm = MellowVM()
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        vm.run(program, config=RunConfig(engine=engine))
    return output.getvalue()


def test_ledger_script_is_balanced_and_immutable():
    output = run_source(
        """
        let empty = ledger_create("THB")
        let book = ledger_post(
            empty,
            "sale-001",
            [
                {"account": "cash", "amount": "100.00"},
                {"account": "revenue", "amount": "-100.00"}
            ],
            "cash sale"
        )
        print(len(ledger_entries(empty)))
        print(len(ledger_entries(book)))
        print(money_format(ledger_balance(book, "cash")))
        let status = ledger_verify(book)
        print(status["ok"])
        """
    )
    assert output.splitlines() == ["0", "1", "THB 100.00", "True"]


def test_ledger_rejects_unbalanced_and_duplicate_transactions():
    book = create("USD")
    with pytest.raises(LedgerError, match="not balanced"):
        post(
            book,
            "bad-001",
            [
                {"account": "cash", "amount": "10.00"},
                {"account": "revenue", "amount": "-9.00"},
            ],
        )

    posted = post(
        book,
        "sale-001",
        [
            {"account": "cash", "amount": "10.00"},
            {"account": "revenue", "amount": "-10.00"},
        ],
    )
    with pytest.raises(LedgerError, match="duplicate transaction id"):
        post(
            posted,
            "sale-001",
            [
                {"account": "cash", "amount": "1.00"},
                {"account": "revenue", "amount": "-1.00"},
            ],
        )


def test_ledger_hash_chain_detects_tampering():
    book = post(
        create("USD"),
        "sale-001",
        [
            {"account": "cash", "amount": "25.00"},
            {"account": "revenue", "amount": "-25.00"},
        ],
    )
    assert verify(book)["ok"] is True
    assert balance(book, "revenue")["amount"] == "-25.00"

    tampered = deepcopy(book)
    tampered["entries"][0]["postings"][0]["amount"] = "250.00"
    status = verify(tampered)
    assert status["ok"] is False
    assert "unbalanced entry" in status["error"] or "hash mismatch" in status["error"]
