from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .compiler.compiler import Compiler, CompiledProgram
from .constants import Op

MAGIC = b"MLVI0200"
VERSION = 2

_STANDALONE_OPS = {
    'HALT': 0,
    'PUSH_CONST': 1,
    'LOAD_LOCAL': 2,
    'STORE_LOCAL': 3,
    'ADD': 4,
    'SUB': 5,
    'MUL': 6,
    'DIV': 7,
    'JUMP': 8,
    'JUMP_IF_FALSE': 9,
    'CALL': 10,
    'RETURN': 11,
    'POP': 12,
    'COMPARE': 13,
    'BUILD_LIST': 14,
    'BUILD_MAP': 15,
    'IMPORT': 16,
    'SYSCALL': 17,
    'DEBUG_SNAPSHOT': 18,
    'DUP': 19,
    # v2.3.4: extended opcode surface
    'MOD': 20,
    'POW': 21,
    'BOOL_AND': 22,
    'BOOL_OR': 23,
    'BOOL_NOT': 24,
    'GETITEM': 25,
    'LEN': 26,
    'PUSH_FUNC': 27,
    'CALL_VAL': 28,
    'STOP': 29,
}
_COMPARE_MAP = {'==': 0, '!=': 1, '<': 2, '<=': 3, '>': 4, '>=': 5}

# v2.3.4: syscall name → C runtime syscall ID (must match mellowrt_main.c)
# Also covers builtin CALL targets from the new IR compiler (e.g. CALL 'range')
_SYSCALL_NAME_MAP = {
    'std.print':   1, 'print':   1,
    'std.len':     2, 'len':     2,
    'std.clock':   3, 'clock_ms': 3,
    'std.getenv':  4, 'getenv':  4,
    'std.str':     5, 'str':     5,
    'std.type':    6, 'type':    6,
    'std.abs':     7, 'abs':     7,
    'std.floor':   8, 'floor':   8,
    'std.ceil':    9, 'ceil':    9,
    'std.sqrt':   10, 'sqrt':   10,
    'std.min':    11, 'min':    11,
    'std.max':    12, 'max':    12,
    # range() builtin
    'range':  20,
    'std.range': 20,
}

@dataclass
class FunctionEntry:
    name: str
    address: int
    arity: int
    local_count: int
    flags: int = 0

@dataclass
class EventEntry:
    name: str
    target: int
    flags: int = 0

@dataclass
class ModuleEntry:
    name: str
    flags: int = 0
    is_core: bool = False

@dataclass
class StandaloneImage:
    source_name: str
    consts: list[dict[str, Any]]
    code: list[tuple[int, int, int, int]]
    spans: list[tuple[int, int, int, int]]
    globals: dict[str, int]
    functions: list[FunctionEntry]
    events: list[EventEntry]
    modules: list[ModuleEntry]
    pipeline: str

    def to_bytes(self) -> bytes:
        buf = bytearray()
        buf += MAGIC
        buf += struct.pack('<II', VERSION, 0)
        buf += _pack_string(self.source_name)
        buf += _pack_string(self.pipeline)
        buf += struct.pack(
            '<7I',
            len(self.consts),
            len(self.code),
            len(self.spans),
            len(self.globals),
            len(self.functions),
            len(self.events),
            len(self.modules),
        )
        for name, slot in sorted(self.globals.items(), key=lambda kv: kv[1]):
            buf += struct.pack('<I', int(slot))
            buf += _pack_string(name)
        for fn in self.functions:
            buf += _pack_string(fn.name)
            buf += struct.pack('<IHHH', int(fn.address), int(fn.arity), int(fn.local_count), int(fn.flags))
        for ev in self.events:
            buf += _pack_string(ev.name)
            buf += struct.pack('<II', int(ev.target), int(ev.flags))
        for mod in self.modules:
            buf += _pack_string(mod.name)
            flags = int(mod.flags) | (1 if mod.is_core else 0)
            buf += struct.pack('<I', flags)
        for c in self.consts:
            tag = c['tag']
            if tag == 'none':
                buf += struct.pack('<B', 0)
            elif tag == 'bool':
                buf += struct.pack('<BB', 1, 1 if c['value'] else 0)
            elif tag == 'i64':
                buf += struct.pack('<Bq', 2, int(c['value']))
            elif tag == 'f64':
                buf += struct.pack('<Bd', 3, float(c['value']))
            elif tag == 'str':
                data = str(c['value']).encode('utf-8')
                buf += struct.pack('<BI', 4, len(data)) + data
            elif tag == 'func':
                fn = c['value']
                buf += struct.pack('<BIHHH', 8, int(fn['address']), int(fn['arity']), int(fn['local_count']), int(fn.get('flags', 0)))
            else:
                raise ValueError(f'Unsupported constant tag for standalone image: {tag}')
        for op, a, b, c in self.code:
            buf += struct.pack('<Biii', int(op), int(a), int(b), int(c))
        for sl, sc, el, ec in self.spans:
            buf += struct.pack('<IIII', int(sl), int(sc), int(el), int(ec))
        return bytes(buf)


