"""The window loop: load textures, replay input events into app state,
draw the scene tree, tick physics and follow the camera."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Tuple


_VAR_RE = re.compile(r'\b(state\.[A-Za-z_][A-Za-z0-9_]*|[A-Za-z_][A-Za-z0-9_]*)\b')


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
