from __future__ import annotations

import argparse
import json
from pathlib import Path

from native_compare.compare import run_compare


ROOT = Path(__file__).resolve().parents[2]


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