def _pack_string(text: str) -> bytes:
    data = text.encode('utf-8')
    return struct.pack('<I', len(data)) + data


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _standalone_binary() -> Path:
    root = _project_root() / 'native' / 'standalone' / 'build'
    return root / ('mellowrt.exe' if os.name == 'nt' else 'mellowrt')


def _core_module_candidates() -> list[Path]:
    root = _project_root()
    return [root / 'stdlib' / 'core.mellow', root / 'stdlib' / 'core.mel']


def _add_const(const_pool: list[dict[str, Any]], const_index: dict[str, int], spec: dict[str, Any]) -> int:
    key = json.dumps(spec, sort_keys=True, ensure_ascii=False)
    if key in const_index:
        return const_index[key]
    idx = len(const_pool)
    const_pool.append(spec)
    const_index[key] = idx
    return idx


def _const_from_python(value: Any) -> dict[str, Any]:
    if value is None:
        return {'tag': 'none'}
    if isinstance(value, bool):
        return {'tag': 'bool', 'value': bool(value)}
    if isinstance(value, int) and not isinstance(value, bool):
        return {'tag': 'i64', 'value': int(value)}
    if isinstance(value, float):
        return {'tag': 'f64', 'value': float(value)}
    if isinstance(value, str):
        return {'tag': 'str', 'value': value}
    raise ValueError(f'Unsupported Python constant for standalone image: {value!r}')


