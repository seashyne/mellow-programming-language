"""One source instruction in, one image instruction out - the opcode chain."""

from __future__ import annotations

from ..constants import Op

from .ops import _COMPARE_MAP, _STANDALONE_OPS, _SYSCALL_NAME_MAP
from .format import ModuleEntry
from .consts import _add_const, _const_from_python, _span_tuple
from .state import Lowering


def emit_instruction(state: Lowering, ins, pc: int) -> 'tuple[int, int, int, int] | None':
    """Lower one source instruction to one image instruction, or return None when the
       instruction only feeds the one that follows it."""
    op = ins[0]
    a = b = c = 0
    if op == Op.HALT:
        sop = _STANDALONE_OPS['HALT']

    elif op == Op.PUSH:
        val = ins[1]
        # Detect PUSH of a syscall name (e.g. 'std.len', 'std.range')
        if isinstance(val, str) and val in _SYSCALL_NAME_MAP:
            state._pending_syscall_name = val
            state.spans.append(_span_tuple(state.spans_src, pc, state.compiled))
            return None   # consumed; SYSCALL handler will emit the real instruction
        # Normal value push — do NOT reset _pending_syscall_name here.
        # The name may have been set by a preceding PUSH('std.len') and the
        # args (LOAD xs, etc.) follow before the SYSCALL opcode.
        sop = _STANDALONE_OPS['PUSH_CONST']
        a = _add_const(state.const_pool, state.const_index, _const_from_python(val))

    elif op in (Op.STORE, Op.STORE_KEEP, Op.STORE_AUTO):
        sop = _STANDALONE_OPS['STORE_LOCAL']
        a = state.slot_for(str(ins[1]), pc)

    elif op == Op.LOAD:
        sop = _STANDALONE_OPS['LOAD_LOCAL']
        a = state.slot_for(str(ins[1]), pc)

    elif op == Op.ADD:  sop = _STANDALONE_OPS['ADD']
    elif op == Op.SUB:  sop = _STANDALONE_OPS['SUB']
    elif op == Op.MUL:  sop = _STANDALONE_OPS['MUL']
    elif op == Op.DIV:  sop = _STANDALONE_OPS['DIV']
    elif op == Op.MOD:  sop = _STANDALONE_OPS['MOD']
    elif op == Op.POW_OP: sop = _STANDALONE_OPS['POW']
    elif op == Op.BOOL_AND: sop = _STANDALONE_OPS['BOOL_AND']
    elif op == Op.BOOL_OR:  sop = _STANDALONE_OPS['BOOL_OR']
    elif op == Op.BOOL_NOT: sop = _STANDALONE_OPS['BOOL_NOT']
    elif op == Op.GETITEM:  sop = _STANDALONE_OPS['GETITEM']
    elif op == Op.LEN:      sop = _STANDALONE_OPS['LEN']

    elif op == Op.JUMP:
        sop = _STANDALONE_OPS['JUMP']
        a = int(ins[1])   # src_pc target — will be patched in pass 2
        state._jump_patches.append((len(state.code), 'a'))

    elif op == Op.JIF:
        sop = _STANDALONE_OPS['JUMP_IF_FALSE']
        a = int(ins[1])   # src_pc target — will be patched in pass 2
        state._jump_patches.append((len(state.code), 'a'))

    elif op == Op.CALL:
        name, argc = str(ins[1]), int(ins[2])
        # Check if this is a call to a builtin (range, len, etc.)
        if name in _SYSCALL_NAME_MAP:
            sop = _STANDALONE_OPS['SYSCALL']
            a = _SYSCALL_NAME_MAP[name]
            b = argc
            c = 1   # push result
        elif name not in state.func_table:
            raise ValueError(f'Unsupported standalone CALL target: {name!r}')
        else:
            state.code.append((_STANDALONE_OPS['PUSH_CONST'], state.func_const_slots[name], 0, 0))
            state.spans.append(_span_tuple(state.spans_src, pc, state.compiled))
            sop = _STANDALONE_OPS['CALL']
            a = argc

    elif op == Op.RETURN:
        sop = _STANDALONE_OPS['RETURN']

    elif op == Op.POP:
        sop = _STANDALONE_OPS['POP']

    elif op == Op.COMPARE:
        sop = _STANDALONE_OPS['COMPARE']
        a = _COMPARE_MAP[str(ins[1])]

    elif op == Op.BUILD_LIST:
        sop = _STANDALONE_OPS['BUILD_LIST']
        a = int(ins[1])

    elif op == Op.BUILD_MAP:
        sop = _STANDALONE_OPS['BUILD_MAP']
        a = int(ins[1])

    elif op == Op.IMPORT:
        sop = _STANDALONE_OPS['IMPORT']
        state.modules.append(ModuleEntry(name=str(ins[1]), flags=0, is_core=False))
        a = len(state.modules) - 1

    elif op == Op.SYSCALL:
        argc = int(ins[1])
        if state._pending_syscall_name == 'std.range':
            # range(start, stop) → BUILD_LIST of integers, emitted inline
            # We can't know values at compile-time in general, so emit a
            # SYSCALL with a dedicated range syscall ID (20).
            sop = _STANDALONE_OPS['SYSCALL']
            a = 20   # syscall ID 20 = range(start,stop) -> list
            b = argc
            c = 1    # push result
            state._pending_syscall_name = None
        elif state._pending_syscall_name is not None:
            sid = _SYSCALL_NAME_MAP.get(state._pending_syscall_name, 0)
            sop = _STANDALONE_OPS['SYSCALL']
            a = sid
            b = argc
            c = 1
            state._pending_syscall_name = None
        else:
            sop = _STANDALONE_OPS['SYSCALL']
            a = 0
            b = argc
            c = 1

    elif op == Op.PRINT:
        sop = _STANDALONE_OPS['SYSCALL']
        a, b, c = 1, 1, 0

    elif op == Op.PRINTN:
        sop = _STANDALONE_OPS['SYSCALL']
        a, b, c = 13, int(ins[1]), 0

    elif op == Op.PUSH_FUNC:
        name = str(ins[1])
        if name not in state.func_const_slots:
            raise ValueError(f'PUSH_FUNC: unknown function {name!r}')
        sop = _STANDALONE_OPS['PUSH_CONST']
        a = state.func_const_slots[name]

    elif op == Op.CALL_VAL:
        sop = _STANDALONE_OPS['CALL_VAL']
        a = int(ins[1])

    elif op == Op.STOP:
        sop = _STANDALONE_OPS['HALT']

    elif op == Op.ARG:
        # Consumed during func_table reconstruction; no code emitted.
        state.spans.append(_span_tuple(state.spans_src, pc, state.compiled))
        return None

    elif op in (Op.WAIT, Op.ASK, Op.SEED, Op.GLOBAL_SEED, Op.RANDFLOAT,
                Op.RANDOM, Op.SHOW_PREC, Op.SAVE, Op.SAVE_VAL, Op.LOAD_F,
                Op.LIST_HAS, Op.LIST_PUT, Op.SLICE, Op.TRY, Op.ENDTRY):
        # Unsupported in standalone — halt with sentinel code
        sop = _STANDALONE_OPS['HALT']
        a = 0xFF

    else:
        raise ValueError(f'Unsupported opcode for standalone image: {ins!r}')
    return (sop, a, b, c)
