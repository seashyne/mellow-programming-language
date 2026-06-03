from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

APP_RE = re.compile(r'mmg\.app\((.*?)\)', re.DOTALL)
CALL_RE = re.compile(
    r'mmg\.(clear|rect|circle|line|text|scene|camera|texture|sprite|on|frame)\((.*?)\)',
    re.DOTALL,
)
KEEP_RE = re.compile(r'^\s*keep\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$', re.MULTILINE)
_VAR_RE = re.compile(r'\b(state\.[A-Za-z_][A-Za-z0-9_]*|[A-Za-z_][A-Za-z0-9_]*)\b')


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


def _parse_value(token: str, env: Dict[str, Any] | None = None) -> Any:
    token = token.strip()
    if not token:
        return None
    env = env or {}
    if token[0] in ('"', "'") and token[-1] == token[0]:
        return token[1:-1]
    low = token.lower()
    if low == 'true':
        return True
    if low == 'false':
        return False
    if low == 'null':
        return None
    if token.startswith('[') and token.endswith(']'):
        inner = token[1:-1].strip()
        if not inner:
            return []
        return [_parse_value(p, env) for p in _split_args(inner)]
    if token.startswith('{') and token.endswith('}'):
        inner = token[1:-1].strip()
        if not inner:
            return {}
        out: Dict[str, Any] = {}
        for part in _split_args(inner):
            if ':' not in part:
                continue
            k, v = part.split(':', 1)
            out[str(_parse_value(k, env))] = _parse_value(v, env)
        return out
    if re.fullmatch(r'-?\d+', token):
        return int(token)
    if re.fullmatch(r'-?\d+\.\d+', token):
        return float(token)
    if token in env:
        return env[token]
    return token


def _extract_named_and_positional(args: List[str], env: Dict[str, Any] | None = None) -> Tuple[list[Any], dict[str, Any]]:
    positional: list[Any] = []
    named: dict[str, Any] = {}
    for arg in args:
        stripped = arg.strip()
        is_quoted = len(stripped) >= 2 and stripped[0] in ('"', "'") and stripped[-1] == stripped[0]
        if (not is_quoted) and re.match(r'^[A-Za-z_][A-Za-z0-9_]*\s*:', stripped):
            k, v = stripped.split(':', 1)
            named[k.strip()] = _parse_value(v, env)
        else:
            positional.append(_parse_value(stripped, env))
    return positional, named


def _scan_keep_env(source: str) -> Dict[str, Any]:
    env: Dict[str, Any] = {}
    for name, raw in KEEP_RE.findall(source):
        try:
            env[name] = _parse_value(raw, env)
        except Exception:
            env[name] = raw.strip()
    return env


def _action_expr_to_command(expr: Any) -> Dict[str, Any]:
    if isinstance(expr, str):
        expr = expr.strip()
        if not expr:
            return {'type': 'noop'}
        if expr == 'close':
            return {'type': 'close'}
        if expr.startswith('print:'):
            return {'type': 'print', 'message': expr.split(':', 1)[1]}
        if expr.startswith('set:') and '=' in expr:
            payload = expr.split(':', 1)[1]
            key, value = payload.split('=', 1)
            return {'type': 'set', 'key': key.strip(), 'value': _parse_value(value)}
        if expr.startswith('inc:'):
            return {'type': 'inc', 'key': expr.split(':', 1)[1].strip(), 'delta': 1}
        if expr.startswith('toggle:'):
            return {'type': 'toggle', 'key': expr.split(':', 1)[1].strip()}
    return {'type': 'script', 'value': expr}


