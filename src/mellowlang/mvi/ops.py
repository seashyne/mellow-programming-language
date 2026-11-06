"""The number tables a lowering reads: standalone opcode ids, comparison codes, and the syscall
   names the C runtime answers."""

from __future__ import annotations


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
    'std.io.println': 1, 'println': 1,
    'std.len':     2, 'len':     2,
    'std.clock':   3, 'clock_ms': 3,
    'std.getenv':  4, 'std.sys.getenv': 4, 'getenv':  4,
    'std.str':     5, 'std.type.to_str': 5, 'str':     5,
    'std.type':    6, 'std.type.of': 6, 'type':    6,
    'std.abs':     7, 'std.math.abs': 7, 'abs':     7,
    'std.floor':   8, 'std.math.floor': 8, 'floor':   8,
    'std.ceil':    9, 'std.math.ceil': 9, 'ceil':    9,
    'std.sqrt':   10, 'std.math.sqrt': 10, 'sqrt':   10,
    'std.min':    11, 'std.math.min': 11, 'min':    11,
    'std.max':    12, 'std.math.max': 12, 'max':    12,
    'std.io.write': 14, 'write': 14,
    'std.io.input': 15, 'input': 15, 'readline': 15, 'read_line': 15, 'ask': 15,
    'std.sys.args': 16, 'args': 16, 'argv': 16,
    'std.sys.cwd': 17, 'cwd': 17,
    'std.sys.sleep_ms': 18, 'sleep_ms': 18,
    'std.sys.exit': 19, 'exit': 19,
    # range() builtin
    'range':  20,
    'std.range': 20,
    'std.gc.collect': 21, 'gc_collect': 21,
    'std.gc.stats': 22, 'gc_stats': 22,
    'std.thread.spawn': 23, 'spawn': 23,
    'std.thread.yield': 24, 'yield': 24,
    'std.chan.channel': 25, 'channel': 25,
    'std.chan.send': 26, 'send': 26,
    'std.chan.recv': 27, 'recv': 27,
}
