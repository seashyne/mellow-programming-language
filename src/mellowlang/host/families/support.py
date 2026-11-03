"""Shared argument-shape predicates used by more than one syscall family."""

from __future__ import annotations


def is_list(x) -> None:
    if not isinstance(x, list):
        raise RuntimeError('std.list: expected list')


def is_dict(x) -> None:
    if not isinstance(x, dict):
        raise RuntimeError('std.map: expected map')
