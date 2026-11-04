"""The tables that hang off the code: function entries and their constants, the core module,
   the two address remaps, the deduplicated module list."""

from __future__ import annotations

from .format import FunctionEntry, ModuleEntry
from .binary import _core_module_candidates
from .consts import _add_const
from .state import Lowering


def build_function_entries(state: Lowering) -> None:
    """One FunctionEntry and one func constant per known function, with the local count the
       scope scan found rather than the parameter count."""
    for name, meta in state.func_table.items():
        # Use the scanned local_count (all vars in function) not just param_count
        _scanned_lc = len(state._func_locals.get(name, {}))
        _lc = _scanned_lc if _scanned_lc > 0 else int(meta.get('param_count', 0))
        meta['local_count'] = _lc
        state.functions.append(FunctionEntry(
            name=name,
            address=int(meta.get('address', 0)),
            arity=int(meta.get('param_count', 0)),
            local_count=_lc,
            flags=int(meta.get('flags', 0)),
        ))
        state.func_const_slots[name] = _add_const(state.const_pool, state.const_index, {
            'tag': 'func',
            'value': {
                'address': int(meta.get('address', 0)),
                'arity': int(meta.get('param_count', 0)),
                'local_count': _lc,
                'flags': int(meta.get('flags', 0)),
            }
        })


def seed_core_module(state: Lowering) -> None:
    """Record the core module when the runtime ships one."""
    core = next((p for p in _core_module_candidates() if p.exists()), None)
    if core is not None:
        state.modules.append(ModuleEntry(name='core', flags=0, is_core=True))


def remap_function_addresses(state: Lowering) -> None:
    """Function addresses are source PCs; rewrite them, and the func constants carrying them,
       to the image PCs the ARG skip produced."""
    # ── pass 2a: remap function body addresses src_pc → img_pc ─────────────
    # func_table addresses are SOURCE bytecode PCs (point to first ARG or first
    # real instruction).  After ARG-skip lowering the image PCs differ.
    for fname, fmeta in state.func_table.items():
        src_addr = int(fmeta.get('address', 0))
        img_addr = state._src_to_img.get(src_addr, src_addr)
        fmeta['address'] = img_addr
    # Rebuild functions list and func_const_slots with corrected addresses
    state.functions.clear()
    for name, meta in state.func_table.items():
        _scanned_lc = len(state._func_locals.get(name, {}))
        _lc = _scanned_lc if _scanned_lc > 0 else int(meta.get('param_count', 0))
        state.functions.append(FunctionEntry(
            name=name,
            address=int(meta['address']),
            arity=int(meta.get('param_count', 0)),
            local_count=_lc,
            flags=int(meta.get('flags', 0)),
        ))
        # Update the func constant in const_pool with corrected address
        slot = state.func_const_slots.get(name)
        if slot is not None:
            state.const_pool[slot] = {
                'tag': 'func',
                'value': {
                    'address': int(meta['address']),
                    'arity': int(meta.get('param_count', 0)),
                    'local_count': _lc,
                    'flags': int(meta.get('flags', 0)),
                }
            }


def rewrite_jump_targets(state: Lowering) -> None:
    """The jump targets recorded during emit become image PCs."""
    # ── pass 2b: rewrite JUMP/JIF targets from src_pc to img_pc ─────────────
    for img_idx, field in state._jump_patches:
        src_target = state.code[img_idx][1]   # field 'a' is always index 1 in tuple
        img_target = state._src_to_img.get(src_target, src_target)
        op_, a_, b_, c_ = state.code[img_idx]
        state.code[img_idx] = (op_, img_target, b_, c_)


def dedupe_modules(state: Lowering) -> list[ModuleEntry]:
    """Keep the first mention of each module name."""
    seen: set[str] = set()
    unique_modules: list[ModuleEntry] = []
    for mod in state.modules:
        if mod.name in seen:
            continue
        seen.add(mod.name)
        unique_modules.append(mod)
    return unique_modules
