from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS = ROOT / "benchmarks"
NATIVE_VS_ZIG = BENCHMARKS / "native_vs_zig"
DEFAULT_MELLOW_BINARY = ROOT / "build" / "standalone-release" / "Release" / "mellow.exe"
DEFAULT_STANDALONE_SOURCE = ROOT / "examples" / "hello.mellow"
LOCAL_ZIG = ROOT / "tools" / "zig" / "zig-x86_64-windows-0.16.0" / "zig.exe"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(BENCHMARKS))
sys.path.insert(0, str(NATIVE_VS_ZIG))

import data_core_benchmark  # noqa: E402
import language_runtime_benchmark  # noqa: E402
import native_data_transform_benchmark  # noqa: E402
import run_compare  # noqa: E402
import standalone_runtime_benchmark  # noqa: E402


@dataclass(frozen=True)
class Profile:
    repeats: int
    cross_language_repeats: int
    standalone_repeats: int
    data_rows: int
    data_batch_size: int
    transform_rows: int
    transform_rounds: int


PROFILES = {
    "quick": Profile(
        repeats=5,
        cross_language_repeats=5,
        standalone_repeats=7,
        data_rows=50_000,
        data_batch_size=1_000,
        transform_rows=750,
        transform_rounds=150,
    ),
    "ci": Profile(
        repeats=7,
        cross_language_repeats=10,
        standalone_repeats=11,
        data_rows=100_000,
        data_batch_size=1_000,
        transform_rows=1_000,
        transform_rounds=250,
    ),
    "full": Profile(
        repeats=30,
        cross_language_repeats=30,
        standalone_repeats=31,
        data_rows=250_000,
        data_batch_size=1_000,
        transform_rows=1_500,
        transform_rounds=400,
    ),
}


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"cannot encode {type(value).__name__}")


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _tool_version(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    text = (completed.stdout or completed.stderr).strip()
    return text or None


def _git_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _environment(mellow_binary: Path, zig_path: str | None) -> dict[str, Any]:
    return {
        "timestamp_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "root": str(ROOT),
        "git_commit": _git_commit(),
        "host": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": {
            "executable": sys.executable,
            "version": platform.python_version(),
        },
        "tools": {
            "mellow_binary": str(mellow_binary),
            "mellow_version": _tool_version([str(mellow_binary), "--version"])
            if mellow_binary.exists()
            else None,
            "zig": {
                "path": zig_path,
                "version": _tool_version([zig_path, "version"]) if zig_path else None,
            },
            "c_compiler": shutil.which("gcc") or shutil.which("clang") or shutil.which("cl"),
            "lua": shutil.which("lua") or shutil.which("luajit"),
        },
    }


def _section_error(exc: BaseException) -> dict[str, Any]:
    return {
        "available": False,
        "failed": True,
        "error_type": type(exc).__name__,
        "error": str(exc),
    }


def _run_section(name: str, operation: Any) -> dict[str, Any]:
    try:
        result = operation()
    except BaseException as exc:  # keep the suite useful when one optional tool is absent
        result = _section_error(exc)
    return {
        "name": name,
        "result": result,
    }


