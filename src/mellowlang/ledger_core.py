from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
from typing import Any


class LedgerError(RuntimeError):
    pass


_SCALE = Decimal("0.01")
_GENESIS = "0" * 64


def _amount(value: Any) -> Decimal:
    if isinstance(value, dict) and value.get("type") == "money":
        value = value.get("amount", "0")
    try:
        return Decimal(str(value)).quantize(_SCALE, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise LedgerError(f"ledger: invalid amount: {value}") from exc


def _currency(value: Any) -> str:
    result = str(value or "USD").strip().upper()
    if not result or len(result) > 12:
        raise LedgerError("ledger: invalid currency")
    return result


def _canonical_hash(payload: dict[str, Any]) -> str:
    try:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise LedgerError("ledger: metadata must be JSON serializable") from exc
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create(currency: Any = "USD") -> dict[str, Any]:
    return {
        "type": "ledger",
        "version": 1,
        "currency": _currency(currency),
        "entries": [],
        "head": _GENESIS,
    }


def _require_ledger(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("type") != "ledger":
        raise LedgerError("ledger: expected ledger")
    if not isinstance(value.get("entries"), list):
        raise LedgerError("ledger: invalid entries")
    return value


def post(
    ledger: Any,
    transaction_id: Any,
    postings: Any,
    memo: Any = "",
    metadata: Any = None,
) -> dict[str, Any]:
    source = _require_ledger(ledger)
    tx_id = str(transaction_id or "").strip()
    if not tx_id:
        raise LedgerError("ledger: transaction id is required")
    if any(str(entry.get("id")) == tx_id for entry in source["entries"] if isinstance(entry, dict)):
        raise LedgerError(f"ledger: duplicate transaction id: {tx_id}")
    if not isinstance(postings, list) or len(postings) < 2:
        raise LedgerError("ledger: postings must contain at least two rows")

    normalized: list[dict[str, str]] = []
    total = Decimal("0.00")
    for row in postings:
        if not isinstance(row, dict):
            raise LedgerError("ledger: each posting must be a map")
        account = str(row.get("account") or "").strip()
        if not account:
            raise LedgerError("ledger: posting account is required")
        amount = _amount(row.get("amount", "0"))
        normalized.append({"account": account, "amount": format(amount, "f")})
        total += amount
    if total != Decimal("0.00"):
        raise LedgerError(f"ledger: transaction is not balanced: {format(total, 'f')}")

    previous_hash = str(source.get("head") or _GENESIS)
    body = {
        "id": tx_id,
        "currency": _currency(source.get("currency")),
        "postings": normalized,
        "memo": str(memo or ""),
        "metadata": deepcopy(metadata) if isinstance(metadata, dict) else {},
        "previous_hash": previous_hash,
    }
    entry = {**body, "hash": _canonical_hash(body)}
    result = deepcopy(source)
    result["entries"].append(entry)
    result["head"] = entry["hash"]
    return result


def verify(ledger: Any) -> dict[str, Any]:
    try:
        source = _require_ledger(ledger)
        expected_previous = _GENESIS
        seen: set[str] = set()
        for index, entry in enumerate(source["entries"]):
            if not isinstance(entry, dict):
                raise LedgerError(f"ledger: invalid entry at index {index}")
            tx_id = str(entry.get("id") or "")
            if not tx_id or tx_id in seen:
                raise LedgerError(f"ledger: duplicate or missing transaction id at index {index}")
            seen.add(tx_id)
            if entry.get("previous_hash") != expected_previous:
                raise LedgerError(f"ledger: broken hash chain at index {index}")
            if _currency(entry.get("currency")) != _currency(source.get("currency")):
                raise LedgerError(f"ledger: currency mismatch at index {index}")
            postings = entry.get("postings")
            if not isinstance(postings, list):
                raise LedgerError(f"ledger: invalid postings at index {index}")
            total = Decimal("0.00")
            for row in postings:
                if not isinstance(row, dict):
                    raise LedgerError(f"ledger: invalid posting at index {index}")
                total += _amount(row.get("amount", "0"))
            if total != Decimal("0.00"):
                raise LedgerError(f"ledger: unbalanced entry at index {index}")
            body = {key: value for key, value in entry.items() if key != "hash"}
            actual_hash = _canonical_hash(body)
            if entry.get("hash") != actual_hash:
                raise LedgerError(f"ledger: hash mismatch at index {index}")
            expected_previous = actual_hash
        if str(source.get("head") or _GENESIS) != expected_previous:
            raise LedgerError("ledger: head hash mismatch")
        return {"ok": True, "count": len(source["entries"]), "head": expected_previous, "error": None}
    except LedgerError as exc:
        return {"ok": False, "count": 0, "head": None, "error": str(exc)}


def balance(ledger: Any, account: Any) -> dict[str, str]:
    source = _require_ledger(ledger)
    account_name = str(account or "").strip()
    total = Decimal("0.00")
    for entry in source["entries"]:
        for row in entry.get("postings", []):
            if isinstance(row, dict) and str(row.get("account")) == account_name:
                total += _amount(row.get("amount", "0"))
    return {"type": "money", "currency": _currency(source.get("currency")), "amount": format(total, "f")}


def entries(ledger: Any) -> list[dict[str, Any]]:
    return deepcopy(_require_ledger(ledger)["entries"])


def register_ledger_functions(host: Any) -> None:
    from .host.legacy import HostFunction

    def wrap(handler):
        def call(args):
            try:
                return handler(*args)
            except LedgerError as exc:
                raise RuntimeError(str(exc)) from exc
        return call

    host.register(HostFunction("std.ledger.create", wrap(create), min_args=0, max_args=1))
    host.register(HostFunction("std.ledger.post", wrap(post), cost=2, min_args=3, max_args=5))
    host.register(HostFunction("std.ledger.verify", wrap(verify), cost=2, min_args=1, max_args=1))
    host.register(HostFunction("std.ledger.balance", wrap(balance), cost=2, min_args=2, max_args=2))
    host.register(HostFunction("std.ledger.entries", wrap(entries), cost=1, min_args=1, max_args=1))
