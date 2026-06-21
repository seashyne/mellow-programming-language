from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mellowlang.release_gate import run_release_gate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Mellow package release checks")
    parser.add_argument("--skip-native", action="store_true", help="Use when native architecture jobs already passed")
    args = parser.parse_args()
    result = run_release_gate(rounds=3, include_native=not args.skip_native)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
