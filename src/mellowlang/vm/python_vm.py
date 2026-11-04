# frinds/vm.py (v2.2)
"""The pure-Python bytecode interpreter.

`MellowLangVM` is assembled in `vm/interp/`; this module keeps the import path
every consumer already uses, plus the module-level names that used to sit above
the interpreter body.
"""

from __future__ import annotations

import sqlite3
from typing import Any, List

from ..constants import Op
from ..data_core import DataCoreError, DataStreamManager
from ..error_core import MellowLangRuntimeError
from ..host import HostRegistry, default_host
from ..range_core import MellowLangRange
from ..replay import ReplayConfig, ReplayLog
from .debugger import DebuggerMixin
from .interp import MellowLangVM
from .storage import (STORAGE_BUILTIN_NAMES, STORAGE_SLOT_NAMES, STORAGE_SYSCALL_BUILTINS,
                      StorageMixin)

__all__ = ["MellowLangVM"]
