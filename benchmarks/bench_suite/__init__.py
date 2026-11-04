"""Standard benchmark suite: config, environment capture, section runner, report."""

from __future__ import annotations

import sys

from .config import BENCHMARKS, NATIVE_VS_ZIG, ROOT

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(BENCHMARKS))
sys.path.insert(0, str(NATIVE_VS_ZIG))
