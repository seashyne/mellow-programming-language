"""Mellow host syscall family: money."""

from __future__ import annotations

from typing import Any, List
from decimal import Decimal as _Decimal
from decimal import InvalidOperation as _InvalidDecimal
from decimal import ROUND_HALF_UP as _ROUND_HALF_UP
from ..base import HostFunction, HostRegistry


def register_money_functions(h: HostRegistry) -> None:
    """Register the money syscalls on a fresh host registry."""
    # ----- std.money (Decimal-backed, float-free money helpers) -----
    _MONEY_TYPE = "money"
    _DEFAULT_SCALE = _Decimal("0.01")

    def _money_decimal(value: Any) -> _Decimal:
        if isinstance(value, dict) and value.get("type") == _MONEY_TYPE:
            value = value.get("amount", "0")
        try:
            return _Decimal(str(value))
        except (_InvalidDecimal, ValueError) as exc:
            raise RuntimeError(f"std.money: invalid decimal amount: {value}") from exc

    def _money_currency(value: Any = None) -> str:
        cur = "USD" if value is None else str(value).strip().upper()
        if not cur or len(cur) > 12:
            raise RuntimeError("std.money: invalid currency")
        return cur

    def _money(value: Any, currency: Any = "USD") -> dict[str, str]:
        amount = _money_decimal(value).quantize(_DEFAULT_SCALE, rounding=_ROUND_HALF_UP)
        return {"type": _MONEY_TYPE, "currency": _money_currency(currency), "amount": format(amount, "f")}

    def _as_money(value: Any) -> dict[str, str]:
        if isinstance(value, dict) and value.get("type") == _MONEY_TYPE:
            return _money(value.get("amount", "0"), value.get("currency", "USD"))
        return _money(value)

    def _same_currency(left: dict[str, str], right: dict[str, str]) -> None:
        if left.get("currency") != right.get("currency"):
            raise RuntimeError(f"std.money: currency mismatch {left.get('currency')} != {right.get('currency')}")

    def _money_of(args: List[Any]):
        currency = args[1] if len(args) >= 2 else "USD"
        return _money(args[0], currency)

    def _money_add(args: List[Any]):
        a, b = _as_money(args[0]), _as_money(args[1])
        _same_currency(a, b)
        return _money(_money_decimal(a) + _money_decimal(b), a["currency"])

    def _money_sub(args: List[Any]):
        a, b = _as_money(args[0]), _as_money(args[1])
        _same_currency(a, b)
        return _money(_money_decimal(a) - _money_decimal(b), a["currency"])

    def _money_mul(args: List[Any]):
        a = _as_money(args[0])
        return _money(_money_decimal(a) * _money_decimal(args[1]), a["currency"])

    def _money_div(args: List[Any]):
        a = _as_money(args[0])
        divisor = _money_decimal(args[1])
        if divisor == 0:
            raise RuntimeError("std.money: division by zero")
        return _money(_money_decimal(a) / divisor, a["currency"])

    def _money_quantize(args: List[Any]):
        a = _as_money(args[0])
        scale = _Decimal(str(args[1] if len(args) >= 2 else "0.01"))
        rounded = _money_decimal(a).quantize(scale, rounding=_ROUND_HALF_UP)
        return {"type": _MONEY_TYPE, "currency": a["currency"], "amount": format(rounded, "f")}

    def _money_format(args: List[Any]):
        a = _as_money(args[0])
        return f"{a['currency']} {a['amount']}"

    h.register(HostFunction('std.money.of', _money_of, cost=1, min_args=1, max_args=2))
    h.register(HostFunction('std.money.add', _money_add, cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.money.sub', _money_sub, cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.money.mul', _money_mul, cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.money.div', _money_div, cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.money.quantize', _money_quantize, cost=1, min_args=1, max_args=2))
    h.register(HostFunction('std.money.format', _money_format, cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.money.amount', lambda a: _as_money(a[0])["amount"], cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.money.currency', lambda a: _as_money(a[0])["currency"], cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.money.eq', lambda a: (_same_currency(_as_money(a[0]), _as_money(a[1])) is None) and _money_decimal(a[0]) == _money_decimal(a[1]), cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.money.lt', lambda a: (_same_currency(_as_money(a[0]), _as_money(a[1])) is None) and _money_decimal(a[0]) < _money_decimal(a[1]), cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.money.gt', lambda a: (_same_currency(_as_money(a[0]), _as_money(a[1])) is None) and _money_decimal(a[0]) > _money_decimal(a[1]), cost=1, min_args=2, max_args=2))
