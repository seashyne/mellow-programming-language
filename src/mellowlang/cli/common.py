from __future__ import annotations

import json
import os
import re
import sys
from importlib import import_module
from pathlib import Path
from typing import Any

class _LazyAttr:
    def __init__(self, module_name: str, attr_name: str):
        self._module_name = module_name
        self._attr_name = attr_name
        self._value: Any | None = None

    def _resolve(self) -> Any:
        if self._value is None:
            self._value = getattr(import_module(self._module_name), self._attr_name)
        return self._value

    def __call__(self, *args, **kwargs):
        return self._resolve()(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._resolve(), name)

    def __fspath__(self) -> str:
        return os.fspath(self._resolve())

    def __str__(self) -> str:
        return str(self._resolve())

    def __repr__(self) -> str:
        return repr(self._resolve())


def _lazy_attr(module_name: str, attr_name: str) -> _LazyAttr:
    return _LazyAttr(module_name, attr_name)


# ============================================================

def _cli_palette() -> dict[str, str]:
    if not _supports_ansi():
        return {"reset": "", "red": "", "green": "", "yellow": "", "blue": "", "bold": "", "dim": ""}
    return {
        "reset": "\033[0m",
        "red": "\033[31m",
        "green": "\033[32m",
        "yellow": "\033[33m",
        "blue": "\033[34m",
        "bold": "\033[1m",
        "dim": "\033[2m",
    }


def _cli_icon(kind: str) -> str:
    return {"ok": "OK", "info": "*", "warn": "!", "error": "ERR", "hint": ">"}.get(kind, "*")


def _cli_line(message: str, *, kind: str = "info", file=None) -> None:
    pal = _cli_palette()
    color = {"ok": pal["green"], "info": pal["blue"], "warn": pal["yellow"], "error": pal["red"], "hint": pal["dim"]}.get(kind, "")
    print(f"{color}{_cli_icon(kind)}{pal['reset']} {message}", file=file or sys.stdout)


def _looks_like_script_path(value: str | None) -> bool:
    if not value or value.startswith('-'):
        return False
    low = value.lower()
    return low.endswith('.mellow') or low.endswith('.mel')


def _argv_prefers_direct_run(argv: list[str]) -> bool:
    return bool(argv) and _looks_like_script_path(argv[0])


def _prompt_yes_no(prompt: str, *, default: bool = True) -> bool:
    if not sys.stdin.isatty():
        return default
    suffix = 'Y/n' if default else 'y/N'
    try:
        raw = input(f"{prompt} [{suffix}]: ").strip().lower()
    except EOFError:
        return default
    if not raw:
        return default
    return raw in {"y", "yes"}

def _start_lsp(*, show_banner: bool | None = None) -> int:
    from ..lsp_server import start_lsp  # lazy import (pygls optional)
    return int(start_lsp(show_banner=show_banner) or 0)


def _supports_ansi() -> bool:
    if not sys.stdout.isatty():
        return False
    if os.name != "nt":
        return True
    env = os.environ
    return any(k in env for k in ("WT_SESSION", "TERM", "ANSICON", "ConEmuANSI")) or (
        "vscode" in env.get("TERM_PROGRAM", "").lower()
    )


