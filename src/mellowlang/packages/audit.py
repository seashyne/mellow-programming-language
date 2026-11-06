from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .manifest import read_manifest
from .metadata import HOST_DEP_SENTINELS, normalize_name
from .project import _repo_registry_root, _repo_starter_packages_root


def _audit_package_dir(package_dir: Path, repo_root: Path) -> Dict[str, Any]:
    from ..compiler import Compiler

    issues: list[dict[str, str]] = []
    manifest: Dict[str, Any] = {}
    name = package_dir.name
    try:
        manifest = read_manifest(package_dir)
        name = str(manifest.get("name") or package_dir.name)
    except Exception as exc:
        issues.append({"severity": "error", "code": "manifest", "message": str(exc)})

    toml_path = package_dir / "mellow.toml"
    json_path = package_dir / "mellow.pkg.json"
    if toml_path.exists() and json_path.exists():
        try:
            toml_manifest = read_manifest(toml_path)
            json_manifest = read_manifest(json_path)
            for key in ("name", "version", "entry", "description", "authors", "license", "keywords", "badges", "official", "visibility", "dependencies"):
                if toml_manifest.get(key) != json_manifest.get(key):
                    issues.append({"severity": "error", "code": "manifest_sync", "message": f"{key} differs between mellow.toml and mellow.pkg.json"})
        except Exception as exc:
            issues.append({"severity": "error", "code": "manifest_sync", "message": str(exc)})
    elif toml_path.exists() != json_path.exists():
        issues.append({"severity": "warn", "code": "manifest_compat", "message": "package should ship both mellow.toml and mellow.pkg.json"})

    entry_ok = False
    entry = str(manifest.get("entry") or "src/main.mel")
    entry_path = package_dir / entry
    if not entry_path.exists():
        issues.append({"severity": "error", "code": "entry_missing", "message": f"missing entry: {entry}"})
    elif entry_path.suffix not in {".mel", ".mellow"}:
        issues.append({"severity": "error", "code": "entry_language", "message": f"runtime package entry must be .mel/.mellow: {entry}"})
    else:
        try:
            Compiler().compile(entry_path.read_text(encoding="utf-8"), filename=str(entry_path))
            entry_ok = True
        except Exception as exc:
            issues.append({"severity": "error", "code": "entry_compile", "message": str(exc)})

    python_sources = [
        path for path in package_dir.rglob("*.py")
        if "__pycache__" not in set(path.relative_to(package_dir).parts)
    ]
    for path in python_sources:
        issues.append({"severity": "error", "code": "python_source", "message": f"runtime package must not ship Python source: {path.relative_to(package_dir)}"})

    dependencies = manifest.get("dependencies") if isinstance(manifest, dict) else {}
    dependency_rows: list[dict[str, Any]] = []
    if isinstance(dependencies, dict):
        for dep_name, dep_spec in dependencies.items():
            dep = normalize_name(str(dep_name))
            spec = str(dep_spec)
            is_host = spec.strip().lower() in HOST_DEP_SENTINELS
            starter_exists = (_repo_starter_packages_root() / dep).exists()
            registry_exists = (_repo_registry_root() / dep).exists()
            resolved = is_host or starter_exists or registry_exists
            dependency_rows.append({"name": dep, "spec": spec, "kind": "host" if is_host else "package", "resolved": resolved})
            if not resolved:
                issues.append({"severity": "error", "code": "dependency_missing", "message": f"dependency not found locally: {dep}"})

    ok = not any(issue["severity"] == "error" for issue in issues)
    try:
        rel = str(package_dir.relative_to(repo_root))
    except ValueError:
        rel = str(package_dir)
    return {
        "name": name,
        "version": str(manifest.get("version") or "") if manifest else "",
        "path": rel,
        "entry": entry,
        "entry_ok": entry_ok,
        "native_ready": ok and entry_path.suffix in {".mel", ".mellow"} and not python_sources,
        "dependencies": dependency_rows,
        "issues": issues,
        "ok": ok,
    }

def _audit_package_sources(include_registry: bool = True, all_versions: bool = False) -> list[Path]:
    roots: list[Path] = []
    starter = _repo_starter_packages_root()
    if starter.exists():
        roots.extend(sorted(path for path in starter.iterdir() if path.is_dir() and (path / "mellow.toml").exists()))
    if include_registry:
        registry = _repo_registry_root()
        if registry.exists():
            for package_root in sorted(path for path in registry.iterdir() if path.is_dir()):
                versions = sorted(path for path in package_root.iterdir() if path.is_dir() and (path / "mellow.toml").exists())
                if all_versions:
                    roots.extend(versions)
                elif versions:
                    roots.append(versions[-1])
    return roots

def audit_packages(*, include_registry: bool = True, all_versions: bool = False) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[2]
    rows = [_audit_package_dir(path, repo_root) for path in _audit_package_sources(include_registry=include_registry, all_versions=all_versions)]
    errors = sum(1 for row in rows for issue in row.get("issues", []) if issue.get("severity") == "error")
    warnings = sum(1 for row in rows for issue in row.get("issues", []) if issue.get("severity") == "warn")
    native_ready = sum(1 for row in rows if row.get("native_ready"))
    return {
        "ok": errors == 0,
        "count": len(rows),
        "native_ready": native_ready,
        "errors": errors,
        "warnings": warnings,
        "include_registry": include_registry,
        "all_versions": all_versions,
        "items": rows,
    }