def run_suite(
    profile_name: str,
    mellow_binary: Path,
    standalone_source: Path,
    zig_path: str | None,
    python_path: str | None,
    lua_path: str | None,
    include_cross_language: bool,
) -> dict[str, Any]:
    profile = PROFILES[profile_name]
    sections: dict[str, Any] = {}

    sections["standalone_runtime"] = _run_section(
        "standalone_runtime",
        lambda: standalone_runtime_benchmark.run_benchmark(
            mellow_binary,
            standalone_source,
            profile.standalone_repeats,
            "",
            platform.machine() or "unknown",
            "native",
        ),
    )["result"]

    sections["language_runtime"] = _run_section(
        "language_runtime",
        lambda: language_runtime_benchmark.run_benchmark(profile.repeats),
    )["result"]

    sections["data_core"] = _run_section(
        "data_core",
        lambda: data_core_benchmark.run_benchmark(
            profile.data_rows,
            profile.data_batch_size,
            profile.repeats,
        ),
    )["result"]

    sections["native_data_transform"] = _run_section(
        "native_data_transform",
        lambda: native_data_transform_benchmark.run_benchmark(
            profile.transform_rows,
            profile.transform_rounds,
            profile.repeats,
        ),
    )["result"]

    if include_cross_language:
        sections["native_vs_languages"] = _run_section(
            "native_vs_languages",
            lambda: run_compare.run_compare(
                mellow_binary,
                profile.cross_language_repeats,
                zig_path,
                python_path,
                lua_path,
                keep_zig_binary=False,
            ),
        )["result"]
    else:
        sections["native_vs_languages"] = {
            "available": False,
            "skipped": True,
            "reason": "disabled by --skip-cross-language",
        }

    return {
        "suite": "mellow_standard_benchmark",
        "schema_version": 1,
        "profile": profile_name,
        "profile_config": profile.__dict__,
        "environment": _environment(mellow_binary, zig_path),
        "sections": sections,
    }


def _ms(seconds: float | int | None) -> str:
    if seconds is None:
        return "n/a"
    return f"{float(seconds) * 1000:.2f}"


def _number(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):,.{digits}f}"


