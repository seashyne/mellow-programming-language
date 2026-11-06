"""Mellow host syscall family: game."""

from __future__ import annotations

from typing import Any, Dict, List
import math as _math
from ..base import HostFunction, HostRegistry


def register_game_functions(h: HostRegistry) -> None:
    """Register the game syscalls on a fresh host registry."""
    # ---------------- v1.4.2: std.game ----------------

    # easing functions: t in [0,1] -> [0,1]
    def _ease_linear(t: float) -> float:
        return float(t)

    def _ease_in_quad(t: float) -> float:
        t = float(t)
        return t * t

    def _ease_out_quad(t: float) -> float:
        t = float(t)
        return 1.0 - (1.0 - t) * (1.0 - t)

    def _ease_in_out_quad(t: float) -> float:
        t = float(t)
        if t < 0.5:
            return 2.0 * t * t
        return 1.0 - _math.pow(-2.0 * t + 2.0, 2.0) / 2.0

    h.register(HostFunction('std.game.easing.linear', lambda a: _ease_linear(a[0]), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.game.easing.in_quad', lambda a: _ease_in_quad(a[0]), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.game.easing.out_quad', lambda a: _ease_out_quad(a[0]), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.game.easing.in_out_quad', lambda a: _ease_in_out_quad(a[0]), cost=1, min_args=1, max_args=1))

    # tween step helper: from, to, t, ease_name
    def _tween_step(args: List[Any]) -> Any:
        a0, a1, t = float(args[0]), float(args[1]), float(args[2])
        ease = str(args[3]) if len(args) >= 4 else 'linear'
        if ease in ('linear', 'ease_linear'):
            e = _ease_linear(t)
        elif ease in ('in_quad', 'ease_in_quad'):
            e = _ease_in_quad(t)
        elif ease in ('out_quad', 'ease_out_quad'):
            e = _ease_out_quad(t)
        elif ease in ('in_out_quad', 'ease_in_out_quad'):
            e = _ease_in_out_quad(t)
        else:
            # default safe
            e = _ease_linear(t)
        return a0 + (a1 - a0) * e

    h.register(HostFunction('std.game.tween.step', _tween_step, cost=1, min_args=3, max_args=4))

    # grid neighbor helpers (bounds aware)
    def _neighbors4(args: List[Any]) -> List[List[int]]:
        x, y, w, hgt = int(args[0]), int(args[1]), int(args[2]), int(args[3])
        out: List[List[int]] = []
        for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
            nx, ny = x+dx, y+dy
            if 0 <= nx < w and 0 <= ny < hgt:
                out.append([nx, ny])
        return out

    def _neighbors8(args: List[Any]) -> List[List[int]]:
        x, y, w, hgt = int(args[0]), int(args[1]), int(args[2]), int(args[3])
        out: List[List[int]] = []
        for dx, dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            nx, ny = x+dx, y+dy
            if 0 <= nx < w and 0 <= ny < hgt:
                out.append([nx, ny])
        return out

    h.register(HostFunction('std.game.grid.neighbors4', _neighbors4, cost=1, min_args=4, max_args=4))
    h.register(HostFunction('std.game.grid.neighbors8', _neighbors8, cost=1, min_args=4, max_args=4))

    # A* pathfinding on a grid (grid: list[list[int]] where 0=free, nonzero=blocked)
    def _astar(args: List[Any]) -> List[List[int]]:
        grid = args[0]
        start = args[1]
        goal = args[2]
        diag = bool(args[3]) if len(args) >= 4 else False

        if not isinstance(grid, list) or not grid:
            raise RuntimeError('std.game.path.astar: expected grid as non-empty list')
        if not isinstance(start, list) or len(start) != 2:
            raise RuntimeError('std.game.path.astar: expected start [x,y]')
        if not isinstance(goal, list) or len(goal) != 2:
            raise RuntimeError('std.game.path.astar: expected goal [x,y]')

        hgt = len(grid)
        w = len(grid[0]) if isinstance(grid[0], list) else 0
        if w <= 0:
            raise RuntimeError('std.game.path.astar: expected grid as list of rows')

        sx, sy = int(start[0]), int(start[1])
        gx, gy = int(goal[0]), int(goal[1])

        def inb(x: int, y: int) -> bool:
            return 0 <= x < w and 0 <= y < hgt

        def blocked(x: int, y: int) -> bool:
            try:
                return int(grid[y][x]) != 0
            except Exception:
                return True

        if not inb(sx, sy) or not inb(gx, gy) or blocked(sx, sy) or blocked(gx, gy):
            return []

        import heapq as _heapq

        moves = ((1,0),(-1,0),(0,1),(0,-1))
        if diag:
            moves = moves + ((1,1),(1,-1),(-1,1),(-1,-1))

        def heuristic(x: int, y: int) -> float:
            # Manhattan or Chebyshev
            dx, dy = abs(x-gx), abs(y-gy)
            return float(max(dx, dy) if diag else (dx + dy))

        openh: List[tuple] = []
        _heapq.heappush(openh, (heuristic(sx, sy), 0.0, sx, sy))
        came: Dict[tuple, tuple] = {}
        gscore: Dict[tuple, float] = {(sx, sy): 0.0}

        while openh:
            _, gcur, x, y = _heapq.heappop(openh)
            if (x, y) == (gx, gy):
                # reconstruct
                path: List[List[int]] = [[gx, gy]]
                cur = (gx, gy)
                while cur in came:
                    cur = came[cur]
                    path.append([cur[0], cur[1]])
                path.reverse()
                return path

            for dx, dy in moves:
                nx, ny = x+dx, y+dy
                if not inb(nx, ny) or blocked(nx, ny):
                    continue
                step_cost = 1.41421356237 if (dx != 0 and dy != 0) else 1.0
                ng = gcur + step_cost
                key = (nx, ny)
                if ng < gscore.get(key, 1e30):
                    came[key] = (x, y)
                    gscore[key] = ng
                    f = ng + heuristic(nx, ny)
                    _heapq.heappush(openh, (f, ng, nx, ny))

        return []

    h.register(HostFunction('std.game.path.astar', _astar, cost=5, min_args=3, max_args=4))

    # ==========================================
    # v1.5.1: Game scripting engine helpers
    # ==========================================
    def _scene_create(args):
        name = str(args[0]) if args else 'scene'
        width = int(args[1]) if len(args) > 1 else 320
        height = int(args[2]) if len(args) > 2 else 180
        return {"name": name, "size": [width, height], "entities": []}

    def _entity_create(args):
        eid = str(args[0]) if args else 'entity'
        x = float(args[1]) if len(args) > 1 else 0.0
        y = float(args[2]) if len(args) > 2 else 0.0
        w = float(args[3]) if len(args) > 3 else 1.0
        h2 = float(args[4]) if len(args) > 4 else 1.0
        return {"id": eid, "pos": [x, y], "size": [w, h2], "vel": [0.0, 0.0], "tags": args[5] if len(args) > 5 and isinstance(args[5], list) else []}

    def _entity_move(args):
        ent = dict(args[0]) if args and isinstance(args[0], dict) else {"pos": [0.0, 0.0]}
        dx = float(args[1]) if len(args) > 1 else 0.0
        dy = float(args[2]) if len(args) > 2 else 0.0
        pos = ent.get('pos', [0.0, 0.0])
        ent['pos'] = [float(pos[0]) + dx, float(pos[1]) + dy]
        ent['vel'] = [dx, dy]
        return ent

    def _collide_aabb(args):
        a = args[0] if args else {}
        b = args[1] if len(args) > 1 else {}
        ap = a.get('pos', [0.0, 0.0]); asz = a.get('size', [0.0, 0.0])
        bp = b.get('pos', [0.0, 0.0]); bsz = b.get('size', [0.0, 0.0])
        return not (ap[0] + asz[0] < bp[0] or bp[0] + bsz[0] < ap[0] or ap[1] + asz[1] < bp[1] or bp[1] + bsz[1] < ap[1])

    def _anim_frame(args):
        frame_count = max(1, int(args[0])) if args else 1
        time_s = float(args[1]) if len(args) > 1 else 0.0
        fps = float(args[2]) if len(args) > 2 else 12.0
        loop = bool(args[3]) if len(args) > 3 else True
        idx = int(time_s * fps)
        if loop:
            idx = idx % frame_count
        else:
            idx = min(frame_count - 1, idx)
        return {"frame": idx, "frame_count": frame_count}

    h.register(HostFunction('std.game.scene.create', _scene_create, cost=1, min_args=1, max_args=3))
    h.register(HostFunction('std.game.entity.create', _entity_create, cost=1, min_args=1, max_args=6))
    h.register(HostFunction('std.game.entity.move', _entity_move, cost=1, min_args=1, max_args=3))
    h.register(HostFunction('std.game.physics.collide_aabb', _collide_aabb, cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.game.anim.frame', _anim_frame, cost=1, min_args=1, max_args=4))

    # ==========================================
    # v1.4.6: เพิ่ม easing curves ใหม่
    # ==========================================
    def _ease_in_cubic(t: float) -> float:
        t = float(t)
        return t * t * t

    def _ease_out_cubic(t: float) -> float:
        t = float(t)
        return 1.0 - (1.0 - t) ** 3

    def _ease_in_out_cubic(t: float) -> float:
        t = float(t)
        return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2

    def _ease_in_back(t: float) -> float:
        t = float(t)
        c1, c3 = 1.70158, 1.70158 + 1
        return c3 * t * t * t - c1 * t * t

    def _ease_out_back(t: float) -> float:
        t = float(t)
        c1, c3 = 1.70158, 1.70158 + 1
        return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2

    def _ease_out_bounce(t: float) -> float:
        t = float(t)
        n1, d1 = 7.5625, 2.75
        if t < 1 / d1:
            return n1 * t * t
        elif t < 2 / d1:
            t -= 1.5 / d1
            return n1 * t * t + 0.75
        elif t < 2.5 / d1:
            t -= 2.25 / d1
            return n1 * t * t + 0.9375
        else:
            t -= 2.625 / d1
            return n1 * t * t + 0.984375

    def _ease_out_elastic(t: float) -> float:
        import math as _m
        t = float(t)
        if t == 0: return 0.0
        if t == 1: return 1.0
        c4 = (2 * _m.pi) / 3
        return pow(2, -10 * t) * _m.sin((t * 10 - 0.75) * c4) + 1

    h.register(HostFunction('std.game.easing.in_cubic', lambda a: _ease_in_cubic(a[0]), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.game.easing.out_cubic', lambda a: _ease_out_cubic(a[0]), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.game.easing.in_out_cubic', lambda a: _ease_in_out_cubic(a[0]), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.game.easing.in_back', lambda a: _ease_in_back(a[0]), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.game.easing.out_back', lambda a: _ease_out_back(a[0]), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.game.easing.out_bounce', lambda a: _ease_out_bounce(a[0]), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.game.easing.out_elastic', lambda a: _ease_out_elastic(a[0]), cost=1, min_args=1, max_args=1))
