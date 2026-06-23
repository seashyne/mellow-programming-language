from __future__ import annotations

import shutil
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import List

from ...compiler import Compiler
from ...lint import lint_source, format_source
from ..common import _json_print, _lazy_attr, _print_pretty_error, _read_text

pkg_scaffold_project = _lazy_attr("mellowlang.package_manager", "scaffold_project")

def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _standalone_mellow_binary() -> Path | None:
    root = _project_root()
    exe = "mellow.exe" if os.name == "nt" else "mellow"
    candidates = [
        root / "native" / "standalone" / "build" / exe,
        root / "native" / "standalone" / "build" / "Debug" / exe,
        root / "build" / "standalone-local-safety" / "Debug" / exe,
        root / "build" / "standalone-local-safety" / exe,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _native_check_file(p: Path, *, json_out: bool) -> int:
    native = _standalone_mellow_binary()
    if native is None:
        message = "standalone native mellow binary not found; build with `cmake -S native/standalone -B native/standalone/build && cmake --build native/standalone/build`"
        if json_out:
            _json_print({"ok": False, "file": str(p), "error": message})
        else:
            print(f"error: {message}", file=sys.stderr)
        return 1
    completed = subprocess.run([str(native), "check", str(p)], capture_output=True, text=True, check=False)
    if json_out:
        _json_print({
            "ok": completed.returncode == 0,
            "file": str(p),
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        })
    else:
        if completed.stdout:
            sys.stdout.write(completed.stdout)
        if completed.stderr:
            sys.stderr.write(completed.stderr)
    return int(completed.returncode)


def _cmd_check(file: str, json_out: bool) -> int:
    """
    Check mode:
      - First, attempt to compile (catches SYNTAX errors with code frame)
      - Then, run lints; print code-frame per issue
    """
    p = Path(file)
    if not p.exists():
        err = {"ok": False, "error": f"path not found: {p}"}
        if json_out:
            _json_print(err)
        else:
            print(f"error: {err['error']}")
        return 2

    # Directory mode: check all *.mellow files (recursive).
    if p.is_dir():
        targets = sorted(p.rglob("*.mellow"))
        if not targets:
            if json_out:
                _json_print({"ok": True, "checked": 0, "errors": 0})
            else:
                print("OK ok (no .mellow files found)")
            return 0

        errors = 0
        checked = 0
        for t in targets:
            checked += 1
            rc = _cmd_check(str(t), json_out=json_out)
            if rc != 0:
                errors += 1
        if json_out:
            _json_print({"ok": errors == 0, "checked": checked, "errors": errors})
        else:
            if errors == 0:
                print(f"\nOK ok ({checked} file(s))")
            else:
                print(f"\nERR {errors} error(s) in {checked} file(s)")
        return 0 if errors == 0 else 1

    return _native_check_file(p, json_out=json_out)

    src = _read_text(p)
    lines = src.splitlines(True)

    # 1) Syntax check via compiler (best signal)
    try:
        Compiler().compile(src, filename=str(p))
    except Exception as e:
        if json_out:
            _json_print({"ok": False, "error": str(e)})
        else:
            _print_pretty_error(e, filename=str(p), source_lines=lines)
        return 1

    # 2) Lint/style issues (non-fatal but should be visible)
    issues = lint_source(src)
    if json_out:
        _json_print({
            "ok": len(issues) == 0,
            "file": str(p),
            "issues": [asdict(it) if hasattr(it, "__dict__") else {"message": str(it)} for it in issues],
        })
        return 0 if not issues else 1

    if not issues:
        print("OK ok")
        return 0

    # Print code-frame per issue (Frinds-style)
    for it in issues:
        kind = getattr(it, "kind", "LINT").upper()
        msg = getattr(it, "message", str(it))
        ln = getattr(it, "line", None)
        col = getattr(it, "col", None)

        # fabricate an error-like object compatible with _print_pretty_error
        class _IssueErr(Exception):
            pass
        ee = _IssueErr(msg)
        setattr(ee, "error_type", kind)
        setattr(ee, "message", msg)
        setattr(ee, "filename", str(p))
        setattr(ee, "line_num", ln)
        setattr(ee, "col", col)
        _print_pretty_error(ee, filename=str(p), source_lines=lines)

    return 1
def _cmd_fmt(files: List[str], write: bool, check: bool) -> int:
    changed = 0
    for f in files:
        p = Path(f)
        if p.is_dir():
            for sub in p.rglob("*.mellow"):
                changed += _fmt_one(sub, write, check)
        else:
            changed += _fmt_one(p, write, check)
    return 0 if (not check or changed == 0) else 1

def _fmt_one(p: Path, write: bool, check: bool) -> int:
    if not p.exists():
        print(f"skip: {p} (not found)")
        return 0
    src = _read_text(p)
    out = format_source(src)
    if out == src:
        return 0
    if check:
        print(f"would format: {p}")
        return 1
    if write:
        p.write_text(out, encoding="utf-8")
        print(f"formatted: {p}")
        return 1
    sys.stdout.write(out)
    return 1

def _cmd_init(dest_dir: str, force: bool) -> int:
    dest = Path(dest_dir).resolve()
    template = Path(__file__).resolve().parents[3] / "project_template"
    if not template.exists():
        print("error: project_template not found.")
        return 2
    if dest.exists() and any(dest.iterdir()) and not force:
        print("error: destination not empty. Use --force.")
        return 2
    if dest.exists() and force:
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template, dest, dirs_exist_ok=True)
    print(f"[OK] created project: {dest}")
    return 0


def _cmd_new(dest_dir: str, force: bool, *, with_core: bool = True, preset: str = "starter") -> int:
    res = pkg_scaffold_project(dest_dir, force=force, with_core=with_core, preset=preset)
    if not res.get("ok"):
        print(f"error: {res.get('error', 'project scaffold failed')}")
        return 2
    print(f"[OK] created project: {res['project_dir']}")
    print(f"[OK] manifest: {res['manifest']}")
    print(f"[OK] preset: {res.get('preset', 'starter')}")
    if res.get('preload'):
        installed = []
        for item in res.get('preload', {}).get('installed', []):
            name = item.get('name')
            version = item.get('version')
            row = f"{name}@{version}" if version else str(name)
            if row not in installed:
                installed.append(row)
        if installed:
            print("[OK] starter packages: " + ", ".join(installed))
        runtime = (res.get('preload') or {}).get('runtime') or {}
        if runtime.get('runtime_map'):
            print(f"[OK] runtime map: {runtime['runtime_map']}")
    return 0