def _get(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


SUMMARY_METRICS = {
    "standalone hello median ms": "sections.standalone_runtime.median_seconds",
    "python cli startup median ms": "sections.language_runtime.cli_startup.median_seconds",
    "compile cold median ms": "sections.language_runtime.compile.cold.median_seconds",
    "data core rows/sec": "sections.data_core.rows_per_second",
    "native data transform speedup": "sections.native_data_transform.native_speedup",
    "arithmetic native speedup": "sections.language_runtime.runtime.arithmetic_loop.native_speedup",
    "function native speedup": "sections.language_runtime.runtime.function_calls.native_speedup",
    "money native speedup": "sections.language_runtime.runtime.money_add.native_speedup",
    "ledger native speedup": "sections.language_runtime.runtime.ledger_post.native_speedup",
}


def _comparison_rows(current: dict[str, Any], baseline: dict[str, Any] | None) -> list[str]:
    if not baseline:
        return []
    rows = [
        "## Baseline Comparison",
        "",
        "| Metric | Baseline | Current | Delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for label, path in SUMMARY_METRICS.items():
        old = _get(baseline, path)
        new = _get(current, path)
        if old is None or new is None:
            continue
        old_float = float(old)
        new_float = float(new)
        delta = ((new_float - old_float) / old_float * 100.0) if old_float else 0.0
        formatter = _ms if label.endswith(" ms") else _number
        rows.append(f"| {label} | {formatter(old_float)} | {formatter(new_float)} | {delta:+.2f}% |")
    rows.append("")
    return rows


def render_markdown(payload: dict[str, Any], baseline: dict[str, Any] | None = None) -> str:
    env = payload["environment"]
    sections = payload["sections"]
    lines = [
        f"# Mellow Standard Benchmark - {payload['profile']}",
        "",
        "## Environment",
        "",
        f"- Timestamp UTC: `{env.get('timestamp_utc')}`",
        f"- Commit: `{env.get('git_commit') or 'unknown'}`",
        f"- Host: `{env.get('host')}`",
        f"- Python: `{env['python'].get('version')}` at `{env['python'].get('executable')}`",
        f"- Mellow: `{env['tools'].get('mellow_version') or 'unavailable'}`",
        f"- Zig: `{env['tools']['zig'].get('version') or 'unavailable'}`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Standalone native run median | {_ms(_get(payload, SUMMARY_METRICS['standalone hello median ms']))} ms |",
        f"| Python CLI startup median | {_ms(_get(payload, SUMMARY_METRICS['python cli startup median ms']))} ms |",
        f"| Cold compile median | {_ms(_get(payload, SUMMARY_METRICS['compile cold median ms']))} ms |",
        f"| Data core throughput | {_number(_get(payload, SUMMARY_METRICS['data core rows/sec']), 0)} rows/sec |",
        f"| Native data transform speedup | {_number(_get(payload, SUMMARY_METRICS['native data transform speedup']))}x |",
        "",
        "## Native VM Speedups",
        "",
        "| Workload | Python VM ms | Native C ms | Speedup |",
        "| --- | ---: | ---: | ---: |",
    ]

    runtime = _get(payload, "sections.language_runtime.runtime") or {}
    for workload in ("arithmetic_loop", "function_calls", "money_add", "ledger_post"):
        item = runtime.get(workload, {})
        lines.append(
            "| "
            f"{workload} | "
            f"{_ms(_get(item, 'py.median_seconds'))} | "
            f"{_ms(_get(item, 'c.median_seconds'))} | "
            f"{_number(item.get('native_speedup'))}x |"
        )

    native_vs = sections.get("native_vs_languages", {})
    summary = native_vs.get("summary", {}) if isinstance(native_vs, dict) else {}
    if summary:
        lines.extend(
            [
                "",
                "## Cross-Language Median Timings",
                "",
                "| Workload | Mellow ms | Zig ms | C ms | Python ms | Lua ms |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for workload, item in summary.items():
            lines.append(
                "| "
                f"{workload} | "
                f"{_number(item.get('mellow_median_ms'))} | "
                f"{_number(item.get('zig_median_ms'))} | "
                f"{_number(item.get('c_median_ms'))} | "
                f"{_number(item.get('python_median_ms'))} | "
                f"{_number(item.get('lua_median_ms'))} |"
            )

    failed = [
        name
        for name, section in sections.items()
        if isinstance(section, dict) and section.get("failed")
    ]
    if failed:
        lines.extend(["", "## Failed Sections", ""])
        lines.extend(f"- `{name}`: {sections[name].get('error')}" for name in failed)

    lines.extend(["", *_comparison_rows(payload, baseline)])
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the standard Mellow benchmark suite.")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="quick")
    parser.add_argument("--output-dir", type=Path, default=BENCHMARKS / "reports" / "standard")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    parser.add_argument("--baseline", type=Path, help="Previous standard-suite JSON to compare against.")
    parser.add_argument("--mellow-binary", type=Path, default=DEFAULT_MELLOW_BINARY)
    parser.add_argument("--standalone-source", type=Path, default=DEFAULT_STANDALONE_SOURCE)
    parser.add_argument("--zig", default=str(LOCAL_ZIG) if LOCAL_ZIG.exists() else None)
    parser.add_argument("--python", help="Python executable for cross-language comparison.")
    parser.add_argument("--lua", help="Lua executable for cross-language comparison.")
    parser.add_argument("--skip-cross-language", action="store_true")
    args = parser.parse_args()

    if not args.mellow_binary.exists():
        parser.error(f"Mellow binary not found: {args.mellow_binary}")
    if not args.standalone_source.exists():
        parser.error(f"standalone source not found: {args.standalone_source}")

    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_out = args.json_out or args.output_dir / f"{stamp}-{args.profile}.json"
    markdown_out = args.markdown_out or args.output_dir / f"{stamp}-{args.profile}.md"

    payload = run_suite(
        args.profile,
        args.mellow_binary,
        args.standalone_source,
        args.zig,
        args.python,
        args.lua,
        include_cross_language=not args.skip_cross_language,
    )
    baseline = _load_json(args.baseline)

    json_out.parent.mkdir(parents=True, exist_ok=True)
    markdown_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(payload, indent=2, default=_json_default) + "\n", encoding="utf-8")
    markdown_out.write_text(render_markdown(payload, baseline), encoding="utf-8")

    print(f"Wrote JSON: {json_out}")
    print(f"Wrote Markdown: {markdown_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
