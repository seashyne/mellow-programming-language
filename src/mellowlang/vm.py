"""mellowlang.vm

Stable public VM API (v1.0.3+).

- MellowVM: facade used by CLI/tooling (stable contract)
- RunConfig: stable config object
- MellowLangVM: legacy VM implementation (kept for back-compat)
"""

from __future__ import annotations

from .vm.vm import MellowVM, RunConfig
from .vm.legacy import MellowLangVM

__all__ = ["MellowVM", "RunConfig", "MellowLangVM"]
