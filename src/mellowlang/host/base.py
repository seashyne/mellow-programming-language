"""Host capability types and the public module allowlist."""
from __future__ import annotations
from dataclasses import dataclass
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
        "chat": {
            "completions_create": "std.sdk.chat_completions_create",
        },
        "sdk": {
            "openai_client": "std.sdk.openai_client",
            "openai_preset_client": "std.sdk.openai_preset_client",
            "deepseek_client": "std.sdk.deepseek_client",
            "openai_chat": "std.sdk.openai_chat",
            "chat_completions_create": "std.sdk.chat_completions_create",
            "describe": "std.sdk.describe",
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