def _print_pretty_error(
    err: Exception,
    filename: str | None = None,
    source_lines: list[str] | None = None,
    *,
    use_color: bool | None = None,
) -> None:
    """
    Frinds-style error formatter:
      Error: <TYPE> at <file>:<line>:<col>
        <message>
        <code frame + caret>
    """
    msg = getattr(err, "message", None) or str(err)

    if use_color is None:
        use_color = _supports_ansi()

    if use_color:
        RED = "\033[31m"
        YELLOW = "\033[33m"
        DIM = "\033[2m"
        RESET = "\033[0m"
    else:
        RED = YELLOW = DIM = RESET = ""

    # ---- Pull structured fields if present (preferred) ----
    err_type = getattr(err, "error_type", None)
    line_no = getattr(err, "line_num", None)
    col = getattr(err, "col", None)
    fn = getattr(err, "filename", None) or filename

    # ---- Fallback: infer line/col from message (ParseError, etc.) ----
    snippet = None
    if line_no is None:
        m = re.search(r"\bline\s+(\d+)\b", msg)
        if m:
            line_no = int(m.group(1))
    if fn is None:
        # e.g. "RUNTIME at test.fds:46: division by zero"
        m = re.search(r"\bat\s+(.+?):(\d+)(?::(\d+))?\b", msg)
        if m:
            fn = m.group(1)
            if line_no is None:
                line_no = int(m.group(2))
            if m.group(3) and col is None:
                col = int(m.group(3))
    # snippet often appears after ":" in messages like "... at line 6: kee i"
    m = re.search(r"\bline\s+\d+\s*:\s*(.+)$", msg)
    if m:
        snippet = m.group(1).strip()

    # --- Friendly hints (DX) ---
    # Add small, deterministic hints for common mistakes.
    try:
        if (getattr(err, 'error_type', None) in (None, 'SYNTAX') and 'Unknown statement' in msg):
            # Common case: user wrote a function call as a statement, or used named args.
            if snippet and '(' in snippet and ')' in snippet:
                msg += "\nHint: you can call functions as statements (game-friendly)."
                if '=' in snippet:
                    msg += "\nHint: named args are supported, e.g. file_write(\"a.txt\", \"hi\", mode=\"w\")."
                msg += "\nTip: if this still errors, try `call(file_write, ...)` (function form)."
    except Exception:
        pass

    if not err_type:
        # ParseError usually means SYNTAX, everything else ERROR
        err_type = "SYNTAX" if err.__class__.__name__ in ("ParseError",) else "ERROR"

    # Compute column from snippet if possible
    if source_lines and line_no and col is None and snippet:
        try:
            line_text = source_lines[int(line_no) - 1]
            idx = line_text.find(snippet)
            if idx >= 0:
                col = idx + 1
        except Exception:
            pass
    if col is None:
        col = 1

    # ---- Header (match Frinds look) ----
    loc = ""
    if fn and line_no:
        loc = f"{fn}:{line_no}:{col}"
    elif fn and line_no is None:
        loc = str(fn)
    elif line_no:
        loc = f"line {line_no}:{col}"

    print(f"{RED}Error:{RESET} {err_type}" + (f" at {loc}" if loc else ""))
    print(f"  {msg}")

    # ---- Call stack (if present) ----
    trace = getattr(err, "trace", None)
    if trace:
        print(f"{DIM}Call Stack:{RESET}")
        for fr in reversed(trace):
            nm = fr.get("name", "<frame>")
            ffn = fr.get("filename", fn) or "<script>"
            ln = fr.get("line")
            cc = fr.get("col")
            floc = ffn if ln is None else f"{ffn}:{ln}" + (f":{cc}" if cc else "")
            print(f"  at {nm} ({floc})")

    # ---- Code frame ----
    if not source_lines or not line_no:
        return
    try:
        ln = int(line_no)
    except Exception:
        return
    if ln < 1 or ln > len(source_lines):
        return

    i = ln - 1
    lo = max(0, i - 1)
    hi = min(len(source_lines) - 1, i + 1)
    for j in range(lo, hi + 1):
        prefix = ">" if j == i else " "
        print(f"{prefix} {j+1:3d} | {source_lines[j].rstrip()}")
        if j == i:
            caret_pos = max(1, min(int(col), len(source_lines[j]) + 1))
            print(f"    | {' '*(caret_pos-1)}{YELLOW}^{RESET}")


def _prog() -> str:
    base = os.path.basename(sys.argv[0]) or "mellow"
    return os.path.splitext(base)[0]

def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")

def _find_project_root(start: Path) -> Path | None:
    """Find nearest parent dir containing mellow.json."""
    try:
        p = start.resolve()
    except Exception:
        p = start
    if p.is_file():
        p = p.parent
    for parent in [p] + list(p.parents):
        if (parent / "mellow.json").exists() or (parent / "mellow.toml").exists() or (parent / "mellow.pkg.json").exists():
            return parent
    return None

def _json_print(obj: Any) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(text.encode("utf-8", errors="replace") + b"\n")

# ----------------------------
# Command handlers