def lower_compiled_to_standalone_image(compiled: CompiledProgram, *, source_name: str = '<memory>') -> StandaloneImage:
    bytecode = list(compiled.bytecode)
    spans_src = list(compiled.span_map or [])
    const_pool: list[dict[str, Any]] = []
    const_index: dict[str, int] = {}
    code: list[tuple[int, int, int, int]] = []
    spans: list[tuple[int, int, int, int]] = []
    globals_map: dict[str, int] = {}

    # ── build func_table ──────────────────────────────────────────────────
    # New IR compiler populates func_table; legacy compiler does not.
    # For legacy bytecode, reconstruct func_table by scanning ARG markers.
    func_table = {k: dict(v) for k, v in (compiled.func_table or {}).items()}
    if not func_table:
        # Legacy scan: JUMP target → [ARG b, ARG a, ...body..., RETURN]
        _current_func = None
        _pending_args: list[str] = []
        for _pc, _ins in enumerate(bytecode):
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
                if _fname not in func_table:
                    func_table[_fname] = {'param_count': _argc, 'local_count': _argc,
                                          'address': 0, 'flags': 0}

        # Second pass: find actual address of each function (ARG block start - param_count)
        for _pc, _ins in enumerate(bytecode):
            if _ins[0] == Op.ARG:
                # ARGs appear in reverse order right after JUMP-over
                # Walk back to find the first ARG in this block
                _block_start = _pc
                while _block_start > 0 and bytecode[_block_start - 1][0] == Op.ARG:
                    _block_start -= 1
                # Walk forward from block_start to find matching CALL
                _nargs = 0
                _p = _block_start
                while _p < len(bytecode) and bytecode[_p][0] == Op.ARG:
                    _nargs += 1
                    _p += 1
                # Find which function name has this arity; match by scanning CALL
                for _fname, _meta in func_table.items():
                    if _meta.get('param_count', 0) == _nargs and _meta.get('address', 0) == 0:
                        _meta['address'] = _block_start
                        _meta['local_count'] = _nargs
                        break

    # v2.3.4: scope-aware slot allocation
    # Build per-function local variable maps from ARG sequences in legacy bytecode.
    # Each function body is preceded by ARG('paramN'), ARG('paramN-1'), ... in legacy.
    # The function's locals are: params first (in declaration order), then other vars.
    _func_locals: dict[str, dict[str, int]] = {}   # func_name → {var: slot}
    _func_ranges: list[tuple[int, int, str]] = []  # (start_pc, end_pc, func_name)

    # Map bytecode addresses back to function names
    _addr_to_func: dict[int, str] = {}
    for fname, fmeta in func_table.items():
        _addr_to_func[int(fmeta.get('address', 0))] = fname

    # Scan bytecode to find function boundaries and ARG sequences
    i_scan = 0
    while i_scan < len(bytecode):
        ins_s = bytecode[i_scan]
        if ins_s[0] == Op.JUMP and i_scan == 0:
            # First JUMP skips over function bodies
            pass
        if i_scan in _addr_to_func:
            fname = _addr_to_func[i_scan]
            # Collect ARGs (they appear in reverse param order)
            args_rev = []
            j = i_scan
            while j < len(bytecode) and bytecode[j][0] == Op.ARG:
                args_rev.append(str(bytecode[j][1]))
                j += 1
            # ARGs are stored reversed (last param first), reverse to get declaration order
            params = list(reversed(args_rev))
            # Find end of this function (first RETURN after body, or next JUMP skip)
            end_j = j
            while end_j < len(bytecode) and bytecode[end_j][0] != Op.HALT:
                if bytecode[end_j][0] == Op.RETURN:
                    end_j += 1
                    # skip implicit "return None" PUSH+RETURN
                    while end_j < len(bytecode) and bytecode[end_j][0] in (Op.PUSH, Op.RETURN):
                        end_j += 1
                    break
                end_j += 1
            _func_ranges.append((i_scan, end_j, fname))
            # Build local map: params get slots 0..N-1, other vars get next slots
            local_map: dict[str, int] = {}
            for idx, p in enumerate(params):
                local_map[p] = idx
            # Scan body for additional STORE/LOAD variable names
            for k in range(j, end_j):
                if k < len(bytecode):
                    ins_k = bytecode[k]
                    if ins_k[0] in (Op.STORE, Op.STORE_KEEP, Op.STORE_AUTO, Op.LOAD):
                        vname = str(ins_k[1])
                        if vname not in local_map:
                            local_map[vname] = len(local_map)
            _func_locals[fname] = local_map
        i_scan += 1

    # Determine current function scope during lowering
    _current_func: str | None = None
    _current_func_end: int = -1

    def slot_for(name: str, src_pc: int = -1) -> int:
        # If inside a function, use function-local slot
        if _current_func and name in _func_locals.get(_current_func, {}):
            return _func_locals[_current_func][name]
        # Global scope
        if name not in globals_map:
            globals_map[name] = len(globals_map)
        return globals_map[name]

    func_const_slots: dict[str, int] = {}
    functions: list[FunctionEntry] = []
    for name, meta in func_table.items():
        # Use the scanned local_count (all vars in function) not just param_count
        _scanned_lc = len(_func_locals.get(name, {}))
        _lc = _scanned_lc if _scanned_lc > 0 else int(meta.get('param_count', 0))
        meta['local_count'] = _lc
        functions.append(FunctionEntry(
            name=name,
            address=int(meta.get('address', 0)),
            arity=int(meta.get('param_count', 0)),
            local_count=_lc,
            flags=int(meta.get('flags', 0)),
        ))
        func_const_slots[name] = _add_const(const_pool, const_index, {
            'tag': 'func',
            'value': {
                'address': int(meta.get('address', 0)),
                'arity': int(meta.get('param_count', 0)),
                'local_count': _lc,
                'flags': int(meta.get('flags', 0)),
            }
        })

    modules: list[ModuleEntry] = []
    core = next((p for p in _core_module_candidates() if p.exists()), None)
    if core is not None:
        modules.append(ModuleEntry(name='core', flags=0, is_core=True))

    # Track pending syscall name pushed before SYSCALL opcode
    _pending_syscall_name: str | None = None
    # v2.3.4: two-pass JUMP target fix
    # src_pc → image instruction index (after skipped ARGs are removed)
    _src_to_img: dict[int, int] = {}
    # (image_instr_index, field) pairs that hold a src_pc jump target to patch
    _jump_patches: list[tuple[int, str]] = []  # (img_idx, 'a')

    for pc, ins in enumerate(bytecode):
        _src_to_img[pc] = len(code)   # record before we (maybe) emit
        # Track function scope transitions
        for (fstart, fend, fname) in _func_ranges:
            if pc == fstart:
                _current_func = fname
                _current_func_end = fend
                break
            if pc >= fend and _current_func == fname:
                _current_func = None
                _current_func_end = -1
        op = ins[0]
        a = b = c = 0

        if op == Op.HALT:
            sop = _STANDALONE_OPS['HALT']

        elif op == Op.PUSH:
            val = ins[1]
            # Detect PUSH of a syscall name (e.g. 'std.len', 'std.range')
            if isinstance(val, str) and val in _SYSCALL_NAME_MAP:
                _pending_syscall_name = val
                spans.append(_span_tuple(spans_src, pc, compiled))
                continue   # consumed; SYSCALL handler will emit the real instruction
            # Normal value push — do NOT reset _pending_syscall_name here.
            # The name may have been set by a preceding PUSH('std.len') and the
            # args (LOAD xs, etc.) follow before the SYSCALL opcode.
            sop = _STANDALONE_OPS['PUSH_CONST']
            a = _add_const(const_pool, const_index, _const_from_python(val))

        elif op in (Op.STORE, Op.STORE_KEEP, Op.STORE_AUTO):
            sop = _STANDALONE_OPS['STORE_LOCAL']
            a = slot_for(str(ins[1]), pc)

        elif op == Op.LOAD:
            sop = _STANDALONE_OPS['LOAD_LOCAL']
            a = slot_for(str(ins[1]), pc)

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
            _jump_patches.append((len(code), 'a'))

        elif op == Op.JIF:
            sop = _STANDALONE_OPS['JUMP_IF_FALSE']
            a = int(ins[1])   # src_pc target — will be patched in pass 2
            _jump_patches.append((len(code), 'a'))

        elif op == Op.CALL:
            name, argc = str(ins[1]), int(ins[2])
            # Check if this is a call to a builtin (range, len, etc.)
            if name in _SYSCALL_NAME_MAP:
                sop = _STANDALONE_OPS['SYSCALL']
                a = _SYSCALL_NAME_MAP[name]
                b = argc
                c = 1   # push result
            elif name not in func_table:
                raise ValueError(f'Unsupported standalone CALL target: {name!r}')
            else:
                code.append((_STANDALONE_OPS['PUSH_CONST'], func_const_slots[name], 0, 0))
                spans.append(_span_tuple(spans_src, pc, compiled))
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
            modules.append(ModuleEntry(name=str(ins[1]), flags=0, is_core=False))
            a = len(modules) - 1

        elif op == Op.SYSCALL:
            argc = int(ins[1])
            if _pending_syscall_name == 'std.range':
                # range(start, stop) → BUILD_LIST of integers, emitted inline
                # We can't know values at compile-time in general, so emit a
                # SYSCALL with a dedicated range syscall ID (20).
                sop = _STANDALONE_OPS['SYSCALL']
                a = 20   # syscall ID 20 = range(start,stop) -> list
                b = argc
                c = 1    # push result
                _pending_syscall_name = None
            elif _pending_syscall_name is not None:
                sid = _SYSCALL_NAME_MAP.get(_pending_syscall_name, 0)
                sop = _STANDALONE_OPS['SYSCALL']
                a = sid
                b = argc
                c = 1
                _pending_syscall_name = None
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
            if name not in func_const_slots:
                raise ValueError(f'PUSH_FUNC: unknown function {name!r}')
            sop = _STANDALONE_OPS['PUSH_CONST']
            a = func_const_slots[name]

        elif op == Op.CALL_VAL:
            sop = _STANDALONE_OPS['CALL_VAL']
            a = int(ins[1])

        elif op == Op.STOP:
            sop = _STANDALONE_OPS['HALT']

        elif op == Op.ARG:
            # Consumed during func_table reconstruction; no code emitted.
            spans.append(_span_tuple(spans_src, pc, compiled))
            continue

        elif op in (Op.WAIT, Op.ASK, Op.SEED, Op.GLOBAL_SEED, Op.RANDFLOAT,
                    Op.RANDOM, Op.SHOW_PREC, Op.SAVE, Op.SAVE_VAL, Op.LOAD_F,
                    Op.LIST_HAS, Op.LIST_PUT, Op.SLICE, Op.TRY, Op.ENDTRY):
            # Unsupported in standalone — halt with sentinel code
            sop = _STANDALONE_OPS['HALT']
            a = 0xFF

        else:
            raise ValueError(f'Unsupported opcode for standalone image: {ins!r}')

        code.append((sop, a, b, c))
        spans.append(_span_tuple(spans_src, pc, compiled))

    if not code or code[-1][0] != _STANDALONE_OPS['HALT']:
        code.append((_STANDALONE_OPS['HALT'], 0, 0, 0))
        spans.append((0, 1, 0, 1))

    # ── pass 2a: remap function body addresses src_pc → img_pc ─────────────
    # func_table addresses are SOURCE bytecode PCs (point to first ARG or first
    # real instruction).  After ARG-skip lowering the image PCs differ.
    for fname, fmeta in func_table.items():
        src_addr = int(fmeta.get('address', 0))
        img_addr = _src_to_img.get(src_addr, src_addr)
        fmeta['address'] = img_addr
    # Rebuild functions list and func_const_slots with corrected addresses
    functions.clear()
    for name, meta in func_table.items():
        _scanned_lc = len(_func_locals.get(name, {}))
        _lc = _scanned_lc if _scanned_lc > 0 else int(meta.get('param_count', 0))
        functions.append(FunctionEntry(
            name=name,
            address=int(meta['address']),
            arity=int(meta.get('param_count', 0)),
            local_count=_lc,
            flags=int(meta.get('flags', 0)),
        ))
        # Update the func constant in const_pool with corrected address
        slot = func_const_slots.get(name)
        if slot is not None:
            const_pool[slot] = {
                'tag': 'func',
                'value': {
                    'address': int(meta['address']),
                    'arity': int(meta.get('param_count', 0)),
                    'local_count': _lc,
                    'flags': int(meta.get('flags', 0)),
                }
            }

    # ── pass 2b: rewrite JUMP/JIF targets from src_pc to img_pc ─────────────
    for img_idx, field in _jump_patches:
        src_target = code[img_idx][1]   # field 'a' is always index 1 in tuple
        img_target = _src_to_img.get(src_target, src_target)
        op_, a_, b_, c_ = code[img_idx]
        code[img_idx] = (op_, img_target, b_, c_)

    seen: set[str] = set()
    unique_modules: list[ModuleEntry] = []
    for mod in modules:
        if mod.name in seen:
            continue
        seen.add(mod.name)
        unique_modules.append(mod)

    events = [EventEntry(name='startup', target=0, flags=1)]
    return StandaloneImage(
        source_name=source_name,
        consts=const_pool,
        code=code,
        spans=spans,
        globals=globals_map,
        functions=functions,
        events=events,
        modules=unique_modules,
        pipeline=compiled.pipeline,
    )

