from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = ROOT / "benchmarks"
BENCH_SUITE = BENCHMARKS / "bench_suite"
NATIVE_COMPARE = BENCHMARKS / "native_vs_zig" / "native_compare"


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _declared_functions(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]


def test_standard_suite_is_a_thin_facade_over_bench_suite() -> None:
    facade = BENCHMARKS / "run_all.py"
    assert _line_count(facade) <= 200, "run_all.py must stay an entry point"
    assert _declared_functions(facade) == ["_json_default", "_load_json", "main"]
    modules = sorted(p.stem for p in BENCH_SUITE.glob("*.py") if p.stem != "__init__")
    assert modules == ["config", "environment", "report", "suite"], (
        "bench_suite must keep one concern per module, not accumulate helpers"
    )
    for path in sorted(BENCH_SUITE.glob("*.py")):
        assert _line_count(path) <= 300, f"{path.name} grew past one concern"
    assert _declared_functions(BENCH_SUITE / "suite.py") == [
        "_section_error", "_run_section", "run_suite"]
    assert _declared_functions(BENCH_SUITE / "report.py")[-1] == "render_markdown"


def test_native_compare_is_a_thin_facade_over_native_compare_package() -> None:
    facade = BENCHMARKS / "native_vs_zig" / "run_compare.py"
    assert _line_count(facade) <= 200, "run_compare.py must stay an entry point"
    assert _declared_functions(facade) == ["main"]
    modules = sorted(p.stem for p in NATIVE_COMPARE.glob("*.py") if p.stem != "__init__")
    assert modules == ["builders", "compare", "process", "runners", "workloads"], (
        "native_compare must keep one benchmark concern per module"
    )
    for path in sorted(NATIVE_COMPARE.glob("*.py")):
        assert _line_count(path) <= 300, f"{path.name} grew past one concern"
    assert _declared_functions(NATIVE_COMPARE / "compare.py") == ["run_compare"]


def test_cross_language_workloads_have_a_source_per_runtime() -> None:
    workload_dir = BENCHMARKS / "native_vs_zig"
    for workload in ("sum_loop", "function_calls", "list_index", "branch_mod", "string_concat"):
        for suffix in (".mellow", ".c", ".zig", ".rs", ".py", ".lua"):
            assert (workload_dir / f"{workload}{suffix}").exists(), (
                f"missing {workload}{suffix} in the cross-language comparison"
            )
