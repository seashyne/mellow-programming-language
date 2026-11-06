"""The .mvi file itself: the magic and version header, the four entry record types, and the
   byte writer that turns an image into a binary."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any


MAGIC = b"MLVI0200"


VERSION = 2


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
