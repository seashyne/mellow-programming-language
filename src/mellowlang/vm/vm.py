from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Any, Dict

from ..replay import ReplayConfig
from ..host import HostRegistry, default_host
from .legacy import MellowLangVM as _LegacyVM
from .cbridge import run_bytecode_ex, CVMUnsupportedOpcode, NativeExecutionRequiredError, c_vm_capabilities, c_vm_debug_supported
from ..compiler import Compiler as _LegacyCompiler
from ..compiler.compiler import CompiledProgram
from ..error_core import MellowLangRuntimeError

@dataclass(frozen=True)
class RunConfig:
    seed: Optional[int] = None
    global_seed: Optional[int] = None
    record_path: Optional[str] = None
    replay_path: Optional[str] = None

    # Engine selection: auto (prefer C if available), py, c
    engine: str = "auto"
    native_allow_fallback: bool = True
    native_require: bool = False

    # Permissions
    allow_ask: bool = False
    allow_wait: bool = True
    allow_storage: bool = True
    # Secure save system (v1.3.4)
    allow_save: bool = True
    save_slots_max: Optional[int] = None
    save_bytes_max: Optional[int] = None
    storage_dir: Optional[str] = None
    # Unsafe filesystem tweaks (default False):
    # - allow scripts to set storage_dir to absolute paths
    # - allow '..' traversal in storage_dir
    allow_unsafe_fs: bool = False

    # Project mode (v1.3.x)
    # If enabled, storage is locked under <project_root>/<sandbox_root>.
    # Host filesystem access via fs_* built-ins is deny-by-default unless allowlisted.
    project_mode: bool = False
    project_root: Optional[str] = None
    sandbox_root: Optional[str] = None
    fs_read_allow: Optional[str] = None   # comma-separated allowlist roots (relative to project root)
    fs_write_allow: Optional[str] = None  # comma-separated allowlist roots (relative to project root)

    # Networking (v1.3.5)
    # Deny-by-default in project mode unless allowlisted.
    allow_net: bool = False
    net_http_allow: Optional[str] = None  # comma-separated allowlist prefixes (e.g. https://api.game.com/)
    net_ws_allow: Optional[str] = None    # comma-separated allowlist prefixes (e.g. wss://ws.game.com/)
    net_max_bytes: Optional[int] = None   # max payload/response bytes
    net_timeout_s: Optional[float] = None

    # Limits / budgets (sandbox)
    max_steps: Optional[int] = None
    max_ms: Optional[int] = None
    syscall_budget: Optional[int] = None

    # Diagnostics
    profile: bool = False

    # Debugger (v1.2.0)
    trace: bool = False                 # print executed lines
    step: bool = False                  # interactive stepper (TTY only)
    break_lines: Optional[str] = None   # e.g. "12,20-25"
    watch: Optional[str] = None         # e.g. "hp,pos,target"
    ai_timeline: Optional[str] = None   # write AI decision timeline (.jsonl)
    debug_pause_on_start: bool = False
    debug_break_instrs: Optional[str] = None
    debug_break_opcodes: Optional[str] = None
    debug_break_when: Optional[str] = None
    debug_watch_exprs: Optional[str] = None

