"""The interpreter state: bytecode, operand stack, scope stack, config and limits."""

from __future__ import annotations

from ...data_core import DataStreamManager
from ...host import HostRegistry, default_host
from ...replay import ReplayConfig, ReplayLog
from typing import Any, List


class FrameMixin:
    def __init__(self, bytecode, func_table=None, event_table=None, *, config=None, host: HostRegistry | None = None, replay: ReplayConfig | None = None, filename: str | None = None, source_lines: list[str] | None = None, line_map: list[int] | None = None, col_map: list[int] | None = None, end_line_map: list[int] | None = None, end_col_map: list[int] | None = None, span_map: list[dict] | None = None):
        self.bytecode = bytecode or []
        self.func_table = func_table or {}
        self.event_table = event_table or {}  # event_name -> meta

        self.stack: List[Any] = []
        self.call_stack: List[int] = []
        self.frame_stack: List[dict] = []  # function/event frames for trace
        self.variables = [{}]  # scope stack (0 = global)

        self.pc = 0
        self.precision = None

        # Debug info for pretty errors
        self.filename = filename
        self.source_lines = source_lines or []
        self._line_map = line_map or []
        self._col_map = col_map or []
        self._end_line_map = end_line_map or []
        self._end_col_map = end_col_map or []
        self._span_map = span_map or []
        self._try_stack: list[dict] = []  # stack of try frames

        self.config = {
            # Permissions
            "allow_ask": False,
            "allow_wait": True,
            "allow_storage": True,

            # Limits
            "max_steps": 200_000,
            "max_stack": 2_000,
            "max_string_len": 20_000,
            "max_list_len": 5_000,
            "max_map_keys": 2_000,
            "data_max_batch_size": 1_000,
            "data_max_open_streams": 8,
            "data_max_record_bytes": 1_048_576,
            "data_max_query_rows": 5_000,
            "allow_data_write": False,

            # Budget for syscalls (anti-spam)
            "syscall_budget": 500,
        }
        if config:
            self.config.update(config)

        # ---------------- Project mode (v1.4.5 standard) ----------------
        # In project mode, storage is locked under <project_root>/<sandbox_root>.
        # Host filesystem operations via fs_* are deny-by-default unless allowlisted.
        import os as _os
        if bool(self.config.get('project_mode', False)):
            pr = self.config.get('project_root') or _os.getcwd()
            sr = self.config.get('sandbox_root') or 'saves'
            pr = _os.path.abspath(str(pr))
            sr = str(sr).strip().strip('"').strip("'").replace('\\', '/')
            if not sr:
                sr = 'saves'
            # Default storage dir is the sandbox root
            base = self.config.get('storage_dir')
            if base is None or str(base).strip() in ('', '.', 'mellow_saves', 'saves'):
                self.config['storage_dir'] = _os.path.join(pr, sr)
            else:
                # Treat provided storage_dir as a namespace under sandbox_root
                raw = str(base).strip().strip('"').strip("'")
                raw = raw.replace('\\', '/').lstrip('/')
                self.config['storage_dir'] = _os.path.join(pr, sr, raw)
            self.config['project_root'] = pr
            self.config['sandbox_root'] = sr

        self.host = host or default_host()
        self._steps = 0
        self._budget = int(self.config.get("syscall_budget", 500))

        # ---------------- Debugger (v1.2.0) ----------------
        import sys as _sys
        self._dbg_trace = bool(self.config.get("debug_trace", False))
        self._dbg_step = bool(self.config.get("debug_step", False))
        self._dbg_interactive = bool(self._dbg_step) and bool(_sys.stdin.isatty()) and bool(_sys.stdout.isatty())
        self._dbg_watch = [x.strip() for x in str(self.config.get("debug_watch", "")).split(",") if x.strip()]
        self._dbg_break = self._parse_break_lines(str(self.config.get("debug_break_lines", "")))
        self._dbg_break_instrs = self._parse_break_lines(str(self.config.get("debug_break_instrs", "")))
        self._dbg_break_opcodes = {x.strip().upper() for x in str(self.config.get("debug_break_opcodes", "")).split(",") if x.strip()}
        self._dbg_pause_on_start = bool(self.config.get("debug_pause_on_start", False))
        self._dbg_break_when = [x.strip() for x in str(self.config.get("debug_break_when", "")).split(";") if x.strip()]
        self._dbg_watch_exprs = [x.strip() for x in str(self.config.get("debug_watch_exprs", "")).split(";") if x.strip()]
        self._dbg_runtime_enabled = bool(self._dbg_trace or self._dbg_step or self._dbg_break or self._dbg_break_instrs or self._dbg_break_opcodes or self._dbg_pause_on_start or self._dbg_break_when or self._dbg_watch_exprs)
        self._dbg_skip_pause_once = False
        self._dbg_step_plan = None
        self._dbg_step_depth = 0
        self._dbg_started = False
        self._dbg_paused = False
        self._dbg_history = []
        self._dbg_last_stop = None
        self._halted = False
        self._last_result = None

        # AI decision timeline (v1.2.0)
        self._ai_trace = bool(self.config.get("ai_trace", False))
        self._ai_timeline_path = self.config.get("ai_timeline")
        self._ai_events: list[dict] = []

        # Deterministic RNG + Replay
        import random as _random
        import time as _time
        import hashlib as _hashlib

        self._replay = ReplayLog(replay or ReplayConfig())
        self._t0 = _time.monotonic()
        self._profile = bool(self.config.get('profile', False))
        self._opcounts = {}  # opcode -> count
        self._data = DataStreamManager(
            resolve_read=lambda path: self._fs_resolve(path, op="read"),
            resolve_write=lambda path: self._fs_resolve(path, op="write"),
            check_cancelled=self._check_data_cancelled,
            max_batch_size=int(self.config.get("data_max_batch_size", 1_000)),
            max_open_streams=int(self.config.get("data_max_open_streams", 8)),
            max_record_bytes=int(self.config.get("data_max_record_bytes", 1_048_576)),
            max_query_rows=int(self.config.get("data_max_query_rows", 5_000)),
            allow_write=bool(self.config.get("allow_data_write", False)),
        )

        # Global base seed (optional): used to derive per-script seeds deterministically.
        # This keeps MellowLang identity: deterministic-by-default + sandboxed (no external entropy).
        self._global_seed = None
        if "global_seed" in self.config:
            try:
                self._global_seed = int(self.config.get("global_seed"))
            except Exception:
                self._global_seed = None
        else:
            # NOTE(v3.6.1): do not load global seed from disk implicitly
            self._global_seed = None

        def _derive_seed(base: int, name: str) -> int:
            payload = f"{int(base)}::{name}".encode("utf-8")
            digest = _hashlib.sha256(payload).digest()
            return int.from_bytes(digest[:8], "little", signed=False)

        if (replay or ReplayConfig()).mode == "replay":
            seed = int(self._replay.next_seed())
        else:
            if self._global_seed is not None:
                seed = _derive_seed(int(self._global_seed), str(self.filename or "<memory>"))
            else:
                seed = int(self.config.get("seed", 12345))
            self._replay.record_seed(seed)

        self.rng = _random.Random(seed)

        # ---------------- Persistent keep store ----------------
        # keep vars survive across runs by default (can be disabled via config)
        self._keep_dirty = False
        self._keep_enabled = bool(self.config.get("allow_storage", True)) and bool(self.config.get("keep_persistent", True))
        self._keep_values: dict[str, Any] = {}
        if self._keep_enabled:
            try:
                # isolate by filename (script) to avoid collisions
                key = (self.filename or "<memory>")
                data = self._load_json(f"__keep__{key}")
                if isinstance(data, dict):
                    self._keep_values = data
            except Exception:
                # keep is best-effort; never break sandbox on load
                self._keep_values = {}

        self._native_foundation_stats = {
            "collections": 0,
            "spawned": 0,
            "yielded": 0,
            "channels": 0,
        }

    def _tick(self):
        self._steps += 1
        if self._steps > int(self.config.get("max_steps", 200_000)):
            self._raise_sandbox("Step limit exceeded")
        max_ms = self.config.get('max_ms', None)
        if max_ms is not None:
            import time as _time
            if (_time.monotonic() - self._t0) * 1000.0 > float(max_ms):
                self._raise_sandbox('Time limit exceeded')
        if len(self.stack) > int(self.config.get("max_stack", 2_000)):
            self._raise_sandbox("Stack limit exceeded")

    def _check_data_cancelled(self):
        max_ms = self.config.get("max_ms", None)
        if max_ms is not None:
            import time as _time
            if (_time.monotonic() - self._t0) * 1000.0 > float(max_ms):
                self._raise_sandbox("Time limit exceeded")

    def _enforce_value_limits(self, v):
        ms = int(self.config.get("max_string_len", 20_000))
        ml = int(self.config.get("max_list_len", 5_000))
        mk = int(self.config.get("max_map_keys", 2_000))
        if isinstance(v, str) and len(v) > ms:
            self._raise_sandbox("String too large")
        if isinstance(v, list) and len(v) > ml:
            self._raise_sandbox("List too large")
        if isinstance(v, dict) and len(v) > mk:
            self._raise_sandbox("Map too large")

    # ---------------- Utilities ----------------
    def format_value(self, val):
        if isinstance(val, dict) and val.get("type") == "money":
            return f"{val.get('currency', 'USD')} {val.get('amount', '0.00')}"
        if isinstance(val, (float, int)):
            if self.precision is not None:
                try:
                    return f"{float(val):.{int(self.precision)}f}"
                except:
                    pass
            if isinstance(val, float) and val.is_integer():
                return str(int(val))
            return str(val)
        return str(val)

    def _load_var(self, name):
        for scope in reversed(self.variables):
            if name in scope:
                return scope[name]
        if self._keep_enabled and name in self._keep_values:
            return self._keep_values.get(name)
        return 0

    def _truthy(self, v) -> bool:
        return bool(v)

    def _sub_vm(self, *args, **kwargs):
        """Build the nested VM for a skill call or an IMPORT.

        The two sites that used to write `MellowLangVM(...)` cannot name the
        assembled class from inside interp/ without an import cycle, and
        `type(self)` is that class for every instance the product builds.
        """
        return type(self)(*args, **kwargs)
