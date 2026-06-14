# frinds/host.py
from __future__ import annotations
from dataclasses import dataclass
from ..range_core import MellowLangRange
from typing import Any, Callable, Dict, List, Optional, Tuple

# Public allowlist for safe get()/import usage
MODULE_ALLOWLIST = {
        "math": {
            "abs": "std.math.abs", "min": "std.math.min", "max": "std.math.max",
            "floor": "std.math.floor", "ceil": "std.math.ceil", "round": "std.math.round",
            "sqrt": "std.math.sqrt", "pow": "std.math.pow",
            "sin": "std.math.sin", "cos": "std.math.cos", "tan": "std.math.tan",
            "atan2": "std.math.atan2", "clamp": "std.math.clamp", "lerp": "std.math.lerp",
            # vectors
            "vec2": "std.math.vec2", "vec3": "std.math.vec3",
            "vec": "std.math.vector", "vector": "std.math.vector",
            "vec_add": "std.math.vec_add", "vec_sub": "std.math.vec_sub", "vec_mul": "std.math.vec_mul",
            "vec_dot": "std.math.vec_dot", "vec_len": "std.math.vec_len", "vec_norm": "std.math.vec_norm",
            "vec_dist": "std.math.vec_dist",
            "vec_lerp": "std.math.vec_lerp", "vec_limit": "std.math.vec_limit",
            "vec_dim": "std.math.vec_dim", "vec_axis": "std.math.vec_axis",
            "pi": "std.math.pi",
        },
        "time": {
            "unix": "std.time.unix", "ms": "std.time.ms", "now": "std.time.now",
        },
        "list": {
            "push": "std.list.push", "pop": "std.list.pop", "len": "std.list.len",
            "insert": "std.list.insert", "remove": "std.list.remove", "has": "std.list.has",
            "sort": "std.list.sort",
        },
        "map": {
            "get": "std.map.get", "set": "std.map.set", "keys": "std.map.keys",
            "values": "std.map.values", "has": "std.map.has",
        },
        "string": {
            "len": "std.string.len", "lower": "std.string.lower", "upper": "std.string.upper",
            "trim": "std.string.trim", "replace": "std.string.replace", "find": "std.string.find",
            "split": "std.string.split", "join": "std.string.join",
            # v1.4.7
            "starts_with": "std.string.starts_with", "ends_with": "std.string.ends_with",
            "contains": "std.string.contains", "repeat": "std.string.repeat",
            "pad_left": "std.string.pad_left", "pad_right": "std.string.pad_right",
            "format": "std.string.format",
        },
        "json": {
            "encode": "std.json.encode", "decode": "std.json.decode",
        },
        "money": {
            "of": "std.money.of",
            "add": "std.money.add",
            "sub": "std.money.sub",
            "mul": "std.money.mul",
            "div": "std.money.div",
            "quantize": "std.money.quantize",
            "format": "std.money.format",
            "amount": "std.money.amount",
            "currency": "std.money.currency",
            "eq": "std.money.eq",
            "lt": "std.money.lt",
            "gt": "std.money.gt",
        },
        "data": {
            "open_jsonl": "std.data.open_jsonl",
            "open_csv": "std.data.open_csv",
            "next": "std.data.next",
            "close": "std.data.close",
            "cancel": "std.data.cancel",
            "info": "std.data.info",
            "project": "std.data.project",
            "where": "std.data.where",
            "sum": "std.data.sum",
            "sqlite_open": "std.data.sqlite_open",
            "sqlite_close": "std.data.sqlite_close",
            "sqlite_query": "std.data.sqlite_query",
            "sqlite_execute": "std.data.sqlite_execute",
        },
        "ledger": {
            "create": "std.ledger.create",
            "post": "std.ledger.post",
            "verify": "std.ledger.verify",
            "balance": "std.ledger.balance",
            "entries": "std.ledger.entries",
        },
        "interop": {
            "available": "std.interop.available",
            "run": "std.interop.run",
            "describe": "std.interop.describe",
        },
        "ai": {
            # v1.4.7 game AI
            "decide": "std.ai.decide",
            "utility_choose": "std.ai.utility_choose",
            "bt_tick": "std.ai.bt_tick",
            "fsm_tick": "std.ai.fsm_tick",
            # v1.4.6: steering + perception
            "seek": "std.ai.steering.seek",
            "flee": "std.ai.steering.flee",
            "arrive": "std.ai.steering.arrive",
            "wander": "std.ai.steering.wander",
            "patrol": "std.ai.steering.patrol",
            "in_range": "std.ai.perception.in_range",
            "in_sight": "std.ai.perception.in_sight",
            "nearest": "std.ai.perception.nearest",
            "filter_range": "std.ai.perception.filter_range",
            # v1.4.8: full AI engine
            "model_create": "std.ai.model_create",
            "train": "std.ai.train",
            "predict": "std.ai.predict",
            "model_save": "std.ai.model_save",
            "model_load": "std.ai.model_load",
            "embed": "std.ai.embed",
            "chat": "std.ai.chat",
            "runtime_boot": "std.ai.runtime_boot",
            "runtime_info": "std.ai.runtime_info",
            "session_open": "std.ai.session_open",
            "session_message": "std.ai.session_message",
            "session_history": "std.ai.session_history",
            "prompt_template": "std.ai.prompt_template",
            "vector_search": "std.ai.vector_search",
            "rag_answer": "std.ai.rag_answer",
            "loss_history": "std.ai.loss_history",
            "model_info": "std.ai.model_info",
            "models_list": "std.ai.models_list",
            "api_providers": "std.ai.api_providers",
            "api_configure": "std.ai.api_configure",
            "api_complete": "std.ai.api_complete",
            "api_embed": "std.ai.api_embed",
            "llm_create": "std.ai.llm_create",
            "llm_train": "std.ai.llm_train",
            "llm_generate": "std.ai.llm_generate",
            "llm_tokenize": "std.ai.llm_tokenize",
            "llm_info": "std.ai.llm_info",
            "llm_dataset": "std.ai.llm_dataset",
            "llm_eval": "std.ai.llm_eval",
            "llm_complete": "std.ai.llm_complete",
            "llm_chat": "std.ai.llm_chat",
            "llm_models": "std.ai.llm_models",
            "llm_backends": "std.ai.llm_backends",
            "llm_device_plan": "std.ai.llm_device_plan",
            "llm_tensor": "std.ai.llm_tensor",
            "llm_tensor_batch": "std.ai.llm_tensor_batch",
            "llm_save": "std.ai.llm_save",
            "llm_load": "std.ai.llm_load",
        },
        # v1.4.2: game-oriented stdlib expansion (pure deterministic helpers)
        "game": {
            # easing
            "ease_linear": "std.game.easing.linear",
            "ease_in_quad": "std.game.easing.in_quad",
            "ease_out_quad": "std.game.easing.out_quad",
            "ease_in_out_quad": "std.game.easing.in_out_quad",
            # v1.4.6: more easing
            "ease_in_cubic": "std.game.easing.in_cubic",
            "ease_out_cubic": "std.game.easing.out_cubic",
            "ease_in_out_cubic": "std.game.easing.in_out_cubic",
            "ease_in_back": "std.game.easing.in_back",
            "ease_out_back": "std.game.easing.out_back",
            "ease_out_bounce": "std.game.easing.out_bounce",
            "ease_out_elastic": "std.game.easing.out_elastic",
            # tween helper
            "tween": "std.game.tween.step",
            # grid
            "neighbors4": "std.game.grid.neighbors4",
            "neighbors8": "std.game.grid.neighbors8",
            # path
            "astar": "std.game.path.astar",
            "scene_create": "std.game.scene.create",
            "entity_create": "std.game.entity.create",
            "entity_move": "std.game.entity.move",
            "collide_aabb": "std.game.physics.collide_aabb",
            "anim_frame": "std.game.anim.frame",
        },
    }


