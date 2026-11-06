"""The `mellow run` handler: find the project, fetch what it needs, pick the
engine, then compile and run."""

from __future__ import annotations

import json
import subprocess
import sys

from pathlib import Path
from typing import Any

from ....compiler import Compiler
from ....vm import MellowVM
from ...common import _cli_line, _find_project_root, _json_print, _print_pretty_error, _read_text

from .deps import pkg_auto_fetch_for_run
from .run_config import RunSettings, build_run_config
from .standalone import _can_use_standalone_native, _standalone_mellow_binary


def _cmd_run(file: str, *, json_out: bool, engine: str, record_path: str | None, replay_path: str | None,
             seed: int | None, global_seed: int | None, allow_ask: bool, no_wait: bool,
             allow_storage: bool, storage_dir: str | None, allow_unsafe_fs: bool,
             max_steps: int | None, max_ms: int | None, syscall_budget: int | None,
             profile: bool,
             trace: bool = False, step: bool = False, break_lines: str | None = None,
             watch: str | None = None, ai_timeline: str | None = None,
             color: bool = False, no_color: bool = False, registry: str | None = None, no_resolve: bool = False,
             sandbox_profile: str = "default", allow_data_write: bool = False,
             data_max_batch_size: int | None = None, data_max_query_rows: int | None = None,
             data_max_record_bytes: int | None = None, data_max_open_streams: int | None = None,
             native_required: bool = False) -> int:
    p = Path(file)

    # Secure save system default (dev-friendly). In project mode this becomes deny-by-default.
    allow_save: bool = True
    sandbox_profile = str(sandbox_profile or "default").strip().lower()
    if sandbox_profile == "finance":
        allow_ask = False
        no_wait = True
        allow_storage = False
        allow_save = False
        allow_unsafe_fs = False
        if max_steps is None:
            max_steps = 100_000
        if syscall_budget is None:
            syscall_budget = 100
    elif sandbox_profile == "data":
        allow_ask = False
        no_wait = True
        allow_save = False
        allow_unsafe_fs = False
        if max_steps is None:
            max_steps = 1_000_000
        if max_ms is None:
            max_ms = 30_000
        if syscall_budget is None:
            syscall_budget = 10_000
        if data_max_batch_size is None:
            data_max_batch_size = 1_000
        if data_max_query_rows is None:
            data_max_query_rows = 5_000

    # --- Project mode auto-detect (v1.4.5 standard) ---
    project_root: Path | None = None
    manifest_path: Path | None = None
    manifest_data: dict[str, Any] = {}

    if p.exists() and p.is_dir():
        # Running a directory: treat it as project root if it has mellow.json
        if (p / "mellow.json").exists():
            project_root = p.resolve()
    else:
        # Running a file: search parents for mellow.json
        project_root = _find_project_root(p)

    if project_root is None:
        # Also try CWD (useful when running relative files)
        project_root = _find_project_root(Path.cwd())

    runtime_root = project_root or (p.parent if p.exists() and p.is_file() else Path.cwd())
    runtime_map = None
    rr: dict[str, Any] | None = None
    if not no_resolve:
        try:
            rr = pkg_auto_fetch_for_run(p if p.exists() else runtime_root, registry=registry, strict=False)
            runtime_map = rr.get("runtime_map")
            if rr.get("installed"):
                installed_rows = [f"{item.get('name')}@{item.get('version')}" for item in rr.get('installed', [])]
                _cli_line('auto-installed missing packages: ' + ', '.join(installed_rows), kind='ok')
            if rr.get("auto_added"):
                auto_added_rows = [f"{k} ({v})" for k, v in (rr.get('auto_added') or {}).items()]
                _cli_line('added to manifest: ' + ', '.join(auto_added_rows), kind='hint')
        except Exception:
            runtime_map = None

    if project_root is not None:
        manifest_path = project_root / "mellow.json"
        try:
            manifest_data = json.loads(_read_text(manifest_path))
        except Exception:
            manifest_data = {}

    project_mode = bool(project_root is not None and bool(manifest_data))

    # If directory run: resolve entry
    if p.exists() and p.is_dir() and project_mode:
        entry = str(manifest_data.get("entry", "main.mellow"))
        p = (project_root / entry).resolve()

    # Apply manifest defaults if not explicitly provided
    if project_mode:
        if global_seed is None and manifest_data.get("global_seed") is not None:
            try:
                global_seed = int(manifest_data.get("global_seed"))
            except Exception:
                pass

        # permissions can be list[str] (preferred) or dict (compatibility input)
        perms = manifest_data.get("permissions")
        if isinstance(perms, dict):
            if not allow_ask and perms.get("allow_ask") is True:
                allow_ask = True
            if perms.get("allow_wait") is False:
                no_wait = True
            if perms.get("allow_storage") is False:
                allow_storage = False
            # Secure save system (v1.3.4)
            allow_save = True
            if perms.get("allow_save") is False:
                allow_save = False
            if storage_dir is None and perms.get("storage_dir"):
                storage_dir = str(perms.get("storage_dir"))
        else:
            allow_save = True

    if not p.exists():
        err = {"ok": False, "error": f"file not found: {p}"}
        if json_out:
            _json_print(err)
        else:
            print(f"error: {err['error']}")
        return 2

    if _can_use_standalone_native(
        engine=engine,
        json_out=json_out,
        record_path=record_path,
        replay_path=replay_path,
        profile=profile,
        trace=trace,
        step=step,
        break_lines=break_lines,
        watch=watch,
        ai_timeline=ai_timeline,
        sandbox_profile=sandbox_profile,
        project_mode=project_mode,
    ):
        native_binary = _standalone_mellow_binary()
        if native_binary is not None:
            native_args = [str(native_binary), str(p)]
            if allow_data_write:
                native_args.append("--data-write")
            if data_max_query_rows is not None:
                native_args.extend(["--data-max-rows", str(int(data_max_query_rows))])
            completed = subprocess.run(native_args, check=False)
            return int(completed.returncode)
        message = "standalone native mellow binary not found; build with `cmake -S native/standalone -B build/standalone-release -DCMAKE_BUILD_TYPE=Release && cmake --build build/standalone-release --config Release`"
        if json_out:
            _json_print({"ok": False, "error": message})
        else:
            print(f"error: {message}", file=sys.stderr)
        return 1

    src = _read_text(p)

    # error color policy is currently handled by runtime; here we only ensure ANSI support isn't forced wrongly.
    # (kept for CLI compatibility)
    use_color = True if color else (False if no_color else None)

    # v1.4.9: fast engine (compile-to-Python) shortcut
    if engine == "fast":
        from ....fast_compiler import FastRunner as _FastRunner
        _fr = _FastRunner(capture_output=False)
        try:
            _fr.run(src, filename=str(p))
        except SystemExit:
            pass
        except Exception as _fe:
            print(f"error: {_fe}", file=sys.stderr)
            return 1
        return 0

    try:
        comp = Compiler()
        program = comp.compile(src, filename=str(p))

        vm = MellowVM()
        cfg = build_run_config(RunSettings(
            ai_timeline=ai_timeline,
            allow_ask=allow_ask,
            allow_data_write=allow_data_write,
            allow_save=allow_save,
            allow_storage=allow_storage,
            allow_unsafe_fs=allow_unsafe_fs,
            break_lines=break_lines,
            data_max_batch_size=data_max_batch_size,
            data_max_open_streams=data_max_open_streams,
            data_max_query_rows=data_max_query_rows,
            data_max_record_bytes=data_max_record_bytes,
            engine=engine,
            global_seed=global_seed,
            manifest_data=manifest_data,
            max_ms=max_ms,
            max_steps=max_steps,
            native_required=native_required,
            no_wait=no_wait,
            profile=profile,
            project_mode=project_mode,
            project_root=project_root,
            record_path=record_path,
            replay_path=replay_path,
            sandbox_profile=sandbox_profile,
            seed=seed,
            step=step,
            storage_dir=storage_dir,
            syscall_budget=syscall_budget,
            trace=trace,
            watch=watch,
        ))

        result = vm.run(program, config=cfg)
        if json_out:
            _json_print({"ok": True, "result": result})
        return 0
    except Exception as e:
        if json_out:
            _json_print({"ok": False, "error": str(e)})
        else:
            _print_pretty_error(e, filename=str(p), source_lines=src.splitlines(True), use_color=use_color)
        return 1
