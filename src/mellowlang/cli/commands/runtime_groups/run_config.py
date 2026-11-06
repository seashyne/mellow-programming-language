"""The settings a run carries into the VM, and the one place that turns them into a `RunConfig`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ....vm import RunConfig


@dataclass
class RunSettings:
    """What `mellow run` settled on for this program, before the VM sees it."""

    ai_timeline: str | None
    allow_ask: bool
    allow_data_write: bool
    allow_save: bool
    allow_storage: bool
    allow_unsafe_fs: bool
    break_lines: str | None
    data_max_batch_size: int | None
    data_max_open_streams: int | None
    data_max_query_rows: int | None
    data_max_record_bytes: int | None
    engine: str
    global_seed: int | None
    manifest_data: dict[str, Any]
    max_ms: int | None
    max_steps: int | None
    native_required: bool
    no_wait: bool
    profile: bool
    project_mode: bool
    project_root: Path | None
    record_path: str | None
    replay_path: str | None
    sandbox_profile: str
    seed: int | None
    step: bool
    storage_dir: str | None
    syscall_budget: int | None
    trace: bool
    watch: str | None


def build_run_config(s: RunSettings) -> RunConfig:
    """Assemble the VM config the way the handler used to inline it."""
    # the settings open into the handler's own names, so what follows is HEAD's
    # assembly line for line, with no name edited
    ai_timeline = s.ai_timeline
    allow_ask = s.allow_ask
    allow_data_write = s.allow_data_write
    allow_save = s.allow_save
    allow_storage = s.allow_storage
    allow_unsafe_fs = s.allow_unsafe_fs
    break_lines = s.break_lines
    data_max_batch_size = s.data_max_batch_size
    data_max_open_streams = s.data_max_open_streams
    data_max_query_rows = s.data_max_query_rows
    data_max_record_bytes = s.data_max_record_bytes
    engine = s.engine
    global_seed = s.global_seed
    manifest_data = s.manifest_data
    max_ms = s.max_ms
    max_steps = s.max_steps
    native_required = s.native_required
    no_wait = s.no_wait
    profile = s.profile
    project_mode = s.project_mode
    project_root = s.project_root
    record_path = s.record_path
    replay_path = s.replay_path
    sandbox_profile = s.sandbox_profile
    seed = s.seed
    step = s.step
    storage_dir = s.storage_dir
    syscall_budget = s.syscall_budget
    trace = s.trace
    watch = s.watch

    # Dev standard: if no project manifest, default storage_dir to CWD (like Python/Lua)
    if not project_mode and storage_dir is None:
        storage_dir = "."

    # Project standard: parse sandbox_root + fs permissions
    sandbox_root = None
    fs_read_allow: str | None = None
    fs_write_allow: str | None = None
    save_slots_max: int | None = None
    save_bytes_max: int | None = None
    # Networking (v1.3.5)
    allow_net: bool = False
    net_http_allow: str | None = None
    net_ws_allow: str | None = None
    net_max_bytes: int | None = None
    net_timeout_s: float | None = None
    interop_allow: str | None = None
    if project_mode:
        sandbox_root = str(manifest_data.get("sandbox_root") or manifest_data.get("sandbox") or "saves")
        perms = manifest_data.get("permissions")
        read_roots: list[str] = []
        write_roots: list[str] = []
        interop_items: list[str] = []
        # Secure save system perms
        allow_save = False
        if isinstance(perms, list):
            http_allow: list[str] = []
            ws_allow: list[str] = []
            for item in perms:
                if not isinstance(item, str):
                    continue
                t = item.strip()
                if t == 'save' or t == 'save:true':
                    allow_save = True
                elif t == 'save:false':
                    allow_save = False
                elif t.startswith('save.max_slots:'):
                    try:
                        save_slots_max = int(t.split(':', 1)[1])
                    except Exception:
                        pass
                elif t.startswith('save.max_bytes:'):
                    try:
                        save_bytes_max = int(t.split(':', 1)[1])
                    except Exception:
                        pass
                # Networking perms
                if t == 'net' or t == 'net:true':
                    allow_net = True
                elif t == 'net:false':
                    allow_net = False
                elif t.startswith('net.http:'):
                    http_allow.append(t.split(':', 1)[1])
                    allow_net = True
                elif t.startswith('net.ws:'):
                    ws_allow.append(t.split(':', 1)[1])
                    allow_net = True
                elif t.startswith('net.max_bytes:'):
                    try:
                        net_max_bytes = int(t.split(':', 1)[1])
                    except Exception:
                        pass
                elif t.startswith('net.timeout_s:'):
                    try:
                        net_timeout_s = float(t.split(':', 1)[1])
                    except Exception:
                        pass
                elif t.startswith('interop:'):
                    interop_name = t.split(':', 1)[1].strip()
                    if interop_name:
                        interop_items.append(interop_name)
                if t.startswith("fs.read:"):
                    read_roots.append(t.split(":", 1)[1])
                elif t.startswith("fs.write:"):
                    write_roots.append(t.split(":", 1)[1])
                elif t.startswith("fs.rw:"):
                    r = t.split(":", 1)[1]
                    read_roots.append(r)
                    write_roots.append(r)
        elif isinstance(perms, dict):
            # compatibility input
            allow_save = bool(perms.get('allow_save', True))
            allow_net = bool(perms.get('allow_net', False))
            try:
                if perms.get('net_max_bytes') is not None:
                    net_max_bytes = int(perms.get('net_max_bytes'))
            except Exception:
                pass
            try:
                if perms.get('net_timeout_s') is not None:
                    net_timeout_s = float(perms.get('net_timeout_s'))
            except Exception:
                pass
            if perms.get('net_http_allow'):
                net_http_allow = str(perms.get('net_http_allow'))
            if perms.get('net_ws_allow'):
                net_ws_allow = str(perms.get('net_ws_allow'))
            raw_interop = perms.get('interop') or perms.get('interop_allow')
            if isinstance(raw_interop, list):
                interop_allow = ",".join(str(item).strip() for item in raw_interop if str(item).strip())
            elif isinstance(raw_interop, str):
                interop_allow = raw_interop
            try:
                if perms.get('save_slots_max') is not None:
                    save_slots_max = int(perms.get('save_slots_max'))
            except Exception:
                pass
            try:
                if perms.get('save_bytes_max') is not None:
                    save_bytes_max = int(perms.get('save_bytes_max'))
            except Exception:
                pass
        fs_read_allow = ",".join(read_roots) if read_roots else None
        fs_write_allow = ",".join(write_roots) if write_roots else None
        if isinstance(perms, list):
            net_http_allow = ",".join(http_allow) if http_allow else None
            net_ws_allow = ",".join(ws_allow) if ws_allow else None
            interop_allow = ",".join(interop_items) if interop_items else None

    if sandbox_profile == "finance":
        allow_ask = False
        no_wait = True
        allow_storage = False
        allow_save = False
        allow_net = False
        net_http_allow = None
        net_ws_allow = None
        allow_unsafe_fs = False
        allow_data_write = False
    elif sandbox_profile == "data":
        allow_ask = False
        no_wait = True
        allow_save = False
        allow_net = False
        net_http_allow = None
        net_ws_allow = None
        allow_unsafe_fs = False

    cfg = RunConfig(
        seed=seed,
        global_seed=global_seed,
        record_path=record_path,
        replay_path=replay_path,
        engine=str(engine),
        native_allow_fallback=False,
        native_require=(str(engine).lower().strip() == "c" or bool(native_required)),
        allow_ask=allow_ask,
        allow_wait=not no_wait,
        allow_storage=allow_storage,
        allow_save=allow_save,
        storage_dir=storage_dir,
        allow_unsafe_fs=bool(allow_unsafe_fs),
        project_mode=project_mode,
        project_root=str(project_root) if project_mode and project_root else None,
        sandbox_root=str(sandbox_root) if sandbox_root else None,
        fs_read_allow=fs_read_allow,
        fs_write_allow=fs_write_allow,
        allow_net=allow_net,
        net_http_allow=net_http_allow,
        net_ws_allow=net_ws_allow,
        net_max_bytes=net_max_bytes,
        net_timeout_s=net_timeout_s,
        interop_allow=interop_allow,
        save_slots_max=save_slots_max,
        save_bytes_max=save_bytes_max,
        max_steps=max_steps,
        max_ms=max_ms,
        syscall_budget=syscall_budget,
        data_max_batch_size=data_max_batch_size,
        data_max_open_streams=data_max_open_streams,
        data_max_record_bytes=data_max_record_bytes,
        data_max_query_rows=data_max_query_rows,
        allow_data_write=allow_data_write,
        profile=profile,
        trace=trace,
        step=step,
        break_lines=break_lines,
        watch=watch,
        ai_timeline=ai_timeline,
    )
    return cfg
