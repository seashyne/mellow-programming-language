"""Turn a parsed spec into the render graph its backends walk."""

from __future__ import annotations

from typing import Any, Dict


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
