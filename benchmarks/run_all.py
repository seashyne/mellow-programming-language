from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from bench_suite.config import (
    BENCHMARKS,
    DEFAULT_MELLOW_BINARY,
    DEFAULT_STANDALONE_SOURCE,
    LOCAL_ZIG,
    PROFILES,
)
from bench_suite.report import render_markdown
from bench_suite.suite import run_suite


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"cannot encode {type(value).__name__}")


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


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
