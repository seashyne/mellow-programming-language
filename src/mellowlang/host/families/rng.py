"""Mellow host syscall family: rng."""

from __future__ import annotations

from typing import Any, Dict, List
from ..base import HostFunction, HostRegistry


def register_rng_functions(h: HostRegistry) -> None:
    """Register the rng syscalls on a fresh host registry."""
    # ----- std.random -----
    # Each VM run gets its own HostRegistry, and vm.py pushes RunConfig into
    # runtime_config before the first syscall, so seeding here is per run.
    import random as _random_mod
    _rng_state: Dict[str, Any] = {"rng": None}

    def _rng() -> "_random_mod.Random":
        if _rng_state["rng"] is None:
            seed = (h.runtime_config or {}).get("seed")
            _rng_state["rng"] = _random_mod.Random(int(seed)) if seed is not None else _random_mod.Random()
        return _rng_state["rng"]

    def _random(args: List[Any]):
        rng = _rng()
        if len(args) == 0:
            return rng.random()
        if len(args) == 1:
            return rng.randint(0, int(args[0]))
        lo, hi = int(args[0]), int(args[1])
        if hi < lo:
            lo, hi = hi, lo
        return rng.randint(lo, hi)

    h.register(HostFunction('std.random.range', _random, cost=1, min_args=0, max_args=2))