def _span_tuple(span_map: list[dict[str, Any]], pc: int, compiled: CompiledProgram) -> tuple[int, int, int, int]:
    if pc < len(span_map):
        s = span_map[pc] or {}
        return (
            int(s.get('start_line', 0) or 0),
            int(s.get('start_col', 1) or 1),
            int(s.get('end_line', s.get('start_line', 0) or 0) or 0),
            int(s.get('end_col', s.get('start_col', 1) or 1) or 1),
        )
    line = int((compiled.line_map or [0])[pc]) if compiled.line_map and pc < len(compiled.line_map) else 0
    col = int((compiled.col_map or [1])[pc]) if compiled.col_map and pc < len(compiled.col_map) else 1
    return (line, col, line, col)


def compile_source_to_standalone_image(source: str, *, filename: str | None = None, optimize: bool = True) -> StandaloneImage:
    # v2.3.4: try new IR compiler first; fall back to legacy compiler for
    # constructs (if/def) that the IR lowerer doesn't yet handle.
    from .compiler.legacy import Compiler as _LegacyCompiler
    from .error_core import MellowLangRuntimeError

    # v2.3.4: standalone always uses legacy compiler — the new IR optimizer has
    # known issues (variable-access after BUILD_LIST/BUILD_MAP) that cause incorrect
    # code generation in the standalone lowering pass.  The legacy compiler is fully
    # tested and produces correct bytecode for all supported constructs.
    legacy_bytecode = _LegacyCompiler().compile(source.splitlines())
    compiled = CompiledProgram(
        bytecode=legacy_bytecode,
        func_table=None,
        event_table=None,
        filename=filename,
        source_lines=source.splitlines(),
        pipeline="legacy",
    )

    return lower_compiled_to_standalone_image(compiled, source_name=filename or '<memory>')


