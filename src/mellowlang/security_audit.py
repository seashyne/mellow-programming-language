from __future__ import annotations

import io
import json
import shutil
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from .agents.policy import PolicyEngine
from .agents.tools import builtin_tool_registry
from .compiler.compiler import Compiler
from .package_manager import (
    package_authors,
    read_manifest,
    verify_signed_manifest,
)
from .vm import MellowVM, RunConfig


ROOT = Path(__file__).resolve().parents[2]


def _check(name: str, ok: bool, detail: str, severity: str = "error") -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "severity": severity, "detail": detail}


def audit_sandbox() -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    work_root = ROOT / "build" / "security-audit-work"
    work_root.mkdir(parents=True, exist_ok=True)
    td = tempfile.mkdtemp(prefix="run-", dir=work_root)
    try:
        cwd = Path(td)
        source = 'save {"x": 1} into "../escape"\n'
        program = Compiler().compile(source, filename="<audit-sandbox>")
        try:
            with redirect_stdout(io.StringIO()):
                MellowVM().run(program, config=RunConfig(max_steps=1000, storage_dir=str(cwd / "saves")))
            checks.append(_check("sandbox.path_traversal", False, "parent traversal write was not blocked"))
        except Exception as exc:
            text = str(exc).lower()
            checks.append(_check("sandbox.path_traversal", "travers" in text or "blocked" in text or "sandbox" in text, str(exc)))
    finally:
        shutil.rmtree(td, ignore_errors=True)
    return checks


def audit_ai_tool_policy() -> list[dict[str, Any]]:
    registry = builtin_tool_registry()
    tool = registry.get("search.docs")
    policy = PolicyEngine()
    denied = policy.check_tool("search.docs", getattr(tool, "capabilities", []))
    allowed_policy = PolicyEngine(allowed_tools=["search.docs"])
    allowed = allowed_policy.check_tool("search.docs", getattr(tool, "capabilities", []))
    return [
        _check("ai_tools.default_deny", not denied.allowed, denied.reason),
        _check("ai_tools.explicit_allow", allowed.allowed, allowed.reason),
    ]


def audit_package_trust(starter_root: Path | None = None) -> list[dict[str, Any]]:
    root = starter_root or (ROOT / "starter_packages")
    checks: list[dict[str, Any]] = []
    package_dirs = sorted(path for path in root.iterdir() if path.is_dir() and (path / "mellow.toml").exists()) if root.exists() else []
    checks.append(_check("packages.starter_root", bool(package_dirs), f"{len(package_dirs)} starter package(s) discovered"))
    for package_dir in package_dirs:
        try:
            manifest = read_manifest(package_dir)
            authors = package_authors(manifest)
            checks.append(_check(f"packages.{package_dir.name}.authors", bool(authors), ", ".join(authors) or "missing authors"))
            checks.append(_check(f"packages.{package_dir.name}.official_flag", bool(manifest.get("official")), "official=true required for starter packages", severity="warn"))
            sha = str(manifest.get("sha256") or manifest.get("archive_sha256") or "")
            if sha:
                verify = verify_signed_manifest(manifest, sha)
                checks.append(_check(f"packages.{package_dir.name}.signature", bool(verify.get("ok")), json.dumps(verify, ensure_ascii=False), severity="warn"))
            else:
                checks.append(_check(f"packages.{package_dir.name}.signature", False, "no archive sha256 in source manifest; release gate signs archives", severity="warn"))
        except Exception as exc:
            checks.append(_check(f"packages.{package_dir.name}", False, str(exc)))
    return checks


def run_security_audit(*, include_packages: bool = True) -> dict[str, Any]:
    checks = []
    checks.extend(audit_sandbox())
    checks.extend(audit_ai_tool_policy())
    if include_packages:
        checks.extend(audit_package_trust())
    errors = [check for check in checks if not check["ok"] and check["severity"] == "error"]
    warnings = [check for check in checks if not check["ok"] and check["severity"] == "warn"]
    return {
        "ok": not errors,
        "checks": checks,
        "errors": len(errors),
        "warnings": len(warnings),
    }