@dataclass
class HostFunction:
    name: str
    handler: Callable[[List[Any]], Any]
    cost: int = 1
    # Very light schema: min/max args + (optional) validator
    min_args: int = 0
    max_args: int = 99
    validator: Optional[Callable[[List[Any]], None]] = None

class HostRegistry:
    """Capability bridge registry (เหมือน Lua host functions แต่มี cost/budget)"""
    def __init__(self):
        self._funcs: Dict[str, HostFunction] = {}
        self.runtime_config: Dict[str, Any] = {}

    def register(self, func: HostFunction):
        self._funcs[func.name] = func

    def set_runtime_config(self, config: Dict[str, Any] | None) -> None:
        self.runtime_config = dict(config or {})

    def has(self, name: str) -> bool:
        return name in self._funcs

    def get_cost(self, name: str) -> int:
        return self._funcs[name].cost if name in self._funcs else 0

    def call(self, name: str, args: List[Any]) -> Any:
        if name not in self._funcs:
            raise RuntimeError(f"SANDBOX: unknown syscall '{name}'")
        fn = self._funcs[name]
        if not (fn.min_args <= len(args) <= fn.max_args):
            raise RuntimeError(f"SANDBOX: syscall '{name}' expects {fn.min_args}-{fn.max_args} args, got {len(args)}")
        if fn.validator:
            fn.validator(args)
        return fn.handler(args)

