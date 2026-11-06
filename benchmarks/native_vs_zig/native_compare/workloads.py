from __future__ import annotations

from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
BENCH_DIR = Path(__file__).resolve().parents[1]
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
