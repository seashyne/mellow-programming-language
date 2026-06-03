from __future__ import annotations

import contextlib
import html
import io
import json
import os
import re
import secrets
import tempfile
import time
from dataclasses import asdict, is_dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..compiler import Compiler
from ..vm import MellowVM, RunConfig
from ..vm.cbridge import c_vm_capabilities
from ..vm.legacy import MellowLangVM


ASSET_DIR = Path(__file__).resolve().parent / 'assets'
SESSION_STORE: dict[str, dict[str, Any]] = {}
SESSION_ORDER: list[str] = []
SESSION_LIMIT = 128
DEBUG_SESSIONS: dict[str, dict[str, Any]] = {}
DEBUG_SESSION_LIMIT = 32
TRACE_RE = re.compile(r"^\[trace\]\s+(?P<file>.*?):(?P<line>\d+):(?P<col>\d+)\s+\|\s*(?P<source>.*?)(?:\s+#\s+(?P<watch>.*))?$", re.MULTILINE)
KEYWORDS = {
    'workflow', 'trigger', 'step', 'parallel', 'policy', 'retry', 'timeout', 'switch',
    'case', 'default', 'run', 'use', 'input', 'output', 'state', 'emit', 'cron', 'webhook',
}


def _store_root() -> Path:
    root = Path.cwd() / '.mellow' / 'playground'
    (root / 'sessions').mkdir(parents=True, exist_ok=True)
    (root / 'recordings').mkdir(parents=True, exist_ok=True)
    return root


def _session_path(session_id: str) -> Path:
    return _store_root() / 'sessions' / f'{session_id}.json'


def _recording_manifest_path(recording_id: str) -> Path:
    return _store_root() / 'recordings' / f'{recording_id}.json'


def _recording_replay_path(recording_id: str) -> Path:
    return _store_root() / 'recordings' / f'{recording_id}.jsonl'


