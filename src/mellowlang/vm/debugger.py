"""The debugger mixin the interpreter assembles, split by subject.

The bodies live in `mellowlang/vm/debugger_groups/`, one mixin per subject;
this module keeps the import path `mellowlang.vm.debugger` and the
`DebuggerMixin` name `vm/interp/vm.py` and `vm/python_vm.py` import."""

from __future__ import annotations

from .debugger_groups.breakpoints import BreakpointMixin
from .debugger_groups.stepping import SteppingMixin
from .debugger_groups.inspection import InspectionMixin
from .debugger_groups.rendering import RenderingMixin


class DebuggerMixin(BreakpointMixin, SteppingMixin, InspectionMixin, RenderingMixin):
    pass
