from __future__ import annotations

import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from ...compiler import Compiler
from ..common import _read_text

def _cmd_pack(entry: str, out_path: str, include: list[str], name: str, version: str) -> int:
    """Create a portable bundle for game/mod distribution."""
    import json, os, zipfile, time
    entry_p = Path(entry).resolve()
    if not entry_p.exists():
        print(f"error: entry not found: {entry_p}")
        return 2

    root_dir = entry_p.parent
    out_p = Path(out_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    manifest = {
        "name": name,
        "version": version,
        "entry": entry_p.name,
        "created_utc": int(time.time()),
    }

    def _add(z: zipfile.ZipFile, p: Path, arc_prefix: str = ""):
        p = p.resolve()
        if p.is_dir():
            for sub in p.rglob("*"):
                if sub.is_file():
                    rel = sub.relative_to(root_dir)
                    z.write(sub, arcname=str(Path(arc_prefix) / rel))
        else:
            rel = p.relative_to(root_dir) if root_dir in p.parents else p.name
            z.write(p, arcname=str(Path(arc_prefix) / rel))

    with zipfile.ZipFile(out_p, "w", compression=zipfile.ZIP_DEFLATED) as z:
        # entry script
        _add(z, entry_p)
        # common folders
        for folder in ("libs", "assets"):
            fp = root_dir / folder
            if fp.exists():
                _add(z, fp)
        # extras
        for ex in include or []:
            ep = (root_dir / ex).resolve() if not Path(ex).is_absolute() else Path(ex).resolve()
            if ep.exists():
                _add(z, ep)
        # manifest
        z.writestr("mellow.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    print(f"[OK] packaged: {out_p}")
    return 0

def _to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return {k: _to_plain(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    return value


def _format_ir_text(program: Any) -> str:
    lines: list[str] = []
    instructions = getattr(program, 'instructions', []) or []
    for idx, ins in enumerate(instructions):
        args = ', '.join(repr(a) for a in getattr(ins, 'args', ()) or ())
        loc = f" @ {getattr(ins, 'line', 0)}:{getattr(ins, 'col', 1)}"
        lines.append(f"{idx:04d}  {getattr(ins, 'op', '?')}" + (f" {args}" if args else '') + loc)
    funcs = getattr(program, 'functions', {}) or {}
    if funcs:
        lines.append('')
        lines.append('[functions]')
        for name, meta in funcs.items():
            lines.append(f"- {name}: entry={meta.entry_label} params={meta.params} kind={meta.kind}")
    events = getattr(program, 'events', {}) or {}
    if events:
        lines.append('')
        lines.append('[events]')
        for name, meta in events.items():
            lines.append(f"- {name}: entry={meta.entry_label} params={meta.params} kind={meta.kind}")
    return '\n'.join(lines)


def _format_cfg_text(cfg: Any) -> str:
    lines: list[str] = []
    lines.append(f"entry: {getattr(cfg, 'entry_label', 'entry')}")
    for block in getattr(cfg, 'blocks', []) or []:
        lines.append('')
        lines.append(f"[{getattr(block, 'label', '?')}] id={getattr(block, 'id', '?')} span={getattr(block, 'start', '?')}..{getattr(block, 'end', '?')}")
        preds = ', '.join(getattr(block, 'predecessors', []) or []) or '-'
        succs = ', '.join(getattr(block, 'successors', []) or []) or '-'
        lines.append(f"  preds: {preds}")
        lines.append(f"  succs: {succs}")
        for idx, ins in enumerate(getattr(block, 'instructions', []) or []):
            args = ', '.join(repr(a) for a in getattr(ins, 'args', ()) or ())
            loc = f" @ {getattr(ins, 'line', 0)}:{getattr(ins, 'col', 1)}"
            lines.append(f"    {idx:02d}  {getattr(ins, 'op', '?')}" + (f" {args}" if args else '') + loc)
    return '\n'.join(lines)


def _emit_dump(title: str, payload: Any, fmt: str) -> None:
    print(f"=== {title} ===")
    if fmt == 'json':
        print(json.dumps(_to_plain(payload), ensure_ascii=False, indent=2))
    else:
        if title.startswith('AST'):
            print(json.dumps(_to_plain(payload), ensure_ascii=False, indent=2))
        elif hasattr(payload, 'blocks'):
            print(_format_cfg_text(payload))
        elif hasattr(payload, 'instructions'):
            print(_format_ir_text(payload))
        else:
            print(json.dumps(_to_plain(payload), ensure_ascii=False, indent=2))
    print()


def _cmd_compile(file: str, target: str, out_path: str | None, *, dump_ast: bool = False, dump_ir: bool = False, dump_ir_optimized: bool = False, dump_cfg: bool = False, dump_cfg_optimized: bool = False, dump_dom: bool = False, dump_dom_optimized: bool = False, dump_def_use: bool = False, dump_def_use_optimized: bool = False, dump_ssa: bool = False, dump_ssa_optimized: bool = False, dump_format: str = 'text', optimize: bool = True) -> int:
    p = Path(file)
    if not p.exists():
        print(f"error: path not found: {p}")
        return 2
    src = _read_text(p)
    if target == "python":
        from ...fast_compiler import PyTranspiler
        py_src = PyTranspiler().transpile(src.splitlines(), filename=str(p))
        out = Path(out_path) if out_path else p.with_suffix('.generated.py')
        out.write_text(py_src, encoding='utf-8')
        print(f"[OK] compiled to Python: {out}")
        return 0
    prog = Compiler().compile(src, filename=str(p), optimize=optimize)
    out = Path(out_path) if out_path else p.with_suffix('.mellowc.json')
    if dump_ast and getattr(prog, 'ast', None) is not None:
        _emit_dump('AST', prog.ast, dump_format)
    if dump_ir and getattr(prog, 'ir', None) is not None:
        _emit_dump('IR', prog.ir, dump_format)
    if dump_cfg and getattr(prog, 'cfg', None) is not None:
        _emit_dump('CFG', prog.cfg, dump_format)
    if dump_dom and getattr(prog, 'dominator_tree', None) is not None:
        _emit_dump('Dominator Tree', prog.dominator_tree, dump_format)
    if dump_def_use and getattr(prog, 'def_use', None) is not None:
        _emit_dump('Def-Use', prog.def_use, dump_format)
    if dump_ssa and getattr(prog, 'ssa_program', None) is not None:
        _emit_dump('SSA', prog.ssa_program, dump_format)
    if dump_ir_optimized and getattr(prog, 'optimized_ir', None) is not None:
        _emit_dump('IR Optimized', prog.optimized_ir, dump_format)
    if dump_cfg_optimized and getattr(prog, 'optimized_cfg', None) is not None:
        _emit_dump('CFG Optimized', prog.optimized_cfg, dump_format)
    if dump_dom_optimized and getattr(prog, 'optimized_dominator_tree', None) is not None:
        _emit_dump('Dominator Tree Optimized', prog.optimized_dominator_tree, dump_format)
    if dump_def_use_optimized and getattr(prog, 'optimized_def_use', None) is not None:
        _emit_dump('Def-Use Optimized', prog.optimized_def_use, dump_format)
    if dump_ssa_optimized and getattr(prog, 'optimized_ssa_program', None) is not None:
        _emit_dump('SSA Optimized', prog.optimized_ssa_program, dump_format)
    if (dump_ir_optimized or dump_cfg_optimized or dump_ssa_optimized) and getattr(prog, 'optimization', None) is not None:
        _emit_dump('Optimization Summary', prog.optimization, dump_format)

    payload = {
        'filename': prog.filename,
        'pipeline': getattr(prog, 'pipeline', 'bytecode'),
        'bytecode': prog.bytecode,
        'func_table': prog.func_table or {},
        'event_table': prog.event_table or {},
        'cfg': _to_plain(getattr(prog, 'cfg', None)),
        'optimized_cfg': _to_plain(getattr(prog, 'optimized_cfg', None)),
        'optimization': _to_plain(getattr(prog, 'optimization', None)),
        'dominator_tree': _to_plain(getattr(prog, 'dominator_tree', None)),
        'optimized_dominator_tree': _to_plain(getattr(prog, 'optimized_dominator_tree', None)),
        'def_use': _to_plain(getattr(prog, 'def_use', None)),
        'optimized_def_use': _to_plain(getattr(prog, 'optimized_def_use', None)),
        'ssa_program': _to_plain(getattr(prog, 'ssa_program', None)),
        'optimized_ssa_program': _to_plain(getattr(prog, 'optimized_ssa_program', None)),
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"[OK] compiled to bytecode: {out}")
    return 0
