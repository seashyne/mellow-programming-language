"""Host assembly: builds a fresh registry from the syscall families."""

from __future__ import annotations

from .base import MODULE_ALLOWLIST, HostFunction, HostRegistry
from .families import (
    register_modules_functions,
    register_basic_functions,
    register_game_functions,
    register_ai_behaviour_functions,
    register_text_list_functions,
    register_math_game_functions,
    register_list_functional_functions,
    register_types_assert_functions,
    register_money_functions,
    register_math_core_functions,
    register_vectors_functions,
    register_rng_functions,
    register_time_range_functions,
    register_pythonics_functions,
)


def default_host() -> HostRegistry:
    """Host ตัวอย่าง (ให้รันทดสอบได้ทันที)"""
    h = HostRegistry()
    h.register(HostFunction(
        name="sys.echo",
        handler=lambda a: a[0] if a else None,
        cost=1,
        min_args=0,
        max_args=1
    ))

    register_modules_functions(h)
    register_basic_functions(h)
    register_game_functions(h)
    register_ai_behaviour_functions(h)
    register_text_list_functions(h)
    register_math_game_functions(h)
    register_list_functional_functions(h)
    register_types_assert_functions(h)
    register_money_functions(h)
    from ..ledger_core import register_ledger_functions
    register_ledger_functions(h)
    from ..interop_core import register_interop_functions
    register_interop_functions(h)
    from ..sdk_core import register_sdk_functions
    register_sdk_functions(h)

    register_math_core_functions(h)
    register_vectors_functions(h)
    register_rng_functions(h)
    register_time_range_functions(h)
    # ----- v1.4.8: AI Engine -----
    try:
        from ..ai_core import register_ai_functions
        register_ai_functions(h)
    except Exception:
        pass  # AI core optional

    register_pythonics_functions(h)
    return h

# Back-compatible import paths: host.runtime has always exported these names.
__all__ = ["MODULE_ALLOWLIST", "HostRegistry", "HostFunction", "default_host"]
