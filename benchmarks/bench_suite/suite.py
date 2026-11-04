from __future__ import annotations

import platform
from pathlib import Path
from typing import Any

import data_core_benchmark
import language_runtime_benchmark
import native_data_transform_benchmark
import run_compare
import standalone_runtime_benchmark

from .config import PROFILES
from .environment import _environment


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
