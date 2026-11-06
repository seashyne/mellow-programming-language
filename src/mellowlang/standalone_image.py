"""The .mvi standalone image: the binary format, the lowering pass that fills
it, and the compile/run surface on top of both.

The bodies live in `mellowlang/mvi/`, one module per concern; this module keeps
the import path `mellowlang.standalone_image` that standalone_runtime and the
tests already use, so no caller needs a second home."""

from __future__ import annotations

from .mvi.ops import _COMPARE_MAP, _STANDALONE_OPS, _SYSCALL_NAME_MAP
from .mvi.format import (
    EventEntry,
    FunctionEntry,
    MAGIC,
    ModuleEntry,
    StandaloneImage,
    VERSION,
    _pack_string,
)
from .mvi.binary import _core_module_candidates, _project_root, _standalone_binary
from .mvi.consts import _add_const, _const_from_python, _span_tuple
from .mvi.lowering import lower_compiled_to_standalone_image
from .mvi.compile import compile_file_to_standalone_image, compile_source_to_standalone_image, run_standalone_image
