"""Who owns which bytecode: rebuild the function table when the compiler left it empty, and map
   each function's parameters and locals to slots."""

from __future__ import annotations

from ..constants import Op

from .state import Lowering


def rebuild_func_table(state: Lowering) -> None:
    """Recover the function table from the ARG markers when the compiler left it empty, then
       point each entry at the start of its own argument block."""
    # Bytecode scan: JUMP target -> [ARG b, ARG a, ...body..., RETURN]
    state._current_func = None
    _pending_args: list[str] = []
    for _pc, _ins in enumerate(state.bytecode):
        _op = _ins[0]
        if _op == Op.JUMP and _pc == 0:
            # main body starts at ins[1], function bodies are before it
            pass
        if _op == Op.ARG:
            _pending_args.append(str(_ins[1]))
        elif _op in (Op.LOAD, Op.STORE, Op.STORE_KEEP, Op.STORE_AUTO,
                     Op.ADD, Op.SUB, Op.MUL, Op.DIV, Op.RETURN,
                     Op.PUSH, Op.COMPARE, Op.JIF, Op.JUMP, Op.POP,
                     Op.BOOL_AND, Op.BOOL_OR, Op.BOOL_NOT,
                     Op.GETITEM, Op.LEN, Op.BUILD_LIST, Op.BUILD_MAP,
                     Op.SYSCALL, Op.PRINT, Op.PRINTN, Op.HALT):
            if _op == Op.ARG:
                pass  # handled above
        elif _op == Op.CALL:
            # CALL ('funcname', argc) — register if not yet known
            _fname, _argc = str(_ins[1]), int(_ins[2])
            if _fname not in state.func_table:
                state.func_table[_fname] = {'param_count': _argc, 'local_count': _argc,
                                      'address': 0, 'flags': 0}

    # Second pass: find actual address of each function (ARG block start - param_count)
    for _pc, _ins in enumerate(state.bytecode):
        if _ins[0] == Op.ARG:
            # ARGs appear in reverse order right after JUMP-over
            # Walk back to find the first ARG in this block
            _block_start = _pc
            while _block_start > 0 and state.bytecode[_block_start - 1][0] == Op.ARG:
                _block_start -= 1
            # Walk forward from block_start to find matching CALL
            _nargs = 0
            _p = _block_start
            while _p < len(state.bytecode) and state.bytecode[_p][0] == Op.ARG:
                _nargs += 1
                _p += 1
            # Find which function name has this arity; match by scanning CALL
            for _fname, _meta in state.func_table.items():
                if _meta.get('param_count', 0) == _nargs and _meta.get('address', 0) == 0:
                    _meta['address'] = _block_start
                    _meta['local_count'] = _nargs
                    break


def scan_func_scopes(state: Lowering) -> None:
    """Walk the bytecode once per function: the ARG block gives the parameters in declaration
       order, the body gives the rest of the slots."""
    # v2.3.4: scope-aware slot allocation
    # Build per-function local variable maps from ARG sequences in bytecode.
    # Each function body is preceded by ARG('paramN'), ARG('paramN-1'), ... .
    # The function's locals are: params first (in declaration order), then other vars.
    # Map bytecode addresses back to function names
    _addr_to_func: dict[int, str] = {}
    for fname, fmeta in state.func_table.items():
        _addr_to_func[int(fmeta.get('address', 0))] = fname

    # Scan bytecode to find function boundaries and ARG sequences
    i_scan = 0
    while i_scan < len(state.bytecode):
        ins_s = state.bytecode[i_scan]
        if ins_s[0] == Op.JUMP and i_scan == 0:
            # First JUMP skips over function bodies
            pass
        if i_scan in _addr_to_func:
            fname = _addr_to_func[i_scan]
            # Collect ARGs (they appear in reverse param order)
            args_rev = []
            j = i_scan
            while j < len(state.bytecode) and state.bytecode[j][0] == Op.ARG:
                args_rev.append(str(state.bytecode[j][1]))
                j += 1
            # ARGs are stored reversed (last param first), reverse to get declaration order
            params = list(reversed(args_rev))
            # Find end of this function (first RETURN after body, or next JUMP skip)
            end_j = j
            while end_j < len(state.bytecode) and state.bytecode[end_j][0] != Op.HALT:
                if state.bytecode[end_j][0] == Op.RETURN:
                    end_j += 1
                    # skip implicit "return None" PUSH+RETURN
                    while end_j < len(state.bytecode) and state.bytecode[end_j][0] in (Op.PUSH, Op.RETURN):
                        end_j += 1
                    break
                end_j += 1
            state._func_ranges.append((i_scan, end_j, fname))
            # Build local map: params get slots 0..N-1, other vars get next slots
            local_map: dict[str, int] = {}
            for idx, p in enumerate(params):
                local_map[p] = idx
            # Scan body for additional STORE/LOAD variable names
            for k in range(j, end_j):
                if k < len(state.bytecode):
                    ins_k = state.bytecode[k]
                    if ins_k[0] in (Op.STORE, Op.STORE_KEEP, Op.STORE_AUTO, Op.LOAD):
                        vname = str(ins_k[1])
                        if vname not in local_map:
                            local_map[vname] = len(local_map)
            state._func_locals[fname] = local_map
        i_scan += 1