class MellowVM:
    """Stable VM facade.

    Contract:
      - run(program, config=RunConfig(...), host=None) -> Any
    """
    def __init__(self, *, host: HostRegistry | None = None) -> None:
        self._host = host or default_host()
        self.last_debug_stop = None
        self.last_engine = "auto"
        self.last_engine_detail = ""
        self.last_debug_capabilities = {}
        self.last_native_result = {}

    def run(self, program: CompiledProgram, *, config: RunConfig | None = None) -> Any:
        cfg = config or RunConfig()
        config_dict: Dict[str, Any] = {
            "allow_ask": bool(cfg.allow_ask),
            "allow_wait": bool(cfg.allow_wait),
            "allow_storage": bool(cfg.allow_storage),
            "allow_save": bool(getattr(cfg, 'allow_save', True)),
            "allow_net": bool(getattr(cfg, 'allow_net', False)),
            "allow_unsafe_fs": bool(cfg.allow_unsafe_fs),
            "project_mode": bool(getattr(cfg, 'project_mode', False)),
        }

        if getattr(cfg, 'save_slots_max', None) is not None:
            config_dict['save_slots_max'] = int(getattr(cfg, 'save_slots_max'))
        if getattr(cfg, 'save_bytes_max', None) is not None:
            config_dict['save_bytes_max'] = int(getattr(cfg, 'save_bytes_max'))
        if cfg.seed is not None:
            config_dict["seed"] = int(cfg.seed)
        if cfg.global_seed is not None:
            config_dict["global_seed"] = int(cfg.global_seed)

        if cfg.storage_dir:
            config_dict["storage_dir"] = str(cfg.storage_dir)

        # Project mode fields
        if getattr(cfg, 'project_root', None):
            config_dict['project_root'] = str(getattr(cfg, 'project_root'))
        if getattr(cfg, 'sandbox_root', None):
            config_dict['sandbox_root'] = str(getattr(cfg, 'sandbox_root'))
        if getattr(cfg, 'fs_read_allow', None):
            config_dict['fs_read_allow'] = str(getattr(cfg, 'fs_read_allow'))
        if getattr(cfg, 'fs_write_allow', None):
            config_dict['fs_write_allow'] = str(getattr(cfg, 'fs_write_allow'))

        # Networking allowlists
        if getattr(cfg, 'net_http_allow', None):
            config_dict['net_http_allow'] = str(getattr(cfg, 'net_http_allow'))
        if getattr(cfg, 'net_ws_allow', None):
            config_dict['net_ws_allow'] = str(getattr(cfg, 'net_ws_allow'))
        if getattr(cfg, 'net_max_bytes', None) is not None:
            config_dict['net_max_bytes'] = int(getattr(cfg, 'net_max_bytes'))
        if getattr(cfg, 'net_timeout_s', None) is not None:
            config_dict['net_timeout_s'] = float(getattr(cfg, 'net_timeout_s'))

        if cfg.max_steps is not None:
            config_dict["max_steps"] = int(cfg.max_steps)
        if cfg.max_ms is not None:
            config_dict["max_ms"] = int(cfg.max_ms)
        if cfg.syscall_budget is not None:
            config_dict["syscall_budget"] = int(cfg.syscall_budget)
        if cfg.profile:
            config_dict["profile"] = True

        # Debugger
        if cfg.trace:
            config_dict["debug_trace"] = True
        if cfg.step:
            config_dict["debug_step"] = True
        if cfg.break_lines:
            config_dict["debug_break_lines"] = str(cfg.break_lines)
        if cfg.watch:
            config_dict["debug_watch"] = str(cfg.watch)
        if cfg.ai_timeline:
            config_dict["ai_timeline"] = str(cfg.ai_timeline)
            config_dict["ai_trace"] = True
        if getattr(cfg, 'debug_pause_on_start', False):
            config_dict['debug_pause_on_start'] = True
        if getattr(cfg, 'debug_break_instrs', None):
            config_dict['debug_break_instrs'] = str(getattr(cfg, 'debug_break_instrs'))
        if getattr(cfg, 'debug_break_opcodes', None):
            config_dict['debug_break_opcodes'] = str(getattr(cfg, 'debug_break_opcodes'))
        if getattr(cfg, 'debug_break_when', None):
            config_dict['debug_break_when'] = str(getattr(cfg, 'debug_break_when'))
        if getattr(cfg, 'debug_watch_exprs', None):
            config_dict['debug_watch_exprs'] = str(getattr(cfg, 'debug_watch_exprs'))

        replay = None
        if cfg.record_path:
            replay = ReplayConfig(mode="record", path=str(cfg.record_path))
        elif cfg.replay_path:
            replay = ReplayConfig(mode="replay", path=str(cfg.replay_path))

        engine = getattr(cfg, "engine", "auto") or "auto"
        native_allow_fallback = bool(getattr(cfg, "native_allow_fallback", True))
        native_require = bool(getattr(cfg, "native_require", False))
        engine = str(engine).lower().strip()
        if engine not in ("auto", "py", "c"):
            engine = "auto"

        # v1.3.0: deterministic record/replay is guaranteed on the legacy Python VM.
        # (C VM replay parity will be completed in a later release.)
        if (cfg.record_path or cfg.replay_path) and engine in ("auto", "c"):
            if native_require or not native_allow_fallback:
                raise MellowLangRuntimeError("NATIVE_REQUIRED", "record/replay still routes through the Python VM in v2.4.0")
            engine = "py"

        # v1.4.7: force Python VM when script uses event handlers
        # (C VM does not support on()/emit() dispatch yet)
        if getattr(program, "event_table", None):
            if native_require or not native_allow_fallback:
                raise MellowLangRuntimeError("NATIVE_REQUIRED", "event handlers still require the Python VM in v2.4.0")
            engine = "py"

        # v2.0: unified debugger hook contract.
        # When any debugger/runtime-inspection feature is requested, route through
        # the Python inspector path so C and Python engines expose the same API
        # shape even if the native extension lacks pause/inspect hooks.
        debug_requested = any([
            bool(getattr(cfg, 'trace', False)),
            bool(getattr(cfg, 'step', False)),
            bool(getattr(cfg, 'break_lines', None)),
            bool(getattr(cfg, 'debug_pause_on_start', False)),
            bool(getattr(cfg, 'debug_break_instrs', None)),
            bool(getattr(cfg, 'debug_break_opcodes', None)),
            bool(getattr(cfg, 'debug_break_when', None)),
            bool(getattr(cfg, 'debug_watch_exprs', None)),
        ])
        native_caps = c_vm_capabilities()
        self.last_debug_capabilities = dict(native_caps)
        if debug_requested and engine in ('auto', 'c') and not c_vm_debug_supported():
            if native_require or not native_allow_fallback:
                raise MellowLangRuntimeError('NATIVE_REQUIRED', 'native C debugger parity is not complete yet in v2.4.0')
            self.last_engine_detail = 'python-debug-bridge-for-c-parity' if native_caps.get('available') else 'python-debug-path'
            engine = 'py'

        # ---- C-accelerated VM (hybrid/native-first) ----
        if engine in ("auto", "c"):
            try:
                self.last_debug_stop = None
                native_run = run_bytecode_ex(
                    bytecode=program.bytecode,
                    host=self._host,
                    config=config_dict,
                    func_table=getattr(program, "func_table", None),
                    event_table=getattr(program, "event_table", None),
                    allow_fallback=native_allow_fallback,
                    require_native=(native_require or (engine == 'c' and not native_allow_fallback)),
                )
                self.last_engine = native_run.engine
                self.last_engine_detail = native_run.detail
                self.last_native_result = {
                    'native_available': native_run.native_available,
                    'used_fallback': native_run.used_fallback,
                    'detail': native_run.detail,
                }
                return native_run.result
            except NativeExecutionRequiredError as e:
                self.last_engine = 'c'
                self.last_engine_detail = f'native-required-failed: {e}'
                raise MellowLangRuntimeError('NATIVE_REQUIRED', str(e))
            except (ImportError, CVMUnsupportedOpcode):
                if engine == "c":
                    raise
            except Exception as e:
                pc = getattr(e, "pc", None)
                if pc is not None and getattr(program, "line_map", None) and getattr(program, "col_map", None):
                    try:
                        pc_i = int(pc)
                        line0 = int(program.line_map[pc_i])
                        col = int(program.col_map[pc_i])
                        line = line0 + 1
                        kind = str(getattr(e, "kind", "RUNTIME") or "RUNTIME")
                        msg = getattr(e, "msg", None) or str(e)
                        raise MellowLangRuntimeError(kind, str(msg), line, filename=program.filename, col=col, trace=[{
                            "name": "<main>",
                            "filename": program.filename,
                            "line": line,
                            "col": col,
                        }])
                    except MellowLangRuntimeError:
                        raise
                    except Exception:
                        pass
                if engine == "c":
                    raise

        # ---- Legacy Python VM ----
        self.last_engine = "py"
        if not self.last_engine_detail:
            self.last_engine_detail = "python-legacy-vm"
        self.last_native_result = {'native_available': bool(native_caps.get('available')), 'used_fallback': False, 'detail': self.last_engine_detail}
        vm = _LegacyVM(
            program.bytecode,
            func_table=getattr(program, "func_table", None),
            event_table=getattr(program, "event_table", None),
            host=self._host,
            config=config_dict,
            replay=replay,
            filename=program.filename,
            source_lines=program.source_lines,
            line_map=getattr(program, 'line_map', None),
            col_map=getattr(program, 'col_map', None),
            end_line_map=getattr(program, 'end_line_map', None),
            end_col_map=getattr(program, 'end_col_map', None),
            span_map=getattr(program, 'span_map', None),
        )
        result = vm.run()
        self.last_debug_stop = getattr(vm, '_dbg_last_stop', None)
        return result