def _build_render_graph(spec: Dict[str, Any]) -> Dict[str, Any]:
    scene_nodes = []
    for scene in spec.get('scenes') or []:
        children = []
        for sprite in scene.get('sprites') or []:
            children.append({'kind': 'sprite', 'id': sprite.get('id'), 'texture': sprite.get('texture'), 'x': sprite.get('x'), 'y': sprite.get('y')})
        for draw in scene.get('draw') or []:
            children.append({'kind': draw.get('type'), 'id': draw.get('id')})
        scene_nodes.append({'kind': 'scene', 'id': scene.get('id'), 'active': scene.get('active', True), 'children': children})
    return {
        'passes': [
            {'name': 'clear', 'target': 'backbuffer', 'color': spec.get('clear')},
            {'name': 'scene', 'target': 'backbuffer', 'scenes': [s.get('id') for s in spec.get('scenes') or []]},
            {'name': 'ui', 'target': 'backbuffer'},
            {'name': 'present', 'target': 'screen'},
        ],
        'nodes': scene_nodes,
        'camera': spec.get('camera'),
    }


def parse_mmg_spec(source: str) -> Dict[str, Any]:
    env = _scan_keep_env(source)
    spec: Dict[str, Any] = {
        'title': 'MMG App',
        'width': 960,
        'height': 640,
        'fps': 60,
        'backend': 'mmg-render-core',
        'platforms': ['windows', 'linux'],
        'clear': '#101418',
        'draw': [],
        'textures': [],
        'scenes': [],
        'events': [],
        'camera': {'x': 0, 'y': 0, 'zoom': 1.0},
        'frame': {'enabled': True, 'fps': 60, 'tick': None},
        'state': {k: v for k, v in env.items() if isinstance(v, (str, int, float, bool, list, dict, type(None)))}
    }
    app_name = None
    current_scene: Dict[str, Any] | None = None
    m = APP_RE.search(source)
    if m:
        args = _split_args(m.group(1))
        positional, named = _extract_named_and_positional(args, env)
        spec['title'] = named.get('title', positional[0] if positional else spec['title']) or spec['title']
        spec['width'] = int(named.get('width', positional[1] if len(positional) > 1 else spec['width']))
        spec['height'] = int(named.get('height', positional[2] if len(positional) > 2 else spec['height']))
        spec['fps'] = int(named.get('fps', spec['fps']))
        spec['frame']['fps'] = spec['fps']
        spec['clear'] = str(named.get('clear', spec['clear']))
        app_name = 'app'
    for kind, raw in CALL_RE.findall(source):
        args = _split_args(raw)
        positional, named = _extract_named_and_positional(args, env)
        if kind == 'clear':
            color = positional[1] if len(positional) > 1 else named.get('color') or spec['clear']
            spec['clear'] = str(color)
            continue
        if kind == 'scene':
            scene_name = positional[1] if len(positional) > 1 else named.get('name') or f"scene_{len(spec['scenes'])+1}"
            current_scene = {'id': str(scene_name), 'active': named.get('active', True), 'sprites': [], 'draw': []}
            spec['scenes'].append(current_scene)
            continue
        if kind == 'camera':
            spec['camera'] = {
                'x': float(named.get('x', positional[1] if len(positional) > 1 else 0) or 0),
                'y': float(named.get('y', positional[2] if len(positional) > 2 else 0) or 0),
                'zoom': float(named.get('zoom', positional[3] if len(positional) > 3 else 1.0) or 1.0),
                'follow': named.get('follow'),
            }
            continue
        if kind == 'frame':
            spec['frame'] = {
                'enabled': True,
                'fps': int(named.get('fps', spec.get('fps', 60))),
                'tick': named.get('tick'),
                'delta_ms': int(1000 / max(1, int(named.get('fps', spec.get('fps', 60))))),
            }
            spec['fps'] = spec['frame']['fps']
            continue
        if kind == 'texture':
            name = positional[1] if len(positional) > 1 else named.get('name') or f"tex_{len(spec['textures'])+1}"
            texture = {
                'id': str(name),
                'source': named.get('source', positional[2] if len(positional) > 2 else ''),
                'filter': named.get('filter', 'linear'),
                'wrap': named.get('wrap', 'clamp'),
            }
            spec['textures'].append(texture)
            continue
        if kind == 'sprite':
            target_scene = current_scene
            if not target_scene:
                target_scene = {'id': 'main', 'active': True, 'sprites': [], 'draw': []}
                spec['scenes'].append(target_scene)
                current_scene = target_scene
            sprite = {
                'id': named.get('id', f"sprite_{len(target_scene['sprites'])+1}"),
                'texture': named.get('texture', positional[1] if len(positional) > 1 else None),
                'x': float(named.get('x', positional[2] if len(positional) > 2 else 0) or 0),
                'y': float(named.get('y', positional[3] if len(positional) > 3 else 0) or 0),
                'w': float(named.get('w', positional[4] if len(positional) > 4 else 64) or 64),
                'h': float(named.get('h', positional[5] if len(positional) > 5 else 64) or 64),
                'vx': float(named.get('vx', 0) or 0),
                'vy': float(named.get('vy', 0) or 0),
                'fill': named.get('fill', '#5cc8ff'),
                'anchor': named.get('anchor', 'nw'),
            }
            target_scene['sprites'].append(sprite)
            continue
        if kind == 'on':
            evt = {
                'target': positional[0] if positional else app_name,
                'event': positional[1] if len(positional) > 1 else named.get('event', 'unknown'),
                'match': positional[2] if len(positional) > 2 else named.get('match'),
                'action': _action_expr_to_command(positional[3] if len(positional) > 3 else named.get('action', 'noop')),
            }
            spec['events'].append(evt)
            continue
        draw_target = current_scene['draw'] if current_scene else spec['draw']
        if kind == 'rect' and len(positional) >= 5:
            draw_target.append({'type': 'rect', 'id': f"rect_{len(draw_target)+1}", 'x': positional[1], 'y': positional[2], 'w': positional[3], 'h': positional[4], 'fill': named.get('fill', '#5cc8ff'), 'stroke': named.get('stroke', ''), 'width': named.get('width', 1)})
        elif kind == 'circle' and len(positional) >= 4:
            draw_target.append({'type': 'circle', 'id': f"circle_{len(draw_target)+1}", 'x': positional[1], 'y': positional[2], 'r': positional[3], 'fill': named.get('fill', '#7ef29a'), 'stroke': named.get('stroke', ''), 'width': named.get('width', 1)})
        elif kind == 'line' and len(positional) >= 5:
            draw_target.append({'type': 'line', 'id': f"line_{len(draw_target)+1}", 'x1': positional[1], 'y1': positional[2], 'x2': positional[3], 'y2': positional[4], 'stroke': named.get('stroke', '#ffffff'), 'width': named.get('width', 2)})
        elif kind == 'text' and len(positional) >= 4:
            draw_target.append({'type': 'text', 'id': f"text_{len(draw_target)+1}", 'x': positional[1], 'y': positional[2], 'text': positional[3], 'fill': named.get('fill', '#ffffff'), 'size': named.get('size', 18), 'anchor': named.get('anchor', 'nw')})
    if not spec['scenes']:
        spec['scenes'].append({'id': 'main', 'active': True, 'sprites': [], 'draw': []})
    spec['render_graph'] = _build_render_graph(spec)
    spec['feature_flags'] = {
        'scene_graph': True,
        'sprite_system': True,
        'texture_system': True,
        'camera': True,
        'frame_loop': True,
        'input_events': True,
        'render_graph': True,
    }
    return spec


