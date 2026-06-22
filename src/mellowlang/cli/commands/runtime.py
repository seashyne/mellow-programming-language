from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path
from typing import Any

from ...compiler import Compiler
from ...vm import MellowVM, RunConfig
from ..common import _cli_line, _find_project_root, _json_print, _lazy_attr, _print_pretty_error, _read_text

pkg_auto_fetch_for_run = _lazy_attr("mellowlang.package_manager", "auto_fetch_for_run")

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


    src = _read_text(p)

    # error color policy is currently handled by runtime; here we only ensure ANSI support isn't forced wrongly.
    # (kept for CLI compatibility)
    use_color = True if color else (False if no_color else None)

    # v1.4.9: fast engine (compile-to-Python) shortcut
    if engine == "fast":
        from ...fast_compiler import FastRunner as _FastRunner
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
            native_allow_fallback=not bool(native_required),
            native_require=bool(native_required),
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

def _iter_test_files(root: Path, pattern: str) -> list[Path]:
    if root.is_file():
        return [root]
    out: list[Path] = []
    for p in sorted(root.rglob(pattern)):
        if p.is_file():
            out.append(p)
    return out

def _run_one_script(path: Path, *, engine: str, native_required: bool = False) -> dict[str, Any]:
    import io
    import contextlib

    src = _read_text(path)
    comp = Compiler()
    program = comp.compile(src, filename=str(path))
    vm = MellowVM()
    cfg = RunConfig(
        engine=engine,
        native_allow_fallback=not bool(native_required),
        native_require=bool(native_required),
    )

    buf_out = io.StringIO()
    buf_err = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            result = vm.run(program, config=cfg)
        return {"ok": True, "stdout": buf_out.getvalue(), "stderr": buf_err.getvalue(), "result": result}
    except Exception as e:
        return {"ok": False, "stdout": buf_out.getvalue(), "stderr": buf_err.getvalue(), "error": str(e), "type": e.__class__.__name__}


