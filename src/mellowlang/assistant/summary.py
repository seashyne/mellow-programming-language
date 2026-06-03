from __future__ import annotations

from typing import List

from .. import __version__
from ..analyzer import AssistantReport


ASSISTANT_VERSION = "0.1.1"


def render_human(report: AssistantReport) -> str:
    out: List[str] = []
    out.append(f"Mellow Code Assistant (v{ASSISTANT_VERSION} / Mellow {__version__}) — {report.filename}")
    out.append("")

    if report.skills:
        out.append("Skills:")
        for s in report.skills:
            params = ", ".join(s.get("params") or [])
            out.append(f"  - {s['name']}({params})  (line {s['line']})")
        out.append("")

    if report.events:
        out.append("Events:")
        for e in report.events:
            params = ", ".join(e.get("params") or [])
            out.append(f"  - on {e['event']}({params})  (line {e['line']})")
        out.append("")

    if report.globals:
        out.append("Top-level vars:")
        for g in report.globals:
            out.append(f"  - {g['kind']}: {', '.join(g['names'])}  (line {g['line']})")
        out.append("")

    if report.top_calls:
        out.append("Top calls (rough):")
        for name, n in report.top_calls[:10]:
            out.append(f"  - {name}() x{n}")
        out.append("")

    if report.hints:
        out.append("Hints:")
        for h in report.hints:
            out.append(f"  • {h}")
    else:
        out.append("Hints:")
        out.append("  • No obvious issues found.")

    return "\n".join(out) + "\n"