def compile_file_to_standalone_image(input_path: str, *, output_path: str | None = None, optimize: bool = True) -> dict[str, Any]:
    path = Path(input_path)
    source = path.read_text(encoding='utf-8')
    image = compile_source_to_standalone_image(source, filename=str(path), optimize=optimize)
    out_path = Path(output_path) if output_path else path.with_suffix('.mvi')
    out_path.write_bytes(image.to_bytes())
    return {
        'ok': True,
        'input': str(path),
        'output': str(out_path),
        'format': 'mlvi-binary-v2',
        'code_len': len(image.code),
        'const_len': len(image.consts),
        'globals': image.globals,
        'functions': [fn.__dict__ for fn in image.functions],
        'events': [ev.__dict__ for ev in image.events],
        'modules': [mod.__dict__ for mod in image.modules],
        'pipeline': image.pipeline,
    }


def run_standalone_image(image_path: str, *, binary_path: str | None = None) -> dict[str, Any]:
    binary = Path(binary_path) if binary_path else _standalone_binary()
    if not binary.exists():
        return {'ok': False, 'error': 'standalone_binary_missing', 'binary_path': str(binary)}
    proc = subprocess.run([str(binary), str(image_path)], capture_output=True, text=True, check=False)
    return {
        'ok': proc.returncode == 0,
        'returncode': proc.returncode,
        'stdout': proc.stdout,
        'stderr': proc.stderr,
        'binary_path': str(binary),
        'image_path': str(image_path),
    }