def default_host() -> HostRegistry:
    """Host ตัวอย่าง (ให้รันทดสอบได้ทันที)"""
    h = HostRegistry()
    h.register(HostFunction(
        name="sys.echo",
        handler=lambda a: a[0] if a else None,
        cost=1,
        min_args=0,
        max_args=1
    ))

    # ---------------- Module get/import helper ----------------
    # get("math") -> {"abs": "std.math.abs", ...}
    # Allows dynamic call(module["abs"], x) while still enforcing an allowlist.
    _module_cache: Dict[str, Dict[str, str]] = {}
    _MODULE_ALLOWLIST = MODULE_ALLOWLIST

    def _sys_get(args: List[Any]):
        name = str(args[0]) if args else ""
        name = name.strip().lower()
        if name not in _MODULE_ALLOWLIST:
            raise RuntimeError(f"sys.get: module not allowed: {name}")
        if name in _module_cache:
            return _module_cache[name]
        mod = dict(_MODULE_ALLOWLIST[name])
        _module_cache[name] = mod
        return mod

    h.register(HostFunction('sys.get', _sys_get, cost=1, min_args=1, max_args=1))
    # Example: clamp(number, lo, hi)

    # ----- stdlib (allowlist) -----
    import json as _json
    import math as _math
    from decimal import Decimal as _Decimal, InvalidOperation as _InvalidDecimal, ROUND_HALF_UP as _ROUND_HALF_UP

    def _is_list(x):
        if not isinstance(x, list):
            raise RuntimeError('std.list: expected list')

    def _is_dict(x):
        if not isinstance(x, dict):
            raise RuntimeError('std.map: expected map')

    h.register(HostFunction(
        name='std.list.push',
        handler=lambda a: (a[0].append(a[1]) or a[0]) if (_is_list(a[0]) is None) else a[0],
        cost=1,
        min_args=2,
        max_args=2
    ))
    h.register(HostFunction(
        name='std.list.pop',
        handler=lambda a: (a[0].pop() if (_is_list(a[0]) is None) and a[0] else None),
        cost=1,
        min_args=1,
        max_args=1
    ))
    h.register(HostFunction(
        name='std.list.len',
        handler=lambda a: len(a[0]) if (_is_list(a[0]) is None) else 0,
        cost=1,
        min_args=1,
        max_args=1
    ))

    def _map_get(args):
        m, k = args[0], args[1]
        _is_dict(m)
        if len(args) == 3:
            return m.get(k, args[2])
        return m.get(k)
    h.register(HostFunction('std.map.get', _map_get, cost=1, min_args=2, max_args=3))

    def _map_set(args):
        m, k, v = args[0], args[1], args[2]
        _is_dict(m)
        m[k] = v
        return m
    h.register(HostFunction('std.map.set', _map_set, cost=1, min_args=3, max_args=3))

    def _map_keys(args):
        m=args[0]
        _is_dict(m)
        return list(m.keys())
    h.register(HostFunction('std.map.keys', _map_keys, cost=1, min_args=1, max_args=1))

    h.register(HostFunction('std.string.len', lambda a: len(str(a[0])) if a else 0, cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.len', lambda a: len(a[0]) if isinstance(a[0], (list,dict)) else len(str(a[0])), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.string.lower', lambda a: str(a[0]).lower(), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.string.upper', lambda a: str(a[0]).upper(), cost=1, min_args=1, max_args=1))

    # v1.4.5: std.string.tostr — convert any value to string (used by f-string compiler)
    def _tostr(a):
        if not a: return ""
        v = a[0]
        if v is None: return "none"
        if isinstance(v, bool): return "true" if v else "false"
        if isinstance(v, float) and v == int(v): return str(int(v))
        return str(v)
    h.register(HostFunction('std.string.tostr', _tostr, cost=1, min_args=1, max_args=1))

    # --- std.string extras ---
    h.register(HostFunction('std.string.trim', lambda a: str(a[0]).strip(), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.string.replace', lambda a: str(a[0]).replace(str(a[1]), str(a[2])), cost=1, min_args=3, max_args=3))
    h.register(HostFunction('std.string.find', lambda a: str(a[0]).find(str(a[1])), cost=1, min_args=2, max_args=2))

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

    # ==========================================
    # v1.4.6: AI — Steering Behaviors
    # ==========================================
    # ทุก steering รับ pos=[x,y], target=[x,y], speed=float
    # คืนค่า velocity [vx, vy] ที่ normalize แล้ว * speed

    def _vec2_normalize(vx: float, vy: float, speed: float = 1.0):
        import math as _m
        mag = _m.sqrt(vx * vx + vy * vy)
        if mag < 1e-9:
            return [0.0, 0.0]
        return [vx / mag * speed, vy / mag * speed]

    def _ai_seek(args):
        """ai_seek(pos, target, speed=1) -> [vx, vy]
        เคลื่อนที่หา target ตรงๆ
        """
        pos = args[0]
        target = args[1]
        speed = float(args[2]) if len(args) >= 3 else 1.0
        dx = float(target[0]) - float(pos[0])
        dy = float(target[1]) - float(pos[1])
        return _vec2_normalize(dx, dy, speed)

    def _ai_flee(args):
        """ai_flee(pos, threat, speed=1) -> [vx, vy]
        วิ่งหนีจาก threat
        """
        pos = args[0]
        threat = args[1]
        speed = float(args[2]) if len(args) >= 3 else 1.0
        dx = float(pos[0]) - float(threat[0])
        dy = float(pos[1]) - float(threat[1])
        return _vec2_normalize(dx, dy, speed)

    def _ai_arrive(args):
        """ai_arrive(pos, target, speed=1, slow_radius=50) -> [vx, vy]
        เคลื่อนที่หา target แล้วชะลอเมื่อใกล้ถึง
        """
        import math as _m
        pos = args[0]
        target = args[1]
        speed = float(args[2]) if len(args) >= 3 else 1.0
        slow_radius = float(args[3]) if len(args) >= 4 else 50.0
        dx = float(target[0]) - float(pos[0])
        dy = float(target[1]) - float(pos[1])
        dist = _m.sqrt(dx * dx + dy * dy)
        if dist < 1e-9:
            return [0.0, 0.0]
        effective_speed = speed * min(1.0, dist / slow_radius) if slow_radius > 0 else speed
        return [dx / dist * effective_speed, dy / dist * effective_speed]

    def _ai_wander(args):
        """ai_wander(pos, current_angle, speed=1, jitter=0.3) -> {"vel":[vx,vy], "angle":float}
        เดินเตร่แบบ deterministic (ใช้ sin/cos ของ angle ที่เปลี่ยนไปเรื่อยๆ)
        ต้องเก็บ angle ไว้ใน state แล้วส่งกลับมาทุก tick
        """
        import math as _m
        pos = args[0]
        angle = float(args[1]) if len(args) >= 2 else 0.0
        speed = float(args[2]) if len(args) >= 3 else 1.0
        jitter = float(args[3]) if len(args) >= 4 else 0.3
        # update angle (deterministic — ไม่ใช้ random)
        new_angle = angle + jitter * _m.sin(angle * 1.618)
        vx = _m.cos(new_angle) * speed
        vy = _m.sin(new_angle) * speed
        return {"vel": [vx, vy], "angle": new_angle}

    def _ai_patrol(args):
        """ai_patrol(pos, waypoints, current_idx, speed=1, threshold=5) -> {"vel":[vx,vy], "idx":int}
        순찰: เดินวนระหว่าง waypoints
        """
        import math as _m
        pos = args[0]
        waypoints = args[1]
        idx = int(args[2]) if len(args) >= 3 else 0
        speed = float(args[3]) if len(args) >= 4 else 1.0
        threshold = float(args[4]) if len(args) >= 5 else 5.0

        if not isinstance(waypoints, list) or len(waypoints) == 0:
            return {"vel": [0.0, 0.0], "idx": 0}

        idx = idx % len(waypoints)
        wp = waypoints[idx]
        dx = float(wp[0]) - float(pos[0])
        dy = float(wp[1]) - float(pos[1])
        dist = _m.sqrt(dx * dx + dy * dy)

        if dist < threshold:
            idx = (idx + 1) % len(waypoints)
            wp = waypoints[idx]
            dx = float(wp[0]) - float(pos[0])
            dy = float(wp[1]) - float(pos[1])
            dist = _m.sqrt(dx * dx + dy * dy)

        vel = _vec2_normalize(dx, dy, speed) if dist > 1e-9 else [0.0, 0.0]
        return {"vel": vel, "idx": idx}

    h.register(HostFunction('std.ai.steering.seek', _ai_seek, cost=1, min_args=2, max_args=3))
    h.register(HostFunction('std.ai.steering.flee', _ai_flee, cost=1, min_args=2, max_args=3))
    h.register(HostFunction('std.ai.steering.arrive', _ai_arrive, cost=1, min_args=2, max_args=4))
    h.register(HostFunction('std.ai.steering.wander', _ai_wander, cost=1, min_args=1, max_args=4))
    h.register(HostFunction('std.ai.steering.patrol', _ai_patrol, cost=2, min_args=3, max_args=5))

    # ==========================================
    # v1.4.6: AI — Perception
    # ==========================================

    def _ai_in_range(args):
        """ai_in_range(pos, target, radius) -> bool
        เช็คว่า target อยู่ในระยะ radius หรือไม่
        """
        import math as _m
        pos, target = args[0], args[1]
        radius = float(args[2])
        dx = float(target[0]) - float(pos[0])
        dy = float(target[1]) - float(pos[1])
        return (dx * dx + dy * dy) <= radius * radius

    def _ai_in_sight(args):
        """ai_in_sight(pos, facing_angle, target, fov_degrees=90, max_dist=200) -> bool
        เช็คว่า target อยู่ใน field of view หรือไม่
        facing_angle = องศาที่หัน (0 = ขวา, 90 = ลง)
        fov_degrees = มุมมองรวม เช่น 90 หมายถึง ±45 องศา
        """
        import math as _m
        pos = args[0]
        facing = float(args[1])
        target = args[2]
        fov = float(args[3]) if len(args) >= 4 else 90.0
        max_dist = float(args[4]) if len(args) >= 5 else 200.0

        dx = float(target[0]) - float(pos[0])
        dy = float(target[1]) - float(pos[1])
        dist = _m.sqrt(dx * dx + dy * dy)
        if dist > max_dist or dist < 1e-9:
            return False

        angle_to = _m.degrees(_m.atan2(dy, dx))
        diff = (angle_to - facing + 180) % 360 - 180
        return abs(diff) <= fov / 2.0

    def _ai_nearest(args):
        """ai_nearest(pos, targets) -> target_or_none
        หา target ที่ใกล้ที่สุดจาก list
        targets = list ของ [x, y] หรือ {"pos": [x,y], ...}
        """
        import math as _m
        pos = args[0]
        targets = args[1]
        if not isinstance(targets, list) or len(targets) == 0:
            return None

        def _get_pos(t):
            if isinstance(t, list) and len(t) >= 2:
                return t
            if isinstance(t, dict) and "pos" in t:
                return t["pos"]
            return None

        best = None
        best_dist = float('inf')
        for t in targets:
            tp = _get_pos(t)
            if tp is None:
                continue
            dx = float(tp[0]) - float(pos[0])
            dy = float(tp[1]) - float(pos[1])
            d = dx * dx + dy * dy
            if d < best_dist:
                best_dist = d
                best = t
        return best

    def _ai_filter_range(args):
        """ai_filter_range(pos, targets, radius) -> list
        กรอง targets เหลือเฉพาะที่อยู่ในระยะ radius
        """
        import math as _m
        pos = args[0]
        targets = args[1]
        radius = float(args[2])
        r2 = radius * radius

        def _get_pos(t):
            if isinstance(t, list) and len(t) >= 2:
                return t
            if isinstance(t, dict) and "pos" in t:
                return t["pos"]
            return None

        result = []
        for t in (targets or []):
            tp = _get_pos(t)
            if tp is None:
                continue
            dx = float(tp[0]) - float(pos[0])
            dy = float(tp[1]) - float(pos[1])
            if dx * dx + dy * dy <= r2:
                result.append(t)
        return result

    h.register(HostFunction('std.ai.perception.in_range', _ai_in_range, cost=1, min_args=3, max_args=3))
    h.register(HostFunction('std.ai.perception.in_sight', _ai_in_sight, cost=1, min_args=3, max_args=5))
    h.register(HostFunction('std.ai.perception.nearest', _ai_nearest, cost=2, min_args=2, max_args=2))
    h.register(HostFunction('std.ai.perception.filter_range', _ai_filter_range, cost=2, min_args=3, max_args=3))
    def _str_split(args):
        s = str(args[0])
        sep = None if len(args) < 2 else str(args[1])
        return s.split(sep) if sep is not None else s.split()
    h.register(HostFunction('std.string.split', _str_split, cost=2, min_args=1, max_args=2))
    def _str_join(args):
        arr = args[0]
        if not isinstance(arr, list):
            raise RuntimeError('std.string.join: expected list')
        sep = '' if len(args) < 2 else str(args[1])
        return sep.join(str(x) for x in arr)
    h.register(HostFunction('std.string.join', _str_join, cost=2, min_args=1, max_args=2))

    # --- std.list extras ---
    def _list_insert(args):
        lst, idx, val = args[0], int(args[1]), args[2]
        _is_list(lst)
        if idx < 0: idx = 0
        if idx > len(lst): idx = len(lst)
        lst.insert(idx, val)
        return lst
    h.register(HostFunction('std.list.insert', _list_insert, cost=1, min_args=3, max_args=3))
    def _list_remove(args):
        lst, val = args[0], args[1]
        _is_list(lst)
        try:
            lst.remove(val)
        except ValueError:
            pass
        return lst
    h.register(HostFunction('std.list.remove', _list_remove, cost=1, min_args=2, max_args=2))
    def _list_has(args):
        lst, val = args[0], args[1]
        _is_list(lst)
        return val in lst
    h.register(HostFunction('std.list.has', _list_has, cost=1, min_args=2, max_args=2))
    def _list_sort(args):
        lst = args[0]
        _is_list(lst)
        try:
            lst.sort()
        except Exception:
            # fallback: sort by string value
            lst.sort(key=lambda x: str(x))
        return lst
    h.register(HostFunction('std.list.sort', _list_sort, cost=2, min_args=1, max_args=1))

    # ==========================================================
    # v1.4.7: String helpers
    # ==========================================================
    h.register(HostFunction('std.string.starts_with',
        lambda a: str(a[0]).startswith(str(a[1])), cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.string.ends_with',
        lambda a: str(a[0]).endswith(str(a[1])), cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.string.contains',
        lambda a: str(a[1]) in str(a[0]), cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.string.repeat',
        lambda a: str(a[0]) * max(0, int(a[1])), cost=1, min_args=2, max_args=2))

    def _str_pad_left(args):
        s = str(args[0]); width = int(args[1])
        ch = str(args[2]) if len(args) >= 3 else " "
        return s.rjust(width, ch[0] if ch else " ")
    h.register(HostFunction('std.string.pad_left', _str_pad_left, cost=1, min_args=2, max_args=3))

    def _str_pad_right(args):
        s = str(args[0]); width = int(args[1])
        ch = str(args[2]) if len(args) >= 3 else " "
        return s.ljust(width, ch[0] if ch else " ")
    h.register(HostFunction('std.string.pad_right', _str_pad_right, cost=1, min_args=2, max_args=3))

    def _str_format(args):
        """str_format(template, val1, val2, ...) — ใช้ {} เป็น placeholder"""
        tmpl = str(args[0])
        vals = args[1:]
        try:
            return tmpl.format(*vals)
        except Exception:
            return tmpl
    h.register(HostFunction('std.string.format', _str_format, cost=1, min_args=1, max_args=99))

    # ==========================================================
    # v1.4.7: Math game helpers
    # ==========================================================
    import math as _math

    h.register(HostFunction('std.math.sign',
        lambda a: (1 if float(a[0]) > 0 else (-1 if float(a[0]) < 0 else 0)),
        cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.fmod',
        lambda a: float(a[0]) % float(a[1]), cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.deg_to_rad',
        lambda a: float(a[0]) * _math.pi / 180.0, cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.rad_to_deg',
        lambda a: float(a[0]) * 180.0 / _math.pi, cost=1, min_args=1, max_args=1))

    def _distance(args):
        ax, ay = float(args[0][0]), float(args[0][1])
        bx, by = float(args[1][0]), float(args[1][1])
        return _math.sqrt((bx-ax)**2 + (by-ay)**2)
    h.register(HostFunction('std.math.distance', _distance, cost=1, min_args=2, max_args=2))

    def _angle_between(args):
        ax, ay = float(args[0][0]), float(args[0][1])
        bx, by = float(args[1][0]), float(args[1][1])
        return _math.degrees(_math.atan2(by-ay, bx-ax))
    h.register(HostFunction('std.math.angle_between', _angle_between, cost=1, min_args=2, max_args=2))

    # ==========================================================
    # v1.4.7: List functional helpers
    # ==========================================================

    def _list_map(args):
        """list_map(list, fn_name) -> list ใหม่ที่ผ่าน fn แต่ละ element"""
        lst = args[0]; _is_list(lst)
        fn_name = str(args[1])
        # fn_name ต้องเป็น registered syscall
        return [h.call(fn_name, [item]) for item in lst]
    h.register(HostFunction('std.list.map', _list_map, cost=3, min_args=2, max_args=2))

    def _list_filter(args):
        """list_filter(list, fn_name) -> list เฉพาะ element ที่ fn return truthy"""
        lst = args[0]; _is_list(lst)
        fn_name = str(args[1])
        return [item for item in lst if h.call(fn_name, [item])]
    h.register(HostFunction('std.list.filter', _list_filter, cost=3, min_args=2, max_args=2))

    def _list_find(args):
        """list_find(list, value) -> index หรือ -1"""
        lst = args[0]; _is_list(lst)
        val = args[1]
        try:
            return lst.index(val)
        except ValueError:
            return -1
    h.register(HostFunction('std.list.find', _list_find, cost=1, min_args=2, max_args=2))

    def _list_slice(args):
        """list_slice(list, start, end?) -> sub-list"""
        lst = args[0]; _is_list(lst)
        start = int(args[1])
        end = int(args[2]) if len(args) >= 3 else len(lst)
        return lst[start:end]
    h.register(HostFunction('std.list.slice', _list_slice, cost=1, min_args=2, max_args=3))

    def _list_reverse(args):
        lst = args[0]; _is_list(lst)
        return list(reversed(lst))
    h.register(HostFunction('std.list.reverse', _list_reverse, cost=1, min_args=1, max_args=1))

    def _list_reduce(args):
        """list_reduce(list, fn_name, initial) -> accumulated value"""
        lst = args[0]; _is_list(lst)
        fn_name = str(args[1])
        acc = args[2] if len(args) >= 3 else (lst[0] if lst else None)
        start = 0 if len(args) >= 3 else 1
        for item in lst[start:]:
            acc = h.call(fn_name, [acc, item])
        return acc
    h.register(HostFunction('std.list.reduce', _list_reduce, cost=3, min_args=2, max_args=3))

    def _list_count(args):
        """list_count(list, value) -> count ของ value ใน list"""
        lst = args[0]; _is_list(lst)
        val = args[1]
        return lst.count(val)
    h.register(HostFunction('std.list.count', _list_count, cost=1, min_args=2, max_args=2))

    # ==========================================================
    # v1.4.7: Type checking
    # ==========================================================
    h.register(HostFunction('std.type.is_number',
        lambda a: isinstance(a[0], (int, float)) and not isinstance(a[0], bool),
        cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.type.is_string',
        lambda a: isinstance(a[0], str), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.type.is_bool',
        lambda a: isinstance(a[0], bool), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.type.is_list',
        lambda a: isinstance(a[0], list), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.type.is_map',
        lambda a: isinstance(a[0], dict), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.type.is_none',
        lambda a: a[0] is None, cost=1, min_args=1, max_args=1))

    def _type_of(args):
        v = args[0]
        if isinstance(v, bool): return "bool"
        if isinstance(v, (int, float)): return "number"
        if isinstance(v, str): return "string"
        if isinstance(v, list): return "list"
        if isinstance(v, dict): return "map"
        if v is None: return "none"
        return "unknown"
    h.register(HostFunction('std.type.of', _type_of, cost=1, min_args=1, max_args=1))

    # ==========================================================
    # v1.4.7: assert
    # ==========================================================
    def _assert(args):
        cond = args[0]
        msg = str(args[1]) if len(args) >= 2 else "assertion failed"
        if not cond:
            raise RuntimeError(f"AssertionError: {msg}")
        return True
    h.register(HostFunction('std.assert.check', _assert, cost=1, min_args=1, max_args=2))

    def _assert_eq(args):
        a, b = args[0], args[1]
        msg = str(args[2]) if len(args) >= 3 else f"expected {b!r}, got {a!r}"
        if a != b:
            raise RuntimeError(f"AssertionError: {msg}")
        return True
    h.register(HostFunction('std.assert.eq', _assert_eq, cost=1, min_args=2, max_args=3))

    def _assert_ne(args):
        a, b = args[0], args[1]
        msg = str(args[2]) if len(args) >= 3 else f"expected {a!r} != {b!r}"
        if a == b:
            raise RuntimeError(f"AssertionError: {msg}")
        return True
    h.register(HostFunction('std.assert.ne', _assert_ne, cost=1, min_args=2, max_args=3))

    # ==========================================================
    # v1.4.7: Event System
    # ==========================================================
    # emit() — fire event โดย VM จัดการ dispatch ใน vm/legacy.py
    # register ที่นี่แค่เป็น placeholder สำหรับ static analysis
    # การทำงานจริงถูก intercept ใน VM loop ก่อนถึง host
    h.register(HostFunction('std.event.emit', lambda a: None, cost=1, min_args=1, max_args=99))

    # --- std.map extras ---
    def _map_values(args):
        m=args[0]; _is_dict(m); return list(m.values())
    h.register(HostFunction('std.map.values', _map_values, cost=1, min_args=1, max_args=1))
    def _map_has(args):
        m,k=args[0],args[1]; _is_dict(m); return k in m
    h.register(HostFunction('std.map.has', _map_has, cost=1, min_args=2, max_args=2))

    h.register(HostFunction('std.json.encode', lambda a: _json.dumps(a[0], ensure_ascii=False), cost=2, min_args=1, max_args=1))
    h.register(HostFunction('std.json.decode', lambda a: _json.loads(str(a[0])), cost=2, min_args=1, max_args=1))

    # ----- std.money (Decimal-backed, float-free money helpers) -----
    _MONEY_TYPE = "money"
    _DEFAULT_SCALE = _Decimal("0.01")

    def _money_decimal(value: Any) -> _Decimal:
        if isinstance(value, dict) and value.get("type") == _MONEY_TYPE:
            value = value.get("amount", "0")
        try:
            return _Decimal(str(value))
        except (_InvalidDecimal, ValueError) as exc:
            raise RuntimeError(f"std.money: invalid decimal amount: {value}") from exc

    def _money_currency(value: Any = None) -> str:
        cur = "USD" if value is None else str(value).strip().upper()
        if not cur or len(cur) > 12:
            raise RuntimeError("std.money: invalid currency")
        return cur

    def _money(value: Any, currency: Any = "USD") -> dict[str, str]:
        amount = _money_decimal(value).quantize(_DEFAULT_SCALE, rounding=_ROUND_HALF_UP)
        return {"type": _MONEY_TYPE, "currency": _money_currency(currency), "amount": format(amount, "f")}

    def _as_money(value: Any) -> dict[str, str]:
        if isinstance(value, dict) and value.get("type") == _MONEY_TYPE:
            return _money(value.get("amount", "0"), value.get("currency", "USD"))
        return _money(value)

    def _same_currency(left: dict[str, str], right: dict[str, str]) -> None:
        if left.get("currency") != right.get("currency"):
            raise RuntimeError(f"std.money: currency mismatch {left.get('currency')} != {right.get('currency')}")

    def _money_of(args: List[Any]):
        currency = args[1] if len(args) >= 2 else "USD"
        return _money(args[0], currency)

    def _money_add(args: List[Any]):
        a, b = _as_money(args[0]), _as_money(args[1])
        _same_currency(a, b)
        return _money(_money_decimal(a) + _money_decimal(b), a["currency"])

    def _money_sub(args: List[Any]):
        a, b = _as_money(args[0]), _as_money(args[1])
        _same_currency(a, b)
        return _money(_money_decimal(a) - _money_decimal(b), a["currency"])

    def _money_mul(args: List[Any]):
        a = _as_money(args[0])
        return _money(_money_decimal(a) * _money_decimal(args[1]), a["currency"])

    def _money_div(args: List[Any]):
        a = _as_money(args[0])
        divisor = _money_decimal(args[1])
        if divisor == 0:
            raise RuntimeError("std.money: division by zero")
        return _money(_money_decimal(a) / divisor, a["currency"])

    def _money_quantize(args: List[Any]):
        a = _as_money(args[0])
        scale = _Decimal(str(args[1] if len(args) >= 2 else "0.01"))
        rounded = _money_decimal(a).quantize(scale, rounding=_ROUND_HALF_UP)
        return {"type": _MONEY_TYPE, "currency": a["currency"], "amount": format(rounded, "f")}

    def _money_format(args: List[Any]):
        a = _as_money(args[0])
        return f"{a['currency']} {a['amount']}"

    h.register(HostFunction('std.money.of', _money_of, cost=1, min_args=1, max_args=2))
    h.register(HostFunction('std.money.add', _money_add, cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.money.sub', _money_sub, cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.money.mul', _money_mul, cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.money.div', _money_div, cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.money.quantize', _money_quantize, cost=1, min_args=1, max_args=2))
    h.register(HostFunction('std.money.format', _money_format, cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.money.amount', lambda a: _as_money(a[0])["amount"], cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.money.currency', lambda a: _as_money(a[0])["currency"], cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.money.eq', lambda a: (_same_currency(_as_money(a[0]), _as_money(a[1])) is None) and _money_decimal(a[0]) == _money_decimal(a[1]), cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.money.lt', lambda a: (_same_currency(_as_money(a[0]), _as_money(a[1])) is None) and _money_decimal(a[0]) < _money_decimal(a[1]), cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.money.gt', lambda a: (_same_currency(_as_money(a[0]), _as_money(a[1])) is None) and _money_decimal(a[0]) > _money_decimal(a[1]), cost=1, min_args=2, max_args=2))
    from ..ledger_core import register_ledger_functions
    register_ledger_functions(h)
    from ..interop_core import register_interop_functions
    register_interop_functions(h)
    def _clamp(args):
        x, lo, hi = float(args[0]), float(args[1]), float(args[2])
        return max(lo, min(hi, x))
    h.register(HostFunction(
        name="math.clamp",
        handler=_clamp,
        cost=1,
        min_args=3,
        max_args=3
    ))

    
    # ----- std.math (advanced) -----
    import math as _math
    h.register(HostFunction('std.math.abs', lambda a: abs(float(a[0])), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.min', lambda a: float(a[0]) if float(a[0]) < float(a[1]) else float(a[1]), cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.max', lambda a: float(a[0]) if float(a[0]) > float(a[1]) else float(a[1]), cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.floor', lambda a: _math.floor(float(a[0])), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.ceil', lambda a: _math.ceil(float(a[0])), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.round', lambda a: round(float(a[0])), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.sqrt', lambda a: _math.sqrt(float(a[0])), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.pow', lambda a: _math.pow(float(a[0]), float(a[1])), cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.sin', lambda a: _math.sin(float(a[0])), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.cos', lambda a: _math.cos(float(a[0])), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.tan', lambda a: _math.tan(float(a[0])), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.atan2', lambda a: _math.atan2(float(a[0]), float(a[1])), cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.pi', lambda a: _math.pi, cost=1, min_args=0, max_args=0))
    h.register(HostFunction('std.math.clamp', _clamp, cost=1, min_args=3, max_args=3))
    def _lerp(args):
        a0, a1, t = float(args[0]), float(args[1]), float(args[2])
        return a0 + (a1 - a0) * t
    h.register(HostFunction('std.math.lerp', _lerp, cost=1, min_args=3, max_args=3))

    # ----- std.math (vectors) -----
    # Representation: vectors are plain python lists [x,y,...]
    # Design goals (MellowLang identity):
    #  - fast in VM hot loops
    #  - works for multiple domains (2D/3D/ND) without adding OOP/metatables
    #  - predictable errors
    _VEC_MIN_DIM = 2
    _VEC_MAX_DIM = 16

    def _expect_vec(v) -> int:
        if not isinstance(v, list):
            raise RuntimeError('std.math.vec: expected vector list')
        n = len(v)
        if n < _VEC_MIN_DIM or n > _VEC_MAX_DIM:
            raise RuntimeError(f'std.math.vec: dimension must be {_VEC_MIN_DIM}-{_VEC_MAX_DIM} (got {n})')
        return n

    def _vector(args):
        """Generic vector constructor.

        Supported:
          - vector(x, y, ...) / vec(x, y, ...)  (dimension inferred from arg count)
          - vector(dim, x, y, ...)             (explicit dim, must match values count)
          - vector(existing_vec)               (copy)
        """
        if len(args) == 1 and isinstance(args[0], list):
            v = args[0]
            n = _expect_vec(v)
            return [float(v[i]) for i in range(n)]

        if len(args) >= 3 and isinstance(args[0], (int, float)):
            dim = int(args[0])
            # explicit dim form only if it matches remaining values
            if dim >= _VEC_MIN_DIM and dim <= _VEC_MAX_DIM and (len(args) - 1) == dim:
                vals = args[1:]
                return [float(x) for x in vals]

        # inferred dimension
        if len(args) < _VEC_MIN_DIM:
            raise RuntimeError(f'std.math.vector: expected at least {_VEC_MIN_DIM} numbers')
        if len(args) > _VEC_MAX_DIM:
            raise RuntimeError(f'std.math.vector: too many components (max {_VEC_MAX_DIM})')
        return [float(x) for x in args]

    def _vec2(args):
        return [float(args[0]), float(args[1])]

    def _vec3(args):
        return [float(args[0]), float(args[1]), float(args[2])]

    def _vec_add(args):
        a, b = args[0], args[1]
        n = _expect_vec(a)
        if _expect_vec(b) != n:
            raise RuntimeError('std.math.vec_add: dimension mismatch')
        return [float(a[i]) + float(b[i]) for i in range(n)]

    def _vec_sub(args):
        a, b = args[0], args[1]
        n = _expect_vec(a)
        if _expect_vec(b) != n:
            raise RuntimeError('std.math.vec_sub: dimension mismatch')
        return [float(a[i]) - float(b[i]) for i in range(n)]

    def _vec_mul(args):
        a, s = args[0], float(args[1])
        n = _expect_vec(a)
        return [float(a[i]) * s for i in range(n)]

    def _vec_dot(args):
        a, b = args[0], args[1]
        n = _expect_vec(a)
        if _expect_vec(b) != n:
            raise RuntimeError('std.math.vec_dot: dimension mismatch')
        return sum(float(a[i]) * float(b[i]) for i in range(n))

    def _vec_len(args):
        a = args[0]
        n = _expect_vec(a)
        return _math.sqrt(sum(float(a[i]) * float(a[i]) for i in range(n)))

    def _vec_norm(args):
        a = args[0]
        n = _expect_vec(a)
        l = _math.sqrt(sum(float(a[i]) * float(a[i]) for i in range(n)))
        if l == 0:
            return [0.0 for _ in range(n)]
        return [float(a[i]) / l for i in range(n)]

    def _vec_dist(args):
        a, b = args[0], args[1]
        n = _expect_vec(a)
        if _expect_vec(b) != n:
            raise RuntimeError('std.math.vec_dist: dimension mismatch')
        return _math.sqrt(sum((float(a[i]) - float(b[i]))**2 for i in range(n)))

    def _vec_dim(args):
        return _expect_vec(args[0])

    def _vec_axis(args):
        v, idx = args[0], args[1]
        n = _expect_vec(v)
        try:
            i = int(idx)
        except Exception:
            raise RuntimeError('std.math.vec_axis: index must be int')
        if i < 0 or i >= n:
            raise RuntimeError(f'std.math.vec_axis: index out of range (0..{n-1}, got {i})')
        return float(v[i])

    def _vec_lerp(args):
        a, b, t = args[0], args[1], float(args[2])
        n = _expect_vec(a)
        if _expect_vec(b) != n:
            raise RuntimeError('std.math.vec_lerp: dimension mismatch')
        return [float(a[i]) + (float(b[i]) - float(a[i])) * t for i in range(n)]

    def _vec_limit(args):
        v, max_len = args[0], float(args[1])
        n = _expect_vec(v)
        if max_len < 0:
            max_len = 0.0
        l = _math.sqrt(sum(float(v[i]) * float(v[i]) for i in range(n)))
        if l == 0 or l <= max_len:
            return [float(v[i]) for i in range(n)]
        s = max_len / l
        return [float(v[i]) * s for i in range(n)]

    # register
    h.register(HostFunction('std.math.vector', _vector, cost=1, min_args=1, max_args=_VEC_MAX_DIM+1))
    h.register(HostFunction('std.math.vec2', _vec2, cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.vec3', _vec3, cost=1, min_args=3, max_args=3))
    h.register(HostFunction('std.math.vec_add', _vec_add, cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.vec_sub', _vec_sub, cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.vec_mul', _vec_mul, cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.vec_dot', _vec_dot, cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.vec_len', _vec_len, cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.vec_norm', _vec_norm, cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.vec_dist', _vec_dist, cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.vec_dim', _vec_dim, cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.vec_axis', _vec_axis, cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.vec_lerp', _vec_lerp, cost=1, min_args=3, max_args=3))
    h.register(HostFunction('std.math.vec_limit', _vec_limit, cost=1, min_args=2, max_args=2))

    # ----- std.time (advanced) -----
    import time as _time
    h.register(HostFunction('std.time.unix', lambda a: _time.time(), cost=1, min_args=0, max_args=0))
    h.register(HostFunction('std.time.ms', lambda a: int(_time.time() * 1000), cost=1, min_args=0, max_args=0))
    # Note: std.time.now is monotonic since host start; not guaranteed deterministic unless replayed
    start = _time.perf_counter()
    h.register(HostFunction('std.time.now', lambda a: _time.perf_counter() - start, cost=1, min_args=0, max_args=0))

# range (Python-like): std.range(end) or std.range(start, end, step)
    def _std_range(args):
        # returns an iterator-like view (no list allocation)
        if len(args) == 1:
            start, end, step = 0, int(args[0]), 1
        elif len(args) == 2:
            start, end, step = int(args[0]), int(args[1]), 1
        elif len(args) == 3:
            start, end, step = int(args[0]), int(args[1]), int(args[2])
        else:
            raise RuntimeError('std.range: expected 1-3 args')
        if step == 0:
            raise RuntimeError('std.range: step cannot be 0')
        return MellowLangRange(start, end, step)

    h.register(HostFunction(
        name='std.range',
        handler=_std_range,
        cost=1,
        min_args=1,
        max_args=3
    ))
    h.register(HostFunction(
        name='range',
        handler=_std_range,
        cost=1,
        min_args=1,
        max_args=3
    ))

    # ----- v1.4.8: AI Engine -----
    try:
        from ..ai_core import register_ai_functions
        register_ai_functions(h)
    except Exception:
        pass  # AI core optional

    # ----- v1.4.9: General Programming Additions -----

    # enumerate: returns [[0,v0],[1,v1],...]
    def _enumerate(a):
        lst = a[0] if a else []
        if not isinstance(lst, (list, str)):
            return []
        return [[i, v] for i, v in enumerate(lst)]
    h.register(HostFunction('std.list.enumerate', _enumerate, cost=2, min_args=1, max_args=1))

    # zip: zip two or more lists into list of pairs
    def _zip(a):
        if len(a) < 2:
            return []
        return [[row[i] for row in a] for i in range(min(len(r) for r in a))]
    h.register(HostFunction('std.list.zip', _zip, cost=2, min_args=2, max_args=10))

    # map_fn: map(fn_ref, list) → [fn(x) for x in list]  — fn_ref is a ("__func__", name) tuple
    # Handled specially in VM's SYSCALL dispatch (needs func_table access)
    h.register(HostFunction('std.list.map_fn', lambda a: a, cost=1, min_args=2, max_args=2))  # stub, VM intercepts

    # filter_fn: filter(fn_ref, list)
    h.register(HostFunction('std.list.filter_fn', lambda a: a, cost=1, min_args=2, max_args=2))  # stub

    # sorted: sorted(list, reverse=False)
    def _sorted(a):
        lst = list(a[0]) if isinstance(a[0], list) else []
        rev = bool(a[1]) if len(a) > 1 else False
        try: return sorted(lst, reverse=rev)
        except: return lst
    h.register(HostFunction('std.list.sorted', _sorted, cost=2, min_args=1, max_args=2))

    # reversed: reversed(list)
    def _reversed(a):
        lst = list(a[0]) if isinstance(a[0], list) else []
        return lst[::-1]
    h.register(HostFunction('std.list.reversed', _reversed, cost=2, min_args=1, max_args=1))

    # any/all
    def _mellow_any(a):
        lst = a[0] if isinstance(a[0], list) else []
        return any(bool(x) for x in lst)
    def _mellow_all(a):
        lst = a[0] if isinstance(a[0], list) else []
        return all(bool(x) for x in lst)
    h.register(HostFunction('std.list.any', _mellow_any, cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.list.all', _mellow_all, cost=1, min_args=1, max_args=1))

    # sum
    def _sum(a):
        lst = a[0] if isinstance(a[0], list) else []
        try: return sum(float(x) if isinstance(x, float) else int(x) for x in lst)
        except: return 0
    h.register(HostFunction('std.math.sum', _sum, cost=2, min_args=1, max_args=1))

    # type conversions
    def _to_int(a): 
        try: return int(float(a[0])) if a else 0
        except: return 0
    def _to_float(a):
        try: return float(a[0]) if a else 0.0
        except: return 0.0
    def _to_str(a):
        v = a[0] if a else None
        if v is None: return "none"
        if isinstance(v, bool): return "true" if v else "false"
        if isinstance(v, float) and v == int(v): return str(int(v))
        return str(v)
    def _to_bool(a):
        v = a[0] if a else None
        if isinstance(v, bool): return v
        if isinstance(v, (int, float)): return v != 0
        if isinstance(v, str): return v.lower() not in ('', '0', 'false', 'none')
        return v is not None
    def _to_list(a):
        v = a[0] if a else None
        if isinstance(v, list): return v
        if isinstance(v, str): return list(v)
        if isinstance(v, dict): return list(v.keys())
        return [v] if v is not None else []

    h.register(HostFunction('std.type.to_int', _to_int, cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.type.to_float', _to_float, cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.type.to_str', _to_str, cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.type.to_bool', _to_bool, cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.type.to_list', _to_list, cost=1, min_args=1, max_args=1))

    # chr/ord
    h.register(HostFunction('std.string.chr', lambda a: chr(int(a[0])) if a else '', cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.string.ord', lambda a: ord(str(a[0])[0]) if a and str(a[0]) else 0, cost=1, min_args=1, max_args=1))

    # list extend helpers for spread builds
    def _list_extend(a):
        base = list(a[0]) if isinstance(a[0], list) else []
        ext = a[1] if len(a) > 1 else []
        if isinstance(ext, (list, str)):
            return base + list(ext)
        return base
    def _list_append_to_top(a):
        base = list(a[0]) if isinstance(a[0], list) else []
        item = a[1] if len(a) > 1 else None
        return base + [item]
    h.register(HostFunction('std.list._extend', _list_extend, cost=2, min_args=2, max_args=2))
    h.register(HostFunction('std.list._append_to_top', _list_append_to_top, cost=1, min_args=2, max_args=2))

    return h
