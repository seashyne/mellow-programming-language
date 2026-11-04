from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = ROOT / "benchmarks"
NATIVE_VS_ZIG = BENCHMARKS / "native_vs_zig"
DEFAULT_MELLOW_BINARY = ROOT / "build" / "standalone-release" / "Release" / "mellow.exe"
DEFAULT_STANDALONE_SOURCE = BENCHMARKS / "fixtures" / "hello.mellow"
LOCAL_ZIG = ROOT / "tools" / "zig" / "zig-x86_64-windows-0.16.0" / "zig.exe"


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
