from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Tuple

from ..parser import parse_program
from .. import ast as mast


@dataclass(frozen=True)
class AssistantReport:
    filename: str
    skills: List[Dict[str, Any]]
    events: List[Dict[str, Any]]
    globals: List[Dict[str, Any]]
    top_calls: List[Tuple[str, int]]
    hints: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _stmt_line(stmt: Any) -> int:
    return int(getattr(stmt, "_line", 0) or 0)


_CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def _collect_calls(source: str) -> List[Tuple[str, int]]:
    # Best-effort: we want *hints*, not perfect parsing.
    counts: Dict[str, int] = {}
    for m in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", source):
        name = m.group(1)
        # skip keywords that can look like calls in some styles
        if name in {
            "if",
            "for",
            "while",
            "loop",
            "skill",
            "on",
            "return",
            "do",
            "end",
            "try",
            "catch",
            "finally",
        }:
            continue
        counts[name] = counts.get(name, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:12]


def analyze_source(source: str, *, filename: str = "<script>") -> AssistantReport:
    """Analyze Mellow source code deterministically.

    This is **offline** and **sandbox-safe**: it only inspects the source text
    and the parsed AST. No network, no execution.
    """

    lines = source.splitlines()
    prog = parse_program(lines, filename=filename)

    skills: List[Dict[str, Any]] = []
    events: List[Dict[str, Any]] = []
    globals_: List[Dict[str, Any]] = []

    # top-level only for globals (keeps / assigns)
    for st in prog.body:
        if isinstance(st, mast.SkillDef):
            skills.append({"name": st.name, "params": list(st.params), "line": _stmt_line(st)})
        elif isinstance(st, mast.OnDef):
            events.append({"event": st.event, "params": list(st.params), "line": _stmt_line(st)})
        elif isinstance(st, mast.KeepStmt):
            globals_.append({"kind": "keep", "names": [st.name], "line": _stmt_line(st)})
        elif isinstance(st, mast.KeepMultiStmt):
            globals_.append({"kind": "keep", "names": list(st.names), "line": _stmt_line(st)})
        elif isinstance(st, mast.AssignStmt):
            globals_.append({"kind": "assign", "names": list(st.names), "line": _stmt_line(st)})

    top_calls = _collect_calls(source)

    # ---------- Hints (heuristics, deterministic) ----------
    hints: List[str] = []

    uses_storage = any(name.startswith("file_") or name.startswith("storage_") for name, _ in top_calls)
    if uses_storage:
        hints.append(
            "Storage/File APIs detected. If this runs in a modding sandbox, prefer `mellow run --storage-dir <dir>` and keep paths relative."
        )

    # deterministic RNG hint
    uses_rng = any(name in {"rand", "random", "rng_next", "rng_float", "rng_int"} for name, _ in top_calls)
    if uses_rng and not re.search(r"\brng_seed\s*\(", source):
        hints.append(
            "Random usage detected. For deterministic replay, seed explicitly (e.g. `rng_seed(123)` or pass `mellow run --seed 123`)."
        )

    # event-driven hint
    if events and not any(name in {"emit", "event_emit"} for name, _ in top_calls):
        hints.append(
            "You defined `on <event>` handlers. Make sure something emits those events (e.g. `emit(\"spawn\", ...)`)."
        )

    # large script hint
    if len(lines) > 400 and not skills:
        hints.append(
            "Large script without `skill` definitions. Consider splitting logic into skills for readability and better stack traces."
        )

    return AssistantReport(
        filename=filename,
        skills=sorted(skills, key=lambda d: d["line"]),
        events=sorted(events, key=lambda d: d["line"]),
        globals=sorted(globals_, key=lambda d: d["line"]),
        top_calls=top_calls,
        hints=hints,
    )