def _golden_output_for(path: Path) -> str | None:
    candidates = [
        path.with_suffix(path.suffix + ".out"),
        path.with_suffix(".out"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    return None


def _cmd_test(path: str, *, engine: str, pattern: str, json_out: bool, native_required: bool = False) -> int:
    root = Path(path)
    files = _iter_test_files(root, pattern)
    if not files:
        if json_out:
            _json_print({"ok": False, "error": f"no test files found in {root} (pattern={pattern})"})
        else:
            print(f"no test files found in {root} (pattern={pattern})")
        return 2

    results: list[dict[str, Any]] = []
    passed = 0
    failed = 0

    def compare(a: dict[str, Any], b: dict[str, Any]) -> tuple[bool, str]:
        keys = ("ok", "stdout", "stderr")
        for k in keys:
            if a.get(k) != b.get(k):
                return False, f"{k} mismatch"
        if a.get("ok"):
            if a.get("result") != b.get("result"):
                return False, "result mismatch"
        else:
            if a.get("error") != b.get("error"):
                return False, "error mismatch"
        return True, "ok"

    for f in files:
        golden = _golden_output_for(f)
        if engine == "dual":
            r_py = _run_one_script(f, engine="py")
            r_c = _run_one_script(f, engine="c", native_required=native_required)
            same, why = compare(r_py, r_c)
            ok = same
            if ok and golden is not None and r_py.get("stdout") != golden:
                ok = False
                why = "golden stdout mismatch"
            rec = {"file": str(f), "ok": ok, "why": why, "py": r_py, "c": r_c}
            if golden is not None:
                rec["golden"] = str(f.with_suffix(f.suffix + ".out") if f.with_suffix(f.suffix + ".out").exists() else f.with_suffix(".out"))
        else:
            r = _run_one_script(f, engine=engine, native_required=(native_required and engine == "c"))
            ok = bool(r.get("ok"))
            why = "ok"
            if ok and golden is not None and r.get("stdout") != golden:
                ok = False
                why = "golden stdout mismatch"
            rec = {"file": str(f), "ok": ok, "why": why, "run": r}
            if golden is not None:
                rec["golden"] = str(f.with_suffix(f.suffix + ".out") if f.with_suffix(f.suffix + ".out").exists() else f.with_suffix(".out"))
        results.append(rec)
        if ok:
            passed += 1
            if not json_out:
                print(f"[PASS] {f}")
        else:
            failed += 1
            if not json_out:
                print(f"[FAIL] {f}")
                if engine == "dual":
                    print(f"  reason: {rec.get('why')}")
                    print(f"  py: {rec['py'].get('error') or rec['py'].get('result')}")
                    print(f"  c : {rec['c'].get('error') or rec['c'].get('result')}")
                else:
                    print(f"  reason: {rec.get('why')}")
                    if rec['run'].get('error'):
                        print(f"  {rec['run'].get('error')}")
    out = {"ok": failed == 0, "passed": passed, "failed": failed, "results": results}
    if json_out:
        _json_print(out)
    return 0 if failed == 0 else 1

def _cmd_replay(file: str, *, replay_path: str, engine: str, json_out: bool) -> int:
    return _cmd_run(
        file,
        json_out=json_out,
        engine=engine,
        record_path=None,
        replay_path=replay_path,
        seed=None,
        global_seed=None,
        allow_ask=False,
        no_wait=False,
        allow_storage=True,
        storage_dir=None,
        allow_unsafe_fs=False,
        max_steps=None,
        max_ms=None,
        syscall_budget=None,
        profile=False,
        trace=False,
        step=False,
        break_lines=None,
        watch=None,
        ai_timeline=None,
        color=False,
        no_color=False,
        registry=None,
        no_resolve=False,
        sandbox_profile="default",
        allow_data_write=False,
        data_max_batch_size=None,
        data_max_query_rows=None,
        data_max_record_bytes=None,
        data_max_open_streams=None,
        native_required=False,
    )


def _cmd_record(
    file: str,
    *,
    record_path: str,
    engine: str,
    seed: int | None,
    global_seed: int | None,
    json_out: bool,
) -> int:
    return _cmd_run(
        file,
        json_out=json_out,
        engine=engine,
        record_path=record_path,
        replay_path=None,
        seed=seed,
        global_seed=global_seed,
        allow_ask=False,
        no_wait=False,
        allow_storage=True,
        storage_dir=None,
        allow_unsafe_fs=False,
        max_steps=None,
        max_ms=None,
        syscall_budget=None,
        profile=False,
        trace=False,
        step=False,
        break_lines=None,
        watch=None,
        ai_timeline=None,
        color=False,
        no_color=False,
        registry=None,
        no_resolve=False,
        sandbox_profile="default",
        allow_data_write=False,
        data_max_batch_size=None,
        data_max_query_rows=None,
        data_max_record_bytes=None,
        data_max_open_streams=None,
        native_required=False,
    )


def _cmd_diff(a: str, b: str, *, json_out: bool) -> int:
    import json
    def load(path: str) -> list[dict[str, Any]]:
        out = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out
    la = load(a)
    lb = load(b)
    n = min(len(la), len(lb))
    first = None
    for i in range(n):
        if la[i] != lb[i]:
            first = {"index": i, "a": la[i], "b": lb[i]}
            break
    if first is None and len(la) != len(lb):
        first = {"index": n, "a": la[n] if len(la) > n else None, "b": lb[n] if len(lb) > n else None, "note": "length mismatch"}
    ok = first is None
    out = {"ok": ok, "first_diff": first, "len_a": len(la), "len_b": len(lb)}
    if json_out:
        _json_print(out)
    else:
        if ok:
            print("logs are identical")
        else:
            print(f"first difference at index {first['index']}")
    return 0 if ok else 1


# ----------------------------
# Main
# ----------------------------
