"""Module-call syscall names, and named arguments folded into positional slots."""

from __future__ import annotations

from typing import List

from ...ast import Expr, Literal
from ...host.runtime import MODULE_ALLOWLIST

from .errors import UnsupportedLoweringError
from .tables import SYSCALL_ARGUMENTS


def _module_syscall(module: str, function: str) -> str:
    mod = str(module).lower()
    func = str(function).lower()
    if mod in MODULE_ALLOWLIST and func in MODULE_ALLOWLIST[mod]:
        return MODULE_ALLOWLIST[mod][func]
    return f"std.{mod}.{func}"


def _bind_call_arguments(syscall_name: str, args: List[Expr],
                         kwargs: List[tuple]) -> List[Expr]:
    signature = SYSCALL_ARGUMENTS.get(syscall_name)
    if signature is None:
        raise UnsupportedLoweringError(
            "named arguments are not yet lowered in IR pipeline")
    slots = list(args)
    filled = set(range(len(slots)))
    for raw_name, value in kwargs:
        name = str(raw_name).strip().lower().lstrip("*")
        if name not in signature:
            raise UnsupportedLoweringError(
                f"unknown named argument '{raw_name}' for syscall: {syscall_name}")
        index = signature.index(name)
        if index in filled:
            raise UnsupportedLoweringError(
                f"duplicate argument '{raw_name}' for syscall: {syscall_name}")
        while len(slots) <= index:
            slots.append(Literal(None))
        slots[index] = value
        filled.add(index)
    return slots
