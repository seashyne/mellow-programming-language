from __future__ import annotations

import json
import shutil
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from . import package_manager as pm
from .benchmarking import run_benchmarks
from .security_audit import run_security_audit


ROOT = Path(__file__).resolve().parents[2]
STARTER_ROOT = ROOT / "starter_packages"
GENERATED_STATE = {
    ".mellow_aliases.json",
    ".mellow_imports.json",
    ".mellow_runtime.json",
    "mellow.lock",
}
SYNC_FIELDS = (
    "name",
    "version",
    "entry",
    "description",
    "dependencies",
    "visibility",
    "authors",
    "license",
    "keywords",
    "badges",
    "official",
    "deprecated",
)


def _comparable(manifest: dict[str, Any], field: str) -> Any:
    if field in {"official", "deprecated"}:
        return bool(manifest.get(field, False))
    if field == "dependencies":
        return manifest.get(field) or {}
    if field in {"authors", "keywords", "badges"}:
        return manifest.get(field) or []
    return manifest.get(field)


def package_dirs(root: Path = STARTER_ROOT) -> list[Path]:
    return sorted(path for path in root.iterdir() if path.is_dir() and (path / "mellow.toml").exists()) if root.exists() else []


def check_manifest_sync(package_dir: Path) -> dict[str, Any]:
    json_path = package_dir / "mellow.pkg.json"
    if not json_path.exists():
        raise RuntimeError(f"{package_dir.name}: missing mellow.pkg.json compatibility manifest")
    toml_manifest = pm.read_manifest(package_dir / "mellow.toml")
    json_manifest = json.loads(json_path.read_text(encoding="utf-8"))
    mismatches = [field for field in SYNC_FIELDS if _comparable(toml_manifest, field) != _comparable(json_manifest, field)]
    if mismatches:
        raise RuntimeError(f"{package_dir.name}: manifest mismatch in {', '.join(mismatches)}")
    if not toml_manifest.get("official"):
        raise RuntimeError(f"{package_dir.name}: official starter package must set official=true")
    if not pm.package_authors(toml_manifest):
        raise RuntimeError(f"{package_dir.name}: official package must declare authors")
    return toml_manifest


def check_archive(package_dir: Path, archive: Path) -> str:
    result = pm.build_package_archive(package_dir, archive)
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
    for raw_name in names:
        path = PurePosixPath(raw_name.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts:
            raise RuntimeError(f"{package_dir.name}: unsafe archive path: {raw_name}")
        if any(part in GENERATED_STATE for part in path.parts):
            raise RuntimeError(f"{package_dir.name}: generated state leaked into archive: {raw_name}")
    if not names:
        raise RuntimeError(f"{package_dir.name}: package archive is empty")
    return str(result["sha256"])


def check_signature(manifest: dict[str, Any], sha256: str) -> None:
    signed = pm.sign_manifest(manifest, sha256)
    verification = pm.verify_signed_manifest(signed, sha256)
    if not verification.get("ok") or not verification.get("signed"):
        raise RuntimeError(f"{manifest.get('name')}: signature verification failed: {verification}")


def check_install_smoke(package_dir: Path, manifest: dict[str, Any], temp_root: Path) -> None:
    published = pm.publish_from_dir(package_dir)
    if published.get("error"):
        raise RuntimeError(f"{manifest.get('name')}: local publish failed: {published['error']}")
    installed = pm.install_package(str(manifest["name"]), str(manifest["version"]))
    if installed.get("error"):
        raise RuntimeError(f"{manifest.get('name')}: install smoke failed: {installed['error']}")
    entry = temp_root / "installed" / str(manifest["name"]) / "current" / "package" / str(manifest["entry"])
    if not entry.is_file():
        raise RuntimeError(f"{manifest.get('name')}: installed entry is missing: {manifest['entry']}")


def run_package_integrity_gate() -> dict[str, Any]:
    packages = package_dirs()
    if not packages:
        raise RuntimeError("no starter packages found")
    work_root = ROOT / ".mellow-release-gate-work"
    work_root.mkdir(parents=True, exist_ok=True)
    temp_root = work_root / f"run-{uuid.uuid4().hex[:12]}"
    temp_root.mkdir(parents=True, exist_ok=False)
    old_registry = pm.REGISTRY_ROOT
    old_installed = pm.INSTALLED_ROOT
    old_pkg_root = pm.PKG_ROOT
    rows: list[dict[str, Any]] = []
    pm.PKG_ROOT = temp_root
    pm.REGISTRY_ROOT = temp_root / "registry"
    pm.INSTALLED_ROOT = temp_root / "installed"
    try:
        for package_dir in packages:
            manifest = check_manifest_sync(package_dir)
            archive = temp_root / "archives" / f"{manifest['name']}-{manifest['version']}.mpkg"
            archive.parent.mkdir(parents=True, exist_ok=True)
            sha256 = check_archive(package_dir, archive)
            check_signature(manifest, sha256)
            check_install_smoke(package_dir, manifest, temp_root)
            rows.append({"name": manifest["name"], "version": manifest["version"], "sha256": sha256})
    finally:
        pm.PKG_ROOT = old_pkg_root
        pm.REGISTRY_ROOT = old_registry
        pm.INSTALLED_ROOT = old_installed
        shutil.rmtree(temp_root, ignore_errors=True)
    return {"ok": True, "packages": rows, "count": len(rows)}


def run_release_gate(*, rounds: int = 3) -> dict[str, Any]:
    benchmark = run_benchmarks(rounds=rounds)
    security = run_security_audit(include_packages=False)
    package_integrity = run_package_integrity_gate()
    ok = bool(benchmark.get("ok") and security.get("ok") and package_integrity.get("ok"))
    return {
        "ok": ok,
        "benchmark": benchmark,
        "sandbox": security,
        "package_integrity": package_integrity,
    }
