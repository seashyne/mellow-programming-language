"""The pass itself, running the blocks in the order the monolith ran them."""

from __future__ import annotations

from ..compiler.compiler import CompiledProgram

from .ops import _STANDALONE_OPS
from .format import EventEntry, StandaloneImage
from .consts import _span_tuple
from .state import Lowering
from .scopes import rebuild_func_table, scan_func_scopes
from .emit import emit_instruction
from .entries import (
    build_function_entries,
    dedupe_modules,
    remap_function_addresses,
    rewrite_jump_targets,
    seed_core_module,
)


def lower_compiled_to_standalone_image(compiled: CompiledProgram, *, source_name: str = '<memory>') -> StandaloneImage:
    state = Lowering(
        compiled=compiled,
        bytecode=list(compiled.bytecode),
        spans_src=list(compiled.span_map or []),
        func_table={k: dict(v) for k, v in (compiled.func_table or {}).items()},
    )

    # ── build func_table ──────────────────────────────────────────────────────
    # New IR compiler populates func_table; bytecode compiler does not.
    # For bytecode, reconstruct func_table by scanning ARG markers.
    if not state.func_table:
        rebuild_func_table(state)
    scan_func_scopes(state)
    build_function_entries(state)
    seed_core_module(state)

    for pc, ins in enumerate(state.bytecode):
        state._src_to_img[pc] = len(state.code)   # record before we (maybe) emit
        state.enter_scope(pc)
        emitted = emit_instruction(state, ins, pc)
        if emitted is None:
            continue
        state.code.append(emitted)
        state.spans.append(_span_tuple(state.spans_src, pc, state.compiled))

    if not state.code or state.code[-1][0] != _STANDALONE_OPS['HALT']:
        state.code.append((_STANDALONE_OPS['HALT'], 0, 0, 0))
        state.spans.append((0, 1, 0, 1))

    remap_function_addresses(state)
    rewrite_jump_targets(state)
    unique_modules = dedupe_modules(state)

    events = [EventEntry(name='startup', target=0, flags=1)]
    return StandaloneImage(
        source_name=source_name,
        consts=state.const_pool,
        code=state.code,
        spans=state.spans,
        globals=state.globals_map,
        functions=state.functions,
        events=events,
        modules=unique_modules,
        pipeline=compiled.pipeline,
    )
