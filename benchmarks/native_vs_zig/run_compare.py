from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BENCH_DIR = Path(__file__).resolve().parent
WORKLOADS: dict[str, dict[str, Any]] = {
    "sum_loop": {
        "iterations": 2_000_000,
        "expected_output": "1999999000000",
        "description": "integer while loop sum; includes Mellow loop super-opcode coverage",
    },
    "function_calls": {
        "iterations": 200_000,
        "expected_output": "19999900000",
        "description": "small function call inside a while loop",
    },
    "list_index": {
        "iterations": 500_000,
        "expected_output": "1500000",
        "description": "list/array indexing plus modulo in a loop",
    },
    "branch_mod": {
        "iterations": 500_000,
        "expected_output": "1000000",
        "description": "branching plus modulo in a loop",
    },
    "string_concat": {
        "iterations": 2_000,
        "expected_output": "2000",
        "description": "repeated string append followed by length",
    },
}


def _time_command(command: list[str], repeats: int, expected_output: str) -> dict[str, Any]:
    warmup = subprocess.run(command, capture_output=True, text=True, check=True)
    expected = warmup.stdout.strip()
    if expected != expected_output:
        raise RuntimeError(f"unexpected output from {' '.join(command)}: {expected}")

    samples: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        completed = subprocess.run(command, capture_output=True, text=True, check=True)
        elapsed = time.perf_counter() - started
        output = completed.stdout.strip()
        if output != expected:
            raise RuntimeError(f"benchmark output changed: {output} != {expected}")
        samples.append(elapsed)

    median = statistics.median(samples)
    return {
        "command": command,
        "output": expected,
        "repeats": repeats,
        "median_ms": median * 1000.0,
        "average_ms": statistics.fmean(samples) * 1000.0,
        "min_ms": min(samples) * 1000.0,
        "max_ms": max(samples) * 1000.0,
        "samples_ms": [sample * 1000.0 for sample in samples],
    }


def _zig_version(zig: str) -> str:
    return subprocess.run([zig, "version"], capture_output=True, text=True, check=True).stdout.strip()


def _tool_version(command: list[str]) -> str:
    completed = subprocess.run(command, capture_output=True, text=True, check=True)
    return (completed.stdout or completed.stderr).strip()


def _build_zig(zig: str, source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    cache_root = Path(os.environ.get("TEMP") or os.environ.get("TMP") or str(output.parent)) / "mellow-zig-cache"
    local_cache = cache_root / "local"
    global_cache = cache_root / "global"
    local_cache.mkdir(parents=True, exist_ok=True)
    global_cache.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    subprocess.run(
        [
            zig,
            "build-exe",
            str(source),
            "-O",
            "ReleaseFast",
            "-fstrip",
            "--cache-dir",
            str(local_cache),
            "--global-cache-dir",
            str(global_cache),
            "--name",
            output.stem,
            "-femit-bin",
        ],
        cwd=output.parent,
        capture_output=True,
        text=True,
        check=True,
    )
    produced = output.parent / (output.stem + ".exe")
    if not produced.exists():
        produced = output.parent / output.stem
    if not produced.exists():
        raise RuntimeError(f"Zig did not produce expected binary for {output.stem}")
    if produced.resolve() != output.resolve():
        shutil.move(str(produced), str(output))


def _find_c_compiler(zig: str | None) -> tuple[str, str] | None:
    for name in ("cc", "gcc", "clang", "cl"):
        path = shutil.which(name)
        if path:
            return name, path
    if zig:
        return "zig cc", zig
    return None


def _build_c(compiler_kind: str, compiler_path: str, source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    if compiler_kind == "cl":
        command = [
            compiler_path,
            "/nologo",
            "/O2",
            str(source),
            f"/Fe:{output}",
        ]
    elif compiler_kind == "zig cc":
        command = [
            compiler_path,
            "cc",
            "-O3",
            str(source),
            "-o",
            str(output),
        ]
    else:
        command = [
            compiler_path,
            "-O3",
            str(source),
            "-o",
            str(output),
        ]
    subprocess.run(command, cwd=output.parent, capture_output=True, text=True, check=True)
    if not output.exists():
        raise RuntimeError(f"C compiler did not produce expected binary: {output}")


def _benchmark_runtime(
    result: dict[str, Any],
    workload: str,
    runtime: str,
    command: list[str],
    repeats: int,
    expected_output: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    slot = result["workloads"][workload].setdefault(runtime, {})
    if metadata:
        slot.update(metadata)
    slot["available"] = True
    try:
        slot["benchmark"] = _time_command(command, repeats, expected_output)
    except subprocess.CalledProcessError as exc:
        slot["failed"] = True
        slot["returncode"] = exc.returncode
        slot["stdout"] = exc.stdout
        slot["stderr"] = exc.stderr
        slot["command"] = command
    except RuntimeError as exc:
        slot["failed"] = True
        slot["error"] = str(exc)
        slot["command"] = command


def _ratio_summary(workload_result: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    mellow = workload_result.get("mellow", {})
    mellow_bench = mellow.get("benchmark")
    if not mellow_bench:
        return summary
    mellow_median = float(mellow_bench["median_ms"])
    summary["mellow_median_ms"] = mellow_median
    for runtime in ("zig", "c", "python", "lua"):
        bench = workload_result.get(runtime, {}).get("benchmark")
        if not bench:
            continue
        runtime_median = float(bench["median_ms"])
        summary[f"{runtime}_median_ms"] = runtime_median
        if runtime in {"python", "lua"}:
            summary[f"mellow_faster_than_{runtime}_by"] = runtime_median / mellow_median if mellow_median else None
        else:
            summary[f"{runtime}_faster_by"] = mellow_median / runtime_median if runtime_median else None
    return summary


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Mellow 2.9.7 native runtime with Zig ReleaseFast.")
    parser.add_argument("--mellow-binary", type=Path, default=ROOT / "build" / "standalone-release" / "Release" / "mellow.exe")
    parser.add_argument("--zig", help="Path to zig executable. Defaults to PATH lookup.")
    parser.add_argument("--python", help="Path to python executable. Defaults to PATH lookup.")
    parser.add_argument("--lua", help="Path to lua or luajit executable. Defaults to PATH lookup.")
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--keep-zig-binary", action="store_true")
    args = parser.parse_args()

    if args.repeats < 3:
        parser.error("--repeats must be at least 3")
    if not args.mellow_binary.exists():
        parser.error(f"Mellow binary not found: {args.mellow_binary}")

    payload = run_compare(args.mellow_binary, args.repeats, args.zig, args.python, args.lua, args.keep_zig_binary)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
