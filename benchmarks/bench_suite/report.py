from __future__ import annotations

from typing import Any


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
