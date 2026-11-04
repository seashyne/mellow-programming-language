"""The interpreter class: the state, the opcode families and the driver."""

from __future__ import annotations

from ..debugger import DebuggerMixin
from ..storage import StorageMixin
from .call_fs import FsGroupMixin
from .call_net import NetGroupMixin
from .call_save import SaveGroupMixin
from .call_storage import StorageCallMixin
from .errors import ErrorMixin
from .events import EventMixin
from .execute import ExecuteMixin
from .frame import FrameMixin
from .invocation import InvocationMixin
from .op_bindings import BindingMixin
from .op_call import CallMixin
from .op_collections import CollectionMixin
from .op_control import ControlMixin
from .op_import import ImportMixin
from .op_io import IOMixin
from .op_math import MathMixin
from .syscalls import SyscallMixin


class MellowLangVM(
    ControlMixin, BindingMixin, MathMixin, IOMixin, CollectionMixin,
    CallMixin, ImportMixin, StorageCallMixin, SaveGroupMixin, NetGroupMixin,
    FsGroupMixin, FrameMixin, ErrorMixin, SyscallMixin, EventMixin,
    InvocationMixin, ExecuteMixin, DebuggerMixin, StorageMixin,
):
    """The pure-Python bytecode interpreter.

    vm/python_vm.py re-exports this name. The body lives in interp/: one
    _exec_* method per opcode family behind ExecuteMixin.OP_HANDLERS, the
    storage builtin name groups behind StorageCallMixin, and the frame,
    error, syscall, event and call helpers beside them."""
