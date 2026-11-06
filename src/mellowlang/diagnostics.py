from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .compiler import Compiler
from .error_core import MellowLangRuntimeError
from .lint import lint_source

KNOWN_HOST_MODULES = {
    "ai",
    "canvas",
    "chan",
    "data",
    "game",
    "gc",
    "io",
    "json",
    "ledger",
    "list",
    "map",
    "math",
    "money",
    "sdk",
    "storage",
    "string",
    "sys",
    "thread",
    "time",
}


@dataclass(frozen=True)
class DiagnosticHint:
    title: str
    detail: str
    action: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class MellowDiagnostic:
    kind: str
    message: str
    severity: str
    line: int | None = None
    col: int | None = None
    end_line: int | None = None
    end_col: int | None = None
    filename: str | None = None
    code: str | None = None
    source: str = "mellow"
    excerpt: str | None = None
    hints: tuple[DiagnosticHint, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["hints"] = [hint.to_dict() for hint in self.hints]
        return data


def _line_excerpt(source: str, line: int | None) -> str | None:
    if line is None or line <= 0:
        return None
    lines = source.splitlines()
    if line > len(lines):
        return None
    return lines[line - 1]


def _infer_code(kind: str, message: str) -> str:
    text = f"{kind} {message}".lower()
    if "syntax" in text or "parser" in text or "indent" in text or "must end with ':'" in text:
        return "E001"
    if "undefined" in text or "used before declaration" in text or "unknown variable" in text:
        return "E101"
    if "sandbox" in text or "not allowed" in text or "budget" in text:
        return "E201"
    return "E000"


def _hints_for(kind: str, message: str, excerpt: str | None) -> tuple[DiagnosticHint, ...]:
    text = f"{kind} {message} {excerpt or ''}".lower()
    hints: list[DiagnosticHint] = []
    if "must end with ':'" in text or "expected ':'" in text:
        hints.append(DiagnosticHint(
            "Block header needs ':'",
            "Mellow block statements such as if, while, for, def, skill, and on open with a trailing colon.",
            "Add ':' at the end of the block header and keep the next line indented.",
        ))
    if "undefined" in text or "used before declaration" in text or "unknown variable" in text:
        hints.append(DiagnosticHint(
            "Name is not in scope",
            "The runtime cannot find a variable, function, or imported package alias with this name.",
            "Check spelling, declare it with let/var/keep, or import the package before using the alias.",
        ))
    if "package import not installed" in text or "missing imports" in text:
        hints.append(DiagnosticHint(
            "Package is not installed",
            "The source imports a package that is not present in mellow_packages/installed or the local registry.",
            "Run mellow diagnose-imports . or mellow add <package> from the project root.",
        ))
    if "syscall_failed" in text or "built-in call failed" in text:
        hints.append(DiagnosticHint(
            "Built-in arguments did not match",
            "A native host function rejected the argument count or value types.",
            "Check the function arity and convert values explicitly before calling the built-in.",
        ))
    if not hints:
        hints.append(DiagnosticHint(
            "Inspect the nearest source line",
            "The diagnostic includes the closest line/column available from the compiler or runtime.",
            "Run mellow assistant <file> --mode diagnose --json for a structured report.",
        ))
    return tuple(hints)


def diagnostic_from_exception(exc: Exception, *, source: str = "", filename: str | None = None) -> MellowDiagnostic:
    kind = getattr(exc, "error_type", exc.__class__.__name__).upper()
    message = getattr(exc, "message", str(exc))
    line = getattr(exc, "line_num", None)
    col = getattr(exc, "col", None)
    err_filename = getattr(exc, "filename", None) or filename
    excerpt = _line_excerpt(source, line)
    code = _infer_code(kind, message)
    return MellowDiagnostic(
        kind=kind,
        message=str(message),
        severity="error",
        line=line,
        col=col,
        end_line=line,
        end_col=(col + 1) if isinstance(col, int) else None,
        filename=err_filename,
        code=code,
        excerpt=excerpt,
        hints=_hints_for(kind, str(message), excerpt),
    )


def diagnostics_for_source(source: str, *, filename: str = "<script>", include_lints: bool = True) -> dict[str, Any]:
    diagnostics: list[MellowDiagnostic] = []
    compile_ok = True
    try:
        Compiler().compile(source, filename=filename)
    except Exception as exc:
        compile_ok = False
        diagnostics.append(diagnostic_from_exception(exc, source=source, filename=filename))

    if include_lints:
        try:
            for issue in lint_source(source):
                if not compile_ok and issue.kind == "SYNTAX":
                    continue
                if issue.kind == "UNDEFINED" and _is_known_dotted_host_warning(issue.message):
                    continue
                excerpt = _line_excerpt(source, issue.line)
                diagnostics.append(MellowDiagnostic(
                    kind=issue.kind,
                    message=issue.message,
                    severity={
                        "SYNTAX": "error",
                        "UNDEFINED": "warning",
                        "SHADOW": "warning",
                        "STYLE": "info",
                        "UNUSED": "hint",
                    }.get(issue.kind, "warning"),
                    line=issue.line,
                    col=issue.col,
                    end_line=issue.line,
                    end_col=(issue.col + 1) if isinstance(issue.col, int) else None,
                    filename=filename,
                    code=_infer_code(issue.kind, issue.message),
                    excerpt=excerpt,
                    hints=_hints_for(issue.kind, issue.message, excerpt),
                ))
        except Exception:
            pass

    payload = {
        "ok": compile_ok and not any(d.severity == "error" for d in diagnostics),
        "filename": filename,
        "compile_ok": compile_ok,
        "diagnostics": [diag.to_dict() for diag in diagnostics],
    }
    payload["ai_prompt"] = build_ai_diagnostic_prompt(payload)
    return payload


def _is_known_dotted_host_warning(message: str) -> bool:
    text = str(message or "")
    if "'" not in text or "." not in text:
        return False
    name = text.split("'", 2)[1]
    module = name.split(".", 1)[0]
    return module in KNOWN_HOST_MODULES


def build_ai_diagnostic_prompt(payload: dict[str, Any]) -> str:
    filename = payload.get("filename") or "<script>"
    lines = [f"You are the Mellow diagnostic assistant for {filename}."]
    lines.append("Explain the likely cause and propose the smallest safe fix.")
    for idx, diag in enumerate(payload.get("diagnostics") or [], start=1):
        loc = f"line {diag.get('line')}" if diag.get("line") else "unknown line"
        if diag.get("col"):
            loc += f", column {diag.get('col')}"
        lines.append(f"{idx}. [{diag.get('severity')}] {diag.get('kind')} {diag.get('code') or ''} at {loc}: {diag.get('message')}")
        if diag.get("excerpt"):
            lines.append(f"   source: {diag.get('excerpt')}")
        hints = diag.get("hints") or []
        if hints:
            lines.append(f"   hint: {hints[0].get('action')}")
    return "\n".join(lines)


__all__ = [
    "DiagnosticHint",
    "MellowDiagnostic",
    "build_ai_diagnostic_prompt",
    "diagnostic_from_exception",
    "diagnostics_for_source",
]
