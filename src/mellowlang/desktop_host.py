from __future__ import annotations

import json
import os
import re
import shutil
import sys
import textwrap
from pathlib import Path
from typing import Any, Callable, Dict, List

WINDOW_RE = re.compile(r'win\.window\((.*?)\)', re.DOTALL)
CALL_RE = re.compile(r'win\.(label|button|input|textarea|checkbox|select|spacer|vstack|hstack|grid|menu|menu_item|slider|listbox)\((.*?)\)', re.DOTALL)
STATE_RE = re.compile(r'keep\s+(\w+)\s*=\s*(.+?)(?:\n|$)')


def _split_args(raw: str) -> List[str]:
    parts: List[str] = []
    cur: List[str] = []
    depth = 0
    in_str = False
    quote = ''
    esc = False
    for ch in raw:
        if in_str:
            cur.append(ch)
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == quote:
                in_str = False
            continue
        if ch in ('"', "'"):
            in_str = True
            quote = ch
            cur.append(ch)
            continue
        if ch in '([{':
            depth += 1
            cur.append(ch)
            continue
        if ch in ')]}':
            depth = max(0, depth - 1)
            cur.append(ch)
            continue
        if ch == ',' and depth == 0:
            parts.append(''.join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    if cur:
        parts.append(''.join(cur).strip())
    return [p for p in parts if p]


def _parse_value(token: str) -> Any:
    token = token.strip()
    if not token:
        return None
    if token[0] in ('"', "'") and token[-1] == token[0]:
        return token[1:-1]
    low = token.lower()
    if low == 'true':
        return True
    if low == 'false':
        return False
    if re.fullmatch(r'-?\d+', token):
        return int(token)
    if re.fullmatch(r'-?\d+\.\d+', token):
        return float(token)
    if token.startswith('[') and token.endswith(']'):
        inner = token[1:-1].strip()
        if not inner:
            return []
        return [_parse_value(x) for x in _split_args(inner)]
    return token


def _extract_named_and_positional(args: List[str]) -> tuple[list[Any], dict[str, Any]]:
    positional: list[Any] = []
    named: dict[str, Any] = {}
    for arg in args:
        stripped = arg.strip()
        is_quoted = len(stripped) >= 2 and stripped[0] in ('"', "'") and stripped[-1] == stripped[0]
        if (not is_quoted) and re.match(r'^[A-Za-z_][A-Za-z0-9_]*\s*:', stripped):
            k, v = stripped.split(':', 1)
            named[k.strip()] = _parse_value(v)
        else:
            positional.append(_parse_value(stripped))
    return positional, named


def _parse_state(source: str) -> Dict[str, Any]:
    state: Dict[str, Any] = {}
    for name, raw_value in STATE_RE.findall(source):
        value = raw_value.strip()
        if value.startswith('win.'):
            continue
        state[name] = _parse_value(value)
    return state


def parse_window_spec(source: str) -> Dict[str, Any]:
    spec: Dict[str, Any] = {
        'title': 'Mellow App',
        'width': 960,
        'height': 640,
        'widgets': [],
        'layout': 'vstack',
        'menus': [],
        'state': _parse_state(source),
        'events': [],
        'platforms': ['windows', 'linux'],
        'runtime': 'native-ui',
        'backend': 'ttk',
    }
    m = WINDOW_RE.search(source)
    if m:
        args = _split_args(m.group(1))
        positional, named = _extract_named_and_positional(args)
        if positional:
            spec['title'] = positional[0] if positional[0] is not None else spec['title']
        if len(positional) > 1 and positional[1] is not None:
            spec['width'] = int(positional[1])
        if len(positional) > 2 and positional[2] is not None:
            spec['height'] = int(positional[2])
        spec['title'] = named.get('title', spec['title'])
        spec['width'] = int(named.get('width', spec['width']))
        spec['height'] = int(named.get('height', spec['height']))
        spec['layout'] = str(named.get('layout', spec['layout']))
        platforms = named.get('platforms', spec['platforms'])
        spec['platforms'] = list(platforms) if isinstance(platforms, list) else spec['platforms']

    for kind, args_raw in CALL_RE.findall(source):
        args = _split_args(args_raw)
        positional, named = _extract_named_and_positional(args)
        if kind in ('vstack', 'hstack', 'grid'):
            spec['layout'] = kind
            if named:
                spec['layout_options'] = named
            continue
        if kind == 'menu':
            label = positional[1] if len(positional) > 1 else named.get('label', 'Menu')
            items = positional[2] if len(positional) > 2 else named.get('items', [])
            spec['menus'].append({'label': label, 'items': items if isinstance(items, list) else []})
            continue
        if kind == 'menu_item':
            menu_name = positional[1] if len(positional) > 1 else named.get('menu', 'Menu')
            item_label = positional[2] if len(positional) > 2 else named.get('label', '')
            action = positional[3] if len(positional) > 3 else named.get('action', '')
            accelerator = named.get('accelerator')
            for menu in spec['menus']:
                if menu.get('label') == menu_name:
                    menu.setdefault('items', []).append({'label': item_label, 'action': action, 'accelerator': accelerator})
                    break
            else:
                spec['menus'].append({'label': menu_name, 'items': [{'label': item_label, 'action': action, 'accelerator': accelerator}]})
            continue
        if len(positional) < 2 and 'text' not in named:
            continue
        widget: Dict[str, Any] = {
            'type': kind,
            'text': positional[1] if len(positional) > 1 else named.get('text', ''),
            'bind': named.get('bind'),
            'id': named.get('id'),
            'placeholder': named.get('placeholder'),
            'options': named.get('options') or positional[2] if kind in ('select', 'listbox') and len(positional) > 2 else named.get('options'),
            'action': named.get('action'),
        }
        if len(positional) > 2 and widget.get('action') is None and kind not in ('input', 'textarea', 'checkbox', 'select', 'listbox', 'slider'):
            widget['action'] = positional[2]
        if kind == 'checkbox':
            widget['default'] = bool(named.get('default', positional[2] if len(positional) > 2 else False))
        if kind == 'spacer':
            widget['size'] = int(named.get('size', positional[1] if positional else 12) or 12)
        if kind == 'slider':
            widget['min'] = int(named.get('min', positional[2] if len(positional) > 2 else 0) or 0)
            widget['max'] = int(named.get('max', positional[3] if len(positional) > 3 else 100) or 100)
        widget = {k: v for k, v in widget.items() if v is not None}
        spec['widgets'].append(widget)
        if widget.get('action'):
            spec['events'].append({'source': widget.get('id') or widget.get('text') or kind, 'action': widget['action']})
    return spec


def parse_window_file(path: str | Path) -> Dict[str, Any]:
    return parse_window_spec(Path(path).read_text(encoding='utf-8'))


def _interpolate(text: str, state: Dict[str, Any]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        return str(state.get(key, ''))
    return re.sub(r'\{\{\s*state\.(\w+)\s*\}\}', repl, str(text))


def _apply_action(action: str, *, root: Any, state: Dict[str, Any], refresh: Any) -> None:
    action = str(action or '').strip()
    if not action:
        return
    low = action.lower()
    if low in ('close', 'quit', 'exit'):
        root.destroy()
        return
    if low.startswith('print:'):
        print(action.split(':', 1)[1])
        return
    if low.startswith('set:') and '=' in action:
        payload = action.split(':', 1)[1]
        key, value = payload.split('=', 1)
        state[key.strip()] = _parse_value(value.strip())
        refresh()
        return
    if low.startswith('inc:'):
        key = action.split(':', 1)[1].strip()
        state[key] = int(state.get(key, 0) or 0) + 1
        refresh()
        return
    if low.startswith('toggle:'):
        key = action.split(':', 1)[1].strip()
        state[key] = not bool(state.get(key, False))
        refresh()
        return
    print(action)


class DesktopRuntime:
    """Cross-platform desktop runtime layer for Windows/Linux.

    This runtime is intentionally backend-driven so Mellow's UI/event/state model
    stays stable even if the widget backend changes later. Current backend: Tk/ttk.
    """

    def __init__(self, spec: Dict[str, Any]):
        self.spec = dict(spec)
        self.state: Dict[str, Any] = dict(spec.get('state') or {})

    def launch(self) -> int:
        import tkinter as tk
        from tkinter import ttk

        root = tk.Tk()
        root.title(str(self.spec.get('title', 'Mellow App')))
        root.geometry(f"{int(self.spec.get('width', 960))}x{int(self.spec.get('height', 640))}")
        refreshers: List[Callable[[], None]] = []

        def refresh_all() -> None:
            for fn in refreshers:
                fn()

        if self.spec.get('menus'):
            menu_bar = tk.Menu(root)
            for menu in self.spec['menus']:
                sub = tk.Menu(menu_bar, tearoff=0)
                for item in menu.get('items') or []:
                    if isinstance(item, dict):
                        label = str(item.get('label', 'Item'))
                        action = str(item.get('action', ''))
                        accelerator = item.get('accelerator')
                    else:
                        label = str(item)
                        action = f'print:{label}'
                        accelerator = None
                    sub.add_command(label=label, accelerator=accelerator or '', command=lambda a=action: _apply_action(a, root=root, state=self.state, refresh=refresh_all))
                menu_bar.add_cascade(label=str(menu.get('label', 'Menu')), menu=sub)
            root.config(menu=menu_bar)

        frame = ttk.Frame(root, padding=16)
        frame.pack(fill='both', expand=True)
        layout = self.spec.get('layout', 'vstack')
        horizontal = layout == 'hstack'

        for index, widget in enumerate(self.spec.get('widgets', [])):
            kind = widget.get('type')
            text = str(widget.get('text', ''))
            bind = widget.get('bind')
            pack_kwargs = {'pady': 6, 'anchor': 'w'}
            if horizontal:
                pack_kwargs['side'] = 'left'
                pack_kwargs['padx'] = 6
            if layout == 'grid':
                pack_kwargs = {}

            def _grid_pos(default_row: int) -> dict[str, int | str]:
                return {'row': int(widget.get('row', default_row)), 'column': int(widget.get('col', 0)), 'padx': 8, 'pady': 6, 'sticky': str(widget.get('sticky', 'w'))}

            if kind == 'label':
                label = ttk.Label(frame, text=_interpolate(text, self.state))
                if layout == 'grid':
                    label.grid(**_grid_pos(index))
                else:
                    label.pack(**pack_kwargs)
                refreshers.append(lambda lbl=label, template=text: lbl.config(text=_interpolate(template, self.state)))
            elif kind == 'button':
                action = str(widget.get('action', '') or '')
                btn = ttk.Button(frame, text=text, command=lambda a=action: _apply_action(a, root=root, state=self.state, refresh=refresh_all))
                if layout == 'grid':
                    btn.grid(**_grid_pos(index))
                else:
                    btn.pack(**pack_kwargs)
            elif kind == 'input':
                var = tk.StringVar(value=str(self.state.get(bind, text) if bind else text))
                entry = ttk.Entry(frame, textvariable=var)
                if layout == 'grid':
                    entry.grid(**_grid_pos(index))
                else:
                    entry.pack(fill='x', expand=not horizontal, **{k: v for k, v in pack_kwargs.items() if k != 'anchor'})
                if bind:
                    var.trace_add('write', lambda *_a, key=bind, v=var: self.state.__setitem__(key, v.get()))
                    refreshers.append(lambda key=bind, v=var: v.set(str(self.state.get(key, ''))))
            elif kind == 'textarea':
                box = tk.Text(frame, height=8)
                box.insert('1.0', str(self.state.get(bind, text) if bind else text))
                if layout == 'grid':
                    box.grid(**_grid_pos(index))
                else:
                    box.pack(fill='both', expand=True, **{k: v for k, v in pack_kwargs.items() if k != 'anchor'})
                if bind:
                    def _sync_text(event: Any, key: str = str(bind), widget_obj: Any = box) -> None:
                        self.state[key] = widget_obj.get('1.0', 'end-1c')
                    box.bind('<KeyRelease>', _sync_text)
                    refreshers.append(lambda key=bind, widget_obj=box: (widget_obj.delete('1.0', 'end'), widget_obj.insert('1.0', str(self.state.get(key, '')))))
            elif kind == 'checkbox':
                var = tk.BooleanVar(value=bool(self.state.get(bind, widget.get('default', False))))
                chk = ttk.Checkbutton(frame, text=text, variable=var)
                if layout == 'grid':
                    chk.grid(**_grid_pos(index))
                else:
                    chk.pack(**pack_kwargs)
                if bind:
                    var.trace_add('write', lambda *_a, key=bind, v=var: self.state.__setitem__(key, bool(v.get())))
                    refreshers.append(lambda key=bind, v=var: v.set(bool(self.state.get(key, False))))
            elif kind == 'select':
                options = widget.get('options') or []
                if isinstance(options, str):
                    options = [options]
                var = tk.StringVar(value=str(self.state.get(bind, options[0] if options else text)))
                combo = ttk.Combobox(frame, values=list(options), textvariable=var, state='readonly')
                if layout == 'grid':
                    combo.grid(**_grid_pos(index))
                else:
                    combo.pack(fill='x', expand=not horizontal, **{k: v for k, v in pack_kwargs.items() if k != 'anchor'})
                if bind:
                    var.trace_add('write', lambda *_a, key=bind, v=var: self.state.__setitem__(key, v.get()))
                    refreshers.append(lambda key=bind, v=var: v.set(str(self.state.get(key, ''))))
            elif kind == 'slider':
                mn, mx = int(widget.get('min', 0)), int(widget.get('max', 100))
                var = tk.DoubleVar(value=float(self.state.get(bind, mn)))
                scale = ttk.Scale(frame, from_=mn, to=mx, variable=var)
                if layout == 'grid':
                    scale.grid(**_grid_pos(index))
                else:
                    scale.pack(fill='x', expand=True, **{k: v for k, v in pack_kwargs.items() if k != 'anchor'})
                if bind:
                    var.trace_add('write', lambda *_a, key=bind, v=var: self.state.__setitem__(key, int(float(v.get()))))
                    refreshers.append(lambda key=bind, v=var: v.set(float(self.state.get(key, mn))))
            elif kind == 'listbox':
                options = widget.get('options') or []
                if isinstance(options, str):
                    options = [options]
                listbox = tk.Listbox(frame, height=min(8, max(3, len(options))))
                for opt in options:
                    listbox.insert('end', str(opt))
                if layout == 'grid':
                    listbox.grid(**_grid_pos(index))
                else:
                    listbox.pack(fill='both', expand=True, **{k: v for k, v in pack_kwargs.items() if k != 'anchor'})
                if bind:
                    def _sync_list(_event: Any, key: str = str(bind), lb: Any = listbox) -> None:
                        sel = lb.curselection()
                        self.state[key] = lb.get(sel[0]) if sel else ''
                    listbox.bind('<<ListboxSelect>>', _sync_list)
            elif kind == 'spacer':
                spacer = ttk.Frame(frame, height=int(widget.get('size', 12)))
                if layout == 'grid':
                    spacer.grid(**_grid_pos(index))
                else:
                    spacer.pack(fill='x')

        root.mainloop()
        return 0


def launch_window(spec: Dict[str, Any]) -> int:
    return DesktopRuntime(spec).launch()


def dump_spec_json(path: str | Path) -> str:
    return json.dumps(parse_window_file(path), ensure_ascii=False, indent=2)


def desktop_status() -> Dict[str, Any]:
    return {
        'ok': True,
        'engine': 'native-ui-runtime',
        'backend': 'ttk',
        'cross_platform': ['windows', 'linux'],
        'supported': ['window', 'label', 'button', 'input', 'textarea', 'checkbox', 'select', 'slider', 'listbox', 'menu', 'menu_item', 'vstack', 'hstack', 'grid', 'run'],
        'builder': 'portable-bundle',
        'requires_pyinstaller': False,
        'python': sys.version.split()[0],
        'platform': sys.platform,
    }


def _portable_launcher_py(entry_rel: str) -> str:
    return textwrap.dedent(f'''
    from pathlib import Path
    import sys

    ROOT = Path(__file__).resolve().parent
    VENDORED_SRC = ROOT / "runtime" / "src"
    if str(VENDORED_SRC) not in sys.path:
        sys.path.insert(0, str(VENDORED_SRC))

    from mellowlang.desktop_host import parse_window_file, launch_window

    entry = (ROOT / {entry_rel!r}).resolve()
    raise SystemExit(launch_window(parse_window_file(entry)))
    ''').strip() + '\n'


def build_desktop_bundle(entry_file: str | Path, *, out_dir: str | Path = 'dist', name: str | None = None, onefile: bool = False, windowed: bool = True) -> Dict[str, Any]:
    entry = Path(entry_file).resolve()
    project_root = entry.parent.parent if entry.parent.name == 'src' else entry.parent
    build_dir = Path(out_dir).resolve()
    app_name = name or project_root.name.replace('-', '_')
    bundle_root = build_dir / app_name
    runtime_src = bundle_root / 'runtime' / 'src'
    app_src = bundle_root / 'app'
    for folder in (runtime_src, app_src):
        folder.mkdir(parents=True, exist_ok=True)

    mellow_src = Path(__file__).resolve().parent
    shutil.copytree(mellow_src, runtime_src / 'mellowlang', dirs_exist_ok=True)
    shutil.copytree(project_root / 'src', app_src / 'src', dirs_exist_ok=True)
    for optional in ('mellow.json', 'mellow.toml', 'README.md'):
        src = project_root / optional
        if src.exists():
            shutil.copy2(src, bundle_root / optional)

    launcher_py = bundle_root / 'run_app.py'
    entry_rel = str(Path('app') / 'src' / entry.name).replace('\\', '/')
    launcher_py.write_text(_portable_launcher_py(entry_rel), encoding='utf-8')

    linux_sh = bundle_root / 'run_linux.sh'
    linux_sh.write_text('#!/usr/bin/env bash\nset -e\nPYTHON_BIN=${PYTHON_BIN:-python3}\n"$PYTHON_BIN" "$(dirname "$0")/run_app.py"\n', encoding='utf-8')
    os.chmod(linux_sh, 0o755)
    windows_bat = bundle_root / 'run_windows.bat'
    windows_bat.write_text('@echo off\r\nset PYTHON_BIN=%PYTHON_BIN%\r\nif "%PYTHON_BIN%"=="" set PYTHON_BIN=python\r\n%PYTHON_BIN% "%~dp0run_app.py"\r\n', encoding='utf-8')

    manifest = {
        'name': app_name,
        'entry': str(entry),
        'bundle_dir': str(bundle_root),
        'out_dir': str(build_dir),
        'launcher': str(launcher_py),
        'spec_file': str(bundle_root / 'bundle.spec.json'),
        'scripts': {'linux': str(linux_sh), 'windows': str(windows_bat)},
        'platforms': ['windows', 'linux'],
        'builder': 'portable-bundle',
        'windowed': windowed,
        'onefile': False,
        'requires_pyinstaller': False,
        'note': 'Portable bundle generated. Target machine needs Python 3 + Tk installed.',
        'runtime': {'engine': 'native-ui-runtime', 'backend': 'ttk'},
    }
    (bundle_root / 'bundle.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    (bundle_root / 'bundle.spec.json').write_text(json.dumps({'entry': str(entry), 'runtime': manifest['runtime'], 'builder': manifest['builder']}, ensure_ascii=False, indent=2), encoding='utf-8')
    return manifest
