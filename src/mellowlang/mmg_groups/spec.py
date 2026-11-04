"""Parse `mmg.app(...)` draw calls into the spec every MMG backend reads,
and dump one from disk."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .graph import _build_render_graph
from .parsing import (APP_RE, CALL_RE, _action_expr_to_command,
                      _extract_named_and_positional, _scan_keep_env, _split_args)


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


def dump_mmg_spec_json(path: str | Path) -> str:
    return json.dumps(parse_mmg_file(path), indent=2, ensure_ascii=False)