def parse_mmg_file(path: str | Path) -> Dict[str, Any]:
    return parse_mmg_spec(Path(path).read_text(encoding='utf-8'))


def mmg_status() -> Dict[str, Any]:
    return {
        'engine': 'mellow-magic-graphics',
        'backend': 'mmg-render-core/tk-canvas',
        'portable_bundle': True,
        'python_required': True,
        'platform': sys.platform,
        'display_available': bool(os.environ.get('DISPLAY') or sys.platform.startswith('win') or sys.platform == 'darwin'),
        'features': ['scene-graph', 'sprite', 'texture', 'camera', 'frame-loop', 'input-events', 'render-graph'],
        'note': 'MMG Render Core is a cross-platform render/runtime foundation. It is not a shader/GPU-native engine yet.',
    }


def _eval_watch(expr: str, state: Dict[str, Any]) -> Any:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key.startswith('state.'):
            key = key.split('.', 1)[1]
        if key in {'and', 'or', 'not', 'True', 'False'}:
            return match.group(0)
        return repr(state.get(key))

    safe = _VAR_RE.sub(repl, expr)
    try:
        return eval(safe, {'__builtins__': {}}, {})
    except Exception:
        return None


def launch_mmg(spec: Dict[str, Any]) -> int:
    import tkinter as tk

    root = tk.Tk()
    root.title(str(spec.get('title', 'MMG App')))
    width = int(spec.get('width', 960))
    height = int(spec.get('height', 640))
    root.geometry(f"{width}x{height}")
    canvas = tk.Canvas(root, width=width, height=height, highlightthickness=0, bg=str(spec.get('clear', '#101418')))
    canvas.pack(fill='both', expand=True)

    state: Dict[str, Any] = dict(spec.get('state') or {})
    textures: Dict[str, Any] = {}
    texture_meta: Dict[str, Dict[str, Any]] = {t['id']: t for t in spec.get('textures') or []}

    for texture in spec.get('textures') or []:
        src = str(texture.get('source') or '')
        img = None
        if src:
            p = Path(src)
            if p.exists():
                try:
                    img = tk.PhotoImage(file=str(p))
                except Exception:
                    img = None
        textures[texture['id']] = img

    camera = dict(spec.get('camera') or {})
    events = spec.get('events') or []
    frame = spec.get('frame') or {'enabled': True, 'fps': 60, 'delta_ms': 16}

    def transform_xy(x: float, y: float) -> Tuple[float, float]:
        zoom = float(camera.get('zoom', 1.0) or 1.0)
        cx = float(camera.get('x', 0) or 0)
        cy = float(camera.get('y', 0) or 0)
        return (x - cx) * zoom, (y - cy) * zoom

    def do_action(action: Dict[str, Any]) -> None:
        typ = action.get('type')
        if typ == 'close':
            root.destroy()
        elif typ == 'print':
            print(action.get('message', ''))
        elif typ == 'set':
            state[str(action.get('key'))] = action.get('value')
        elif typ == 'inc':
            key = str(action.get('key'))
            state[key] = int(state.get(key, 0) or 0) + int(action.get('delta', 1) or 1)
        elif typ == 'toggle':
            key = str(action.get('key'))
            state[key] = not bool(state.get(key, False))
        elif typ == 'script':
            val = action.get('value')
            if isinstance(val, str) and val.startswith('watch:'):
                print(_eval_watch(val.split(':', 1)[1], state))

    def handle_event(evt_name: str, match_val: Any = None) -> None:
        for evt in events:
            if evt.get('event') != evt_name:
                continue
            expected = evt.get('match')
            if expected not in (None, '', '*') and match_val not in (expected, str(expected)):
                continue
            do_action(evt.get('action') or {'type': 'noop'})

    def render() -> None:
        canvas.delete('all')
        canvas.configure(bg=str(spec.get('clear', '#101418')))
        # top-level draw calls
        for item in spec.get('draw') or []:
            kind = item.get('type')
            if kind == 'rect':
                x, y = transform_xy(float(item['x']), float(item['y']))
                w = float(item['w']) * float(camera.get('zoom', 1.0) or 1.0)
                h = float(item['h']) * float(camera.get('zoom', 1.0) or 1.0)
                canvas.create_rectangle(x, y, x + w, y + h, fill=item.get('fill', ''), outline=item.get('stroke', ''), width=item.get('width', 1))
            elif kind == 'circle':
                x, y = transform_xy(float(item['x']), float(item['y']))
                r = float(item['r']) * float(camera.get('zoom', 1.0) or 1.0)
                canvas.create_oval(x - r, y - r, x + r, y + r, fill=item.get('fill', ''), outline=item.get('stroke', ''), width=item.get('width', 1))
            elif kind == 'line':
                x1, y1 = transform_xy(float(item['x1']), float(item['y1']))
                x2, y2 = transform_xy(float(item['x2']), float(item['y2']))
                canvas.create_line(x1, y1, x2, y2, fill=item.get('stroke', '#fff'), width=item.get('width', 2))
            elif kind == 'text':
                x, y = transform_xy(float(item['x']), float(item['y']))
                canvas.create_text(x, y, text=str(item.get('text', '')), fill=item.get('fill', '#fff'), anchor=item.get('anchor', 'nw'), font=('Arial', int(item.get('size', 18))))
        # scenes + sprites
        for scene in spec.get('scenes') or []:
            if not scene.get('active', True):
                continue
            for draw in scene.get('draw') or []:
                kind = draw.get('type')
                if kind == 'rect':
                    x, y = transform_xy(float(draw['x']), float(draw['y']))
                    w = float(draw['w']) * float(camera.get('zoom', 1.0) or 1.0)
                    h = float(draw['h']) * float(camera.get('zoom', 1.0) or 1.0)
                    canvas.create_rectangle(x, y, x + w, y + h, fill=draw.get('fill', ''), outline=draw.get('stroke', ''), width=draw.get('width', 1))
                elif kind == 'text':
                    x, y = transform_xy(float(draw['x']), float(draw['y']))
                    canvas.create_text(x, y, text=str(draw.get('text', '')), fill=draw.get('fill', '#fff'), anchor=draw.get('anchor', 'nw'), font=('Arial', int(draw.get('size', 18))))
            for sprite in scene.get('sprites') or []:
                x, y = transform_xy(float(sprite.get('x', 0)), float(sprite.get('y', 0)))
                w = float(sprite.get('w', 64)) * float(camera.get('zoom', 1.0) or 1.0)
                h = float(sprite.get('h', 64)) * float(camera.get('zoom', 1.0) or 1.0)
                tex_id = sprite.get('texture')
                img = textures.get(tex_id)
                if img is not None:
                    canvas.create_image(x, y, anchor=str(sprite.get('anchor', 'nw')), image=img)
                else:
                    fill = sprite.get('fill') or '#5cc8ff'
                    outline = '#ffffff' if tex_id in texture_meta else ''
                    canvas.create_rectangle(x, y, x + w, y + h, fill=fill, outline=outline)
                    if tex_id:
                        canvas.create_text(x + 4, y + 4, anchor='nw', fill='#ffffff', text=str(tex_id), font=('Arial', 10))
        canvas.create_text(width - 10, 10, anchor='ne', fill='#94a3b8', text=f"MMG {spec.get('fps', 60)} FPS", font=('Arial', 10))

    def tick() -> None:
        follow = camera.get('follow')
        if follow:
            for scene in spec.get('scenes') or []:
                for sprite in scene.get('sprites') or []:
                    if sprite.get('id') == follow:
                        camera['x'] = max(0.0, float(sprite.get('x', 0)) - width / 2)
                        camera['y'] = max(0.0, float(sprite.get('y', 0)) - height / 2)
        for scene in spec.get('scenes') or []:
            for sprite in scene.get('sprites') or []:
                sprite['x'] = float(sprite.get('x', 0)) + float(sprite.get('vx', 0))
                sprite['y'] = float(sprite.get('y', 0)) + float(sprite.get('vy', 0))
        render()
        if frame.get('enabled', True):
            root.after(int(frame.get('delta_ms', max(1, int(1000 / max(1, int(spec.get('fps', 60))))))), tick)

    root.bind('<Escape>', lambda e: handle_event('key', 'Escape'))
    root.bind('<Key>', lambda e: handle_event('key', getattr(e, 'keysym', None)))
    canvas.bind('<Button-1>', lambda e: handle_event('click', 'left'))
    canvas.bind('<Button-3>', lambda e: handle_event('click', 'right'))
    render()
    if frame.get('enabled', True):
        root.after(int(frame.get('delta_ms', 16)), tick)
    root.mainloop()
    return 0


def dump_mmg_spec_json(path: str | Path) -> str:
    return json.dumps(parse_mmg_file(path), indent=2, ensure_ascii=False)