def _save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def _to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return {k: _to_plain(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    return value


def _escape_html(text: str) -> str:
    return html.escape(text, quote=False)


def _highlight_source_html(source: str) -> str:
    out_lines: list[str] = []
    for raw in source.splitlines() or ['']:
        line = _escape_html(raw)
        line = re.sub(r'(&quot;.*?&quot;|".*?"|\'.*?\')', r'<span class="tok-string">\1</span>', line)
        line = re.sub(r'(#[^\n]*)', r'<span class="tok-comment">\1</span>', line)
        line = re.sub(r'\b(\d+(?:\.\d+)?)\b', r'<span class="tok-number">\1</span>', line)
        line = re.sub(
            r'\b(' + '|'.join(sorted(KEYWORDS, key=len, reverse=True)) + r')\b',
            r'<span class="tok-keyword">\1</span>',
            line,
        )
        out_lines.append(line or '&nbsp;')
    return '<br>'.join(out_lines)


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


def _render_dump(title: str, payload: Any, fmt: str) -> str:
    if fmt == 'json':
        return json.dumps(_to_plain(payload), ensure_ascii=False, indent=2)
    if title.startswith('AST'):
        return json.dumps(_to_plain(payload), ensure_ascii=False, indent=2)
    if hasattr(payload, 'blocks'):
        return _format_cfg_text(payload)
    if hasattr(payload, 'instructions'):
        return _format_ir_text(payload)
    return json.dumps(_to_plain(payload), ensure_ascii=False, indent=2)


def _collect_examples() -> list[dict[str, str]]:
    candidates: list[tuple[str, str]] = [
        ('hello', 'examples/hello.mellow'),
        ('modern_quickstart', 'examples/modern_quickstart.mellow'),
        ('loops', 'examples/loops.mellow'),
        ('try_catch', 'examples/try_catch.mellow'),
    ]
    root = Path(__file__).resolve().parents[3]
    out: list[dict[str, str]] = []
    for name, rel in candidates:
        p = root / rel
        if p.exists():
            out.append({'name': name, 'path': rel, 'source': p.read_text(encoding='utf-8')})
    if not out:
        out.append({'name': 'hello', 'path': '<built-in>', 'source': 'print("Hello from Mellow Playground!")\n'})
    return out


def _parse_watch_pairs(text: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not text:
        return out
    for part in text.split(','):
        if '=' not in part:
            continue
        key, value = part.split('=', 1)
        out[key.strip()] = value.strip()
    return out


def _extract_trace_events(stdout: str) -> tuple[str, list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    cleaned = stdout
    for idx, match in enumerate(TRACE_RE.finditer(stdout)):
        events.append({
            'index': idx,
            'file': match.group('file') or '<script>',
            'line': int(match.group('line')),
            'col': int(match.group('col')),
            'source': (match.group('source') or '').rstrip(),
            'watch_raw': match.group('watch') or '',
            'watch': _parse_watch_pairs(match.group('watch')),
        })
    cleaned = TRACE_RE.sub('', cleaned).strip('\n')
    return cleaned, events


def _first_line(block: Any) -> int:
    for ins in getattr(block, 'instructions', []) or []:
        line = int(getattr(ins, 'line', 0) or 0)
        if line > 0:
            return line
    return 0


def _source_outline_graph(source: str, cfg: Any = None) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    workflow_name = 'script'
    last_node_id: str | None = None
    node_index = 0
    trigger_nodes: list[str] = []

    for lineno, raw in enumerate(source.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        m = re.match(r'workflow\s+([A-Za-z_][\w\-]*)', line)
        if m:
            workflow_name = m.group(1)
            node_id = f'n{node_index}'; node_index += 1
            nodes.append({'id': node_id, 'label': workflow_name, 'kind': 'workflow', 'line': lineno})
            last_node_id = node_id
            continue
        m = re.match(r'trigger\s+(.+)$', line)
        if m:
            node_id = f'n{node_index}'; node_index += 1
            nodes.append({'id': node_id, 'label': m.group(1), 'kind': 'trigger', 'line': lineno})
            trigger_nodes.append(node_id)
            continue
        m = re.match(r'step\s+([A-Za-z_][\w\-]*)', line)
        if m:
            node_id = f'n{node_index}'; node_index += 1
            nodes.append({'id': node_id, 'label': m.group(1), 'kind': 'step', 'line': lineno})
            if last_node_id:
                edges.append({'from': last_node_id, 'to': node_id})
            last_node_id = node_id
            continue
        if line.startswith('parallel'):
            node_id = f'n{node_index}'; node_index += 1
            nodes.append({'id': node_id, 'label': 'parallel', 'kind': 'parallel', 'line': lineno})
            if last_node_id:
                edges.append({'from': last_node_id, 'to': node_id})
            last_node_id = node_id
            continue
        if line.startswith('policy'):
            node_id = f'n{node_index}'; node_index += 1
            nodes.append({'id': node_id, 'label': 'policy', 'kind': 'policy', 'line': lineno})
            if last_node_id:
                edges.append({'from': last_node_id, 'to': node_id})
            last_node_id = node_id
            continue

    for trig in trigger_nodes:
        step_targets = [n['id'] for n in nodes if n.get('kind') in ('step', 'parallel')]
        if step_targets:
            edges.append({'from': trig, 'to': step_targets[0]})

    if cfg is not None and getattr(cfg, 'blocks', None):
        cfg_nodes = []
        cfg_edges = []
        for block in getattr(cfg, 'blocks', []) or []:
            label = getattr(block, 'label', '?')
            cfg_nodes.append({
                'id': f'cfg:{label}',
                'label': label,
                'kind': 'block',
                'line': _first_line(block),
            })
            for succ in getattr(block, 'successors', []) or []:
                cfg_edges.append({'from': f'cfg:{label}', 'to': f'cfg:{succ}'})
        if cfg_nodes:
            return {'name': workflow_name, 'nodes': cfg_nodes, 'edges': cfg_edges, 'mode': 'cfg'}

    return {'name': workflow_name, 'nodes': nodes, 'edges': edges, 'mode': 'source'}


def _diff_watch(prev: dict[str, str], cur: dict[str, str]) -> list[dict[str, Any]]:
    keys = sorted(set(prev) | set(cur))
    out = []
    for key in keys:
        a = prev.get(key)
        b = cur.get(key)
        if a != b:
            out.append({'name': key, 'before': a, 'after': b})
    return out


def _attach_state_diffs(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prev: dict[str, str] = {}
    for event in events:
        cur = dict(event.get('watch') or {})
        event['state_diff'] = _diff_watch(prev, cur)
        prev = cur
    return events


def _timeline(events: list[dict[str, Any]], compile_ms: float, run_ms: float) -> list[dict[str, Any]]:
    total = max(len(events), 1)
    trace_budget = max(run_ms, 0.001)
    items = [
        {'kind': 'compile', 'label': 'Compile', 'ms': round(compile_ms, 3)},
        {'kind': 'run', 'label': 'Run', 'ms': round(run_ms, 3)},
    ]
    for event in events:
        share = trace_budget / total
        items.append({
            'kind': 'step',
            'label': f"L{event['line']} • {event['source'][:64]}",
            'ms': round(share, 3),
            'line': event['line'],
            'index': event['index'],
            'state_diff_count': len(event.get('state_diff') or []),
        })
    return items


def _store_session(payload: dict[str, Any]) -> str:
    session_id = secrets.token_urlsafe(6)
    SESSION_STORE[session_id] = payload
    SESSION_ORDER.append(session_id)
    while len(SESSION_ORDER) > SESSION_LIMIT:
        old = SESSION_ORDER.pop(0)
        SESSION_STORE.pop(old, None)
    _save_json(_session_path(session_id), payload)
    return session_id


def _load_session(session_id: str) -> dict[str, Any] | None:
    payload = SESSION_STORE.get(session_id)
    if payload is not None:
        return payload
    path = _session_path(session_id)
    if path.exists():
        payload = _load_json(path)
        SESSION_STORE[session_id] = payload
        return payload
    return None


def _record_manifest(recording_id: str, manifest: dict[str, Any]) -> None:
    _save_json(_recording_manifest_path(recording_id), manifest)


def _load_recording(recording_id: str) -> dict[str, Any] | None:
    path = _recording_manifest_path(recording_id)
    if path.exists():
        return _load_json(path)
    return None



def _debug_store_root() -> Path:
    root = _store_root() / 'debug'
    root.mkdir(parents=True, exist_ok=True)
    return root


def _summarize_debugger_vm(vm: MellowLangVM, *, session_id: str, program: Any, source: str) -> dict[str, Any]:
    stop = _to_plain(getattr(vm, '_dbg_last_stop', None))
    return {
        'ok': True,
        'session_id': session_id,
        'paused': bool(getattr(vm, '_dbg_paused', False)),
        'finished': bool(getattr(vm, '_halted', False) or vm.pc >= len(vm.bytecode)),
        'result': repr(getattr(vm, '_last_result', None)),
        'pipeline': getattr(program, 'pipeline', 'legacy'),
        'bytecode_count': len(getattr(program, 'bytecode', []) or []),
        'stop': stop,
        'history_tail': _to_plain(getattr(vm, '_dbg_history', [])[-24:]),
        'editor': {
            'line_count': max(len(source.splitlines()), 1),
            'highlighted_html': _highlight_source_html(source),
        },
        'engine': getattr(vm, '_engine_name', getattr(vm, 'engine_name', 'py')),
        'engine_detail': getattr(vm, '_engine_detail', 'python-debugger-runtime'),
        'debug_capabilities': {
            'pause_resume': True,
            'conditional_breakpoints': True,
            'watch_expressions': True,
            'typed_frames': True,
            'engine_contract': 'python-debugger-runtime',
            'native_c_capabilities': c_vm_capabilities(),
        },
    }


def start_debug_session(source: str, *, optimize: bool = True, watch: str | None = None, break_lines: str | None = None, break_instrs: str | None = None, break_opcodes: str | None = None, break_when: str | None = None, watch_exprs: str | None = None) -> dict[str, Any]:
    compiler = Compiler()
    program = compiler.compile(source, filename='<playground>', optimize=optimize)
    session_id = secrets.token_urlsafe(6)
    td = tempfile.TemporaryDirectory(prefix='mellow-debug-')
    vm = MellowLangVM(
        list(program.bytecode),
        dict(getattr(program, 'func_table', None) or {}),
        dict(getattr(program, 'event_table', None) or {}),
        config={
            'allow_storage': True,
            'allow_save': True,
            'storage_dir': td.name,
            'project_mode': True,
            'project_root': td.name,
            'sandbox_root': 'sandbox',
            'max_steps': 100_000,
            'max_ms': 5_000,
            'debug_pause_on_start': True,
            'debug_watch': watch or '',
            'debug_break_lines': break_lines or '',
            'debug_break_instrs': break_instrs or '',
            'debug_break_opcodes': break_opcodes or '',
            'debug_break_when': break_when or '',
            'debug_watch_exprs': watch_exprs or '',
        },
        filename=program.filename,
        source_lines=program.source_lines,
        line_map=getattr(program, 'line_map', None),
        col_map=getattr(program, 'col_map', None),
        end_line_map=getattr(program, 'end_line_map', None),
        end_col_map=getattr(program, 'end_col_map', None),
        span_map=getattr(program, 'span_map', None),
    )
    vm._engine_name = 'py'
    vm._engine_detail = 'python-debugger-runtime'
    vm.run()
    DEBUG_SESSIONS[session_id] = {
        'vm': vm,
        'program': program,
        'source': source,
        'tempdir': td,
        'created_at': int(time.time()),
    }
    while len(DEBUG_SESSIONS) > DEBUG_SESSION_LIMIT:
        old_id = next(iter(DEBUG_SESSIONS.keys()))
        old = DEBUG_SESSIONS.pop(old_id, None)
        if old and old.get('tempdir'):
            old['tempdir'].cleanup()
    return _summarize_debugger_vm(vm, session_id=session_id, program=program, source=source)


def debugger_command(session_id: str, command: str) -> dict[str, Any]:
    entry = DEBUG_SESSIONS.get(session_id)
    if not entry:
        raise FileNotFoundError('Debugger session not found')
    vm: MellowLangVM = entry['vm']
    program = entry['program']
    source = entry['source']
    if command == 'stop':
        vm._halted = True
        vm._dbg_paused = False
        return _summarize_debugger_vm(vm, session_id=session_id, program=program, source=source)
    mode = {
        'continue': 'continue',
        'step_into': 'step_into',
        'step_over': 'step_over',
        'step_out': 'step_out',
        'pause': 'continue',
    }.get(command, command)
    vm.debug_resume(mode)
    vm.run()
    return _summarize_debugger_vm(vm, session_id=session_id, program=program, source=source)


def get_debug_session(session_id: str) -> dict[str, Any]:
    entry = DEBUG_SESSIONS.get(session_id)
    if not entry:
        raise FileNotFoundError('Debugger session not found')
    return _summarize_debugger_vm(entry['vm'], session_id=session_id, program=entry['program'], source=entry['source'])


def run_playground_session(
    source: str,
    *,
    optimize: bool = True,
    dump_format: str = 'text',
    include_dumps: bool = True,
    engine: str = 'auto',
    allow_net: bool = False,
    trace: bool = True,
    watch: str | None = None,
    break_lines: str | None = None,
    record_execution: bool = True,
    replay_recording_id: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    compiler = Compiler()
    program = compiler.compile(source, filename='<playground>', optimize=optimize)
    compiled_ms = (time.perf_counter() - started) * 1000.0

    run_started = time.perf_counter()
    vm = MellowVM()
    recording_id = replay_recording_id or secrets.token_urlsafe(6)
    replay_log = _recording_replay_path(recording_id)
    if break_lines:
        engine = 'py'
    if replay_recording_id:
        engine = 'py'
    with tempfile.TemporaryDirectory(prefix='mellow-playground-') as td:
        base_config = dict(
            engine=engine or 'auto',
            allow_net=bool(allow_net),
            allow_storage=True,
            allow_save=True,
            storage_dir=td,
            project_mode=True,
            project_root=td,
            sandbox_root='sandbox',
            max_steps=100_000,
            max_ms=5_000,
            break_lines=break_lines,
        )
        stdout = io.StringIO()
        run_cfg = RunConfig(
            engine=base_config['engine'],
            allow_net=base_config['allow_net'],
            allow_storage=True,
            allow_save=True,
            storage_dir=td,
            project_mode=True,
            project_root=td,
            sandbox_root='sandbox',
            max_steps=100_000,
            max_ms=5_000,
            break_lines=break_lines,
            record_path=str(replay_log) if (record_execution and not replay_recording_id) else None,
            replay_path=str(replay_log) if replay_recording_id else None,
        )
        with contextlib.redirect_stdout(stdout):
            result = vm.run(program, config=run_cfg)

        trace_stdout = io.StringIO()
        if trace:
            trace_cfg = RunConfig(
                engine='py' if (break_lines or replay_recording_id) else (engine or 'auto'),
                allow_net=bool(allow_net),
                allow_storage=True,
                allow_save=True,
                storage_dir=td,
                project_mode=True,
                project_root=td,
                sandbox_root='sandbox',
                max_steps=100_000,
                max_ms=5_000,
                trace=True,
                watch=watch,
                break_lines=break_lines,
                replay_path=str(replay_log) if replay_recording_id else None,
            )
            with contextlib.redirect_stdout(trace_stdout):
                _ = vm.run(program, config=trace_cfg)
    ran_ms = (time.perf_counter() - run_started) * 1000.0
    raw_stdout = stdout.getvalue()
    trace_raw = trace_stdout.getvalue() if trace else ''
    clean_stdout, _ = _extract_trace_events(raw_stdout)
    _, trace_events = _extract_trace_events(trace_raw)
    trace_events = _attach_state_diffs(trace_events)
    graph = _source_outline_graph(source, getattr(program, 'optimized_cfg', None) or getattr(program, 'cfg', None))
    debug_stop = _to_plain(getattr(vm, 'last_debug_stop', None))
    payload: dict[str, Any] = {
        'ok': True,
        'pipeline': getattr(program, 'pipeline', 'legacy'),
        'stdout': clean_stdout,
        'raw_stdout': raw_stdout,
        'result': repr(result),
        'compile_ms': round(compiled_ms, 3),
        'run_ms': round(ran_ms, 3),
        'bytecode_count': len(getattr(program, 'bytecode', []) or []),
        'optimization': _to_plain(getattr(program, 'optimization', None)),
        'engine': getattr(vm, 'last_engine', engine or 'auto'),
        'engine_detail': getattr(vm, 'last_engine_detail', ''),
        'native_c_capabilities': _to_plain(getattr(vm, 'last_debug_capabilities', {})),
        'metadata': {
            'func_count': len(getattr(program, 'func_table', {}) or {}),
            'event_count': len(getattr(program, 'event_table', {}) or {}),
        },
        'timeline': _timeline(trace_events, compiled_ms, ran_ms),
        'trace_events': trace_events,
        'state_diffs': [e.get('state_diff') or [] for e in trace_events],
        'graph': graph,
        'editor': {
            'line_count': max(len(source.splitlines()), 1),
            'highlighted_html': _highlight_source_html(source),
        },
        'engine': getattr(vm, '_engine_name', getattr(vm, 'engine_name', 'py')),
        'engine_detail': getattr(vm, '_engine_detail', 'python-debugger-runtime'),
        'debug_capabilities': {
            'pause_resume': True,
            'conditional_breakpoints': True,
            'watch_expressions': True,
            'typed_frames': True,
            'engine_contract': 'python-debugger-runtime',
            'native_c_capabilities': c_vm_capabilities(),
        },
        'debugger': {
            'break_lines': break_lines or '',
            'stopped': bool(debug_stop),
            'stop': debug_stop,
            'recording_id': recording_id if record_execution or replay_recording_id else None,
            'replayable': replay_log.exists(),
            'replay_mode': bool(replay_recording_id),
        },
    }
    if include_dumps:
        payload['dumps'] = {
            'ast': _render_dump('AST', getattr(program, 'ast', None), dump_format) if getattr(program, 'ast', None) is not None else '',
            'ir': _render_dump('IR', getattr(program, 'ir', None), dump_format) if getattr(program, 'ir', None) is not None else '',
            'optimized_ir': _render_dump('IR Optimized', getattr(program, 'optimized_ir', None), dump_format) if getattr(program, 'optimized_ir', None) is not None else '',
            'cfg': _render_dump('CFG', getattr(program, 'cfg', None), dump_format) if getattr(program, 'cfg', None) is not None else '',
            'optimized_cfg': _render_dump('CFG Optimized', getattr(program, 'optimized_cfg', None), dump_format) if getattr(program, 'optimized_cfg', None) is not None else '',
            'ssa': _render_dump('SSA', getattr(program, 'ssa_program', None), dump_format) if getattr(program, 'ssa_program', None) is not None else '',
            'optimized_ssa': _render_dump('SSA Optimized', getattr(program, 'optimized_ssa_program', None), dump_format) if getattr(program, 'optimized_ssa_program', None) is not None else '',
        }
    if record_execution and not replay_recording_id:
        manifest = {
            'recording_id': recording_id,
            'created_at': int(time.time()),
            'source': source,
            'watch': watch or '',
            'break_lines': break_lines or '',
            'optimize': bool(optimize),
            'engine': engine or 'auto',
            'payload': payload,
            'replay_log_path': str(replay_log),
        }
        _record_manifest(recording_id, manifest)
    return payload


def replay_recording(recording_id: str) -> dict[str, Any]:
    manifest = _load_recording(recording_id)
    if not manifest:
        raise FileNotFoundError('Recording not found')
    payload = run_playground_session(
        str(manifest.get('source', '')),
        optimize=bool(manifest.get('optimize', True)),
        dump_format='text',
        include_dumps=True,
        engine='py',
        allow_net=False,
        trace=True,
        watch=str(manifest.get('watch', '') or '') or None,
        break_lines=str(manifest.get('break_lines', '') or '') or None,
        record_execution=False,
        replay_recording_id=recording_id,
    )
    payload['debugger']['replayed_from_recording'] = recording_id
    return payload


def build_static_playground(out_dir: str | os.PathLike[str]) -> Path:
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    for asset in ASSET_DIR.iterdir():
        if asset.is_file():
            (target / asset.name).write_text(asset.read_text(encoding='utf-8'), encoding='utf-8')
    return target


class _PlaygroundApiHandler(BaseHTTPRequestHandler):
    static_dir: Path

    def _send_json(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get('Content-Length', '0') or '0')
        raw = self.rfile.read(length) if length > 0 else b'{}'
        return json.loads(raw.decode('utf-8') or '{}')

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ('/api/health', '/api/healthz'):
            self._send_json(200, {'ok': True, 'service': 'mellow-playground-time-travel'})
            return
        if path == '/api/examples':
            self._send_json(200, {'ok': True, 'examples': _collect_examples()})
            return
        if path.startswith('/api/session/'):
            session_id = path.rsplit('/', 1)[-1]
            payload = _load_session(session_id)
            if not payload:
                self._send_json(404, {'ok': False, 'error': 'Session not found'})
                return
            self._send_json(200, {'ok': True, 'session': payload})
            return
        if path.startswith('/api/replay/'):
            recording_id = path.rsplit('/', 1)[-1]
            try:
                self._send_json(200, replay_recording(recording_id))
            except Exception as e:
                self._send_json(404, {'ok': False, 'error': str(e)})
            return
        if path.startswith('/api/debug/session/'):
            session_id = path.rsplit('/', 1)[-1]
            try:
                self._send_json(200, get_debug_session(session_id))
            except Exception as e:
                self._send_json(404, {'ok': False, 'error': str(e)})
            return
        if path in ('/', '/index.html') or path.startswith('/s/'):
            return self._serve_asset('index.html', 'text/html; charset=utf-8')
        if path == '/styles.css':
            return self._serve_asset('styles.css', 'text/css; charset=utf-8')
        if path == '/app.js':
            return self._serve_asset('app.js', 'application/javascript; charset=utf-8')
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        if self.path not in ('/api/run', '/api/compile', '/api/share', '/api/replay', '/api/debug/start', '/api/debug/command'):
            self.send_response(404)
            self.end_headers()
            return
        try:
            body = self._read_json()
            if self.path == '/api/share':
                source = str(body.get('source', ''))
                result = body.get('result') or {}
                session_payload = {
                    'source': source,
                    'result': result,
                    'created_at': int(time.time()),
                }
                session_id = _store_session(session_payload)
                proto = 'https' if self.headers.get('X-Forwarded-Proto', '').lower() == 'https' else 'http'
                host = self.headers.get('Host', '127.0.0.1')
                self._send_json(200, {'ok': True, 'session_id': session_id, 'share_url': f'{proto}://{host}/s/{session_id}', 'persisted': True})
                return
            if self.path == '/api/replay':
                recording_id = str(body.get('recording_id', '')).strip()
                self._send_json(200, replay_recording(recording_id))
                return
            if self.path == '/api/debug/start':
                source = str(body.get('source', ''))
                self._send_json(200, start_debug_session(
                    source,
                    optimize=bool(body.get('optimize', True)),
                    watch=str(body.get('watch', '') or '') or None,
                    break_lines=str(body.get('break_lines', '') or '') or None,
                    break_instrs=str(body.get('break_instrs', '') or '') or None,
                    break_opcodes=str(body.get('break_opcodes', '') or '') or None,
                    break_when=str(body.get('break_when', '') or '') or None,
                    watch_exprs=str(body.get('watch_exprs', '') or '') or None,
                ))
                return
            if self.path == '/api/debug/command':
                session_id = str(body.get('session_id', '')).strip()
                command = str(body.get('command', 'continue')).strip()
                self._send_json(200, debugger_command(session_id, command))
                return
            source = str(body.get('source', ''))
            if not source.strip():
                self._send_json(400, {'ok': False, 'error': 'Source is empty.'})
                return
            payload = run_playground_session(
                source,
                optimize=bool(body.get('optimize', True)),
                dump_format='json' if str(body.get('dump_format', 'text')) == 'json' else 'text',
                include_dumps=True,
                engine=str(body.get('engine', 'auto') or 'auto'),
                allow_net=bool(body.get('allow_net', False)),
                trace=bool(body.get('trace', True)),
                watch=str(body.get('watch', '') or '') or None,
                break_lines=str(body.get('break_lines', '') or '') or None,
                record_execution=bool(body.get('record_execution', True)),
            )
            if self.path == '/api/compile':
                payload['stdout'] = ''
                payload['raw_stdout'] = ''
                payload['result'] = 'Compile OK'
                payload['run_ms'] = 0.0
                payload['timeline'] = [payload['timeline'][0]] if payload.get('timeline') else []
                payload['trace_events'] = []
                payload['state_diffs'] = []
            self._send_json(200, payload)
        except Exception as e:
            self._send_json(500, {'ok': False, 'error': str(e)})

    def _serve_asset(self, name: str, content_type: str) -> None:
        asset = self.static_dir / name
        if not asset.exists():
            self.send_response(404)
            self.end_headers()
            return
        body = asset.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve_playground(host: str = '127.0.0.1', port: int = 8765) -> ThreadingHTTPServer:
    handler = type('PlaygroundHandler', (_PlaygroundApiHandler,), {'static_dir': ASSET_DIR})
    server = ThreadingHTTPServer((host, port), handler)
    return server
