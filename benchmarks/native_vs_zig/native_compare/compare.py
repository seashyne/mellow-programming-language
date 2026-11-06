from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .builders import _build_c, _build_zig, _find_c_compiler
from .process import _tool_version, _zig_version
from .runners import _benchmark_runtime, _ratio_summary
from .workloads import BENCH_DIR, WORKLOADS


def run_compare(
    mellow_binary: Path,
    repeats: int,
    zig_path: str | None,
    python_path: str | None,
    lua_path: str | None,
    keep_zig_binary: bool,
) -> dict[str, Any]:
    zig = zig_path or shutil.which("zig")
    c_compiler = _find_c_compiler(zig)
    python_exe = python_path or shutil.which("python")
    lua_exe = lua_path or shutil.which("lua") or shutil.which("luajit")

    result: dict[str, Any] = {
        "suite": "native_mellow_comparison",
        "workload_order": list(WORKLOADS),
        "workloads": {},
        "mellow": {
            "binary": str(mellow_binary),
            "version": subprocess.run([str(mellow_binary), "--version"], capture_output=True, text=True, check=True).stdout.strip(),
            "runtime_info": subprocess.run([str(mellow_binary), "--runtime-info"], capture_output=True, text=True, check=True).stdout.strip(),
        },
        "tools": {
            "zig": {"available": bool(zig), "path": zig, "version": _zig_version(zig) if zig else None},
            "c": {
                "available": bool(c_compiler),
                "compiler": c_compiler[0] if c_compiler else None,
                "path": c_compiler[1] if c_compiler else None,
            },
            "python": {"available": bool(python_exe), "path": python_exe, "version": _tool_version([python_exe, "--version"]) if python_exe else None},
            "lua": {"available": bool(lua_exe), "path": lua_exe, "version": _tool_version([lua_exe, "-v"]) if lua_exe else None},
        },
        "summary": {},
    }

    for workload, meta in WORKLOADS.items():
        expected = str(meta["expected_output"])
        result["workloads"][workload] = {
            "description": meta["description"],
            "iterations": meta["iterations"],
            "expected_output": expected,
        }

        _benchmark_runtime(
            result,
            workload,
            "mellow",
            [str(mellow_binary), str(BENCH_DIR / f"{workload}.mellow")],
            repeats,
            expected,
            {"binary": str(mellow_binary)},
        )

        if c_compiler:
            c_kind, c_path = c_compiler
            unique_c = f"{workload}_c_{os.getpid()}_{int(time.time() * 1000)}"
            c_bin = BENCH_DIR / "build" / ((unique_c + ".exe") if os.name == "nt" else unique_c)
            try:
                _build_c(c_kind, c_path, BENCH_DIR / f"{workload}.c", c_bin)
                _benchmark_runtime(
                    result,
                    workload,
                    "c",
                    [str(c_bin)],
                    repeats,
                    expected,
                    {"compiler": c_kind, "compiler_path": c_path, "binary": str(c_bin)},
                )
                if not keep_zig_binary:
                    try:
                        c_bin.unlink(missing_ok=True)
                    except OSError:
                        pass
            except subprocess.CalledProcessError as exc:
                result["workloads"][workload]["c"] = {
                    "available": True,
                    "failed": True,
                    "compiler": c_kind,
                    "compiler_path": c_path,
                    "returncode": exc.returncode,
                    "stdout": exc.stdout,
                    "stderr": exc.stderr,
                }
        else:
            result["workloads"][workload]["c"] = {
                "available": False,
                "reason": "no C compiler was found in PATH; Zig was also unavailable for zig cc fallback.",
            }

        if zig:
            unique_zig = f"{workload}_zig_{os.getpid()}_{int(time.time() * 1000)}"
            zig_bin = BENCH_DIR / "build" / ((unique_zig + ".exe") if (Path(zig).suffix.lower() == ".exe" or Path.cwd().drive) else unique_zig)
            try:
                _build_zig(zig, BENCH_DIR / f"{workload}.zig", zig_bin)
                _benchmark_runtime(
                    result,
                    workload,
                    "zig",
                    [str(zig_bin)],
                    repeats,
                    expected,
                    {"binary": str(zig_bin), "version": result["tools"]["zig"]["version"]},
                )
                if not keep_zig_binary:
                    try:
                        zig_bin.unlink(missing_ok=True)
                    except OSError:
                        pass
            except subprocess.CalledProcessError as exc:
                result["workloads"][workload]["zig"] = {
                    "available": True,
                    "failed": True,
                    "version": result["tools"]["zig"]["version"],
                    "returncode": exc.returncode,
                    "stdout": exc.stdout,
                    "stderr": exc.stderr,
                }
        else:
            result["workloads"][workload]["zig"] = {
                "available": False,
                "reason": "zig executable was not found in PATH; pass --zig PATH or install Zig to run this side.",
            }

        if python_exe:
            _benchmark_runtime(
                result,
                workload,
                "python",
                [python_exe, str(BENCH_DIR / f"{workload}.py")],
                repeats,
                expected,
                {"binary": python_exe, "version": result["tools"]["python"]["version"]},
            )
        else:
            result["workloads"][workload]["python"] = {
                "available": False,
                "reason": "python executable was not found in PATH; pass --python PATH to run this side.",
            }

        if lua_exe:
            _benchmark_runtime(
                result,
                workload,
                "lua",
                [lua_exe, str(BENCH_DIR / f"{workload}.lua")],
                repeats,
                expected,
                {"binary": lua_exe, "version": result["tools"]["lua"]["version"]},
            )
        else:
            result["workloads"][workload]["lua"] = {
                "available": False,
                "reason": "lua/luajit executable was not found in PATH; pass --lua PATH to run this side.",
            }

        result["summary"][workload] = _ratio_summary(result["workloads"][workload])
    return result
