"""Line-level reading of mellow-web source: header/state/call patterns,
comment and import stripping, and argument splitting."""

from __future__ import annotations

import re

from .model import MellowWebError


_HEADER_RE = re.compile(r"^(page|component)\s+([A-Za-z_][A-Za-z0-9_]*)\s*$")
_STATE_RE = re.compile(r"^state\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$")
_CALL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.]*)\s*(?:\((.*)\))?\s*$")
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _strip_imports_and_comments(lines: list[str]) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    for idx, raw in enumerate(lines, start=1):
        if "\t" in raw:
            raise MellowWebError(f"line {idx}: tabs are not supported in mellow-web indentation")
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("use ") or stripped.startswith("import "):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        out.append((idx, indent, raw.strip()))
    return out


def _split_args(raw: str) -> tuple[list[str], dict[str, str]]:
    parts = _split_top_level(raw)
    args: list[str] = []
    props: dict[str, str] = {}
    for part in parts:
        if not part:
            continue
        key, value = _split_named_arg(part)
        if key:
            props[key] = value
        else:
            args.append(part.strip())
    return args, props


def _split_top_level(raw: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    depth = 0
    escape = False
    for ch in raw:
        if quote:
            current.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            continue
        if ch in {"'", '"'}:
            quote = ch
            current.append(ch)
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return parts


def _split_named_arg(part: str) -> tuple[str | None, str]:
    quote: str | None = None
    depth = 0
    escape = False
    for idx, ch in enumerate(part):
        if quote:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            continue
        if ch in {"'", '"'}:
            quote = ch
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == ":" and depth == 0:
            key = part[:idx].strip()
            if _IDENT_RE.match(key):
                return key, part[idx + 1 :].strip()
    return None, part
