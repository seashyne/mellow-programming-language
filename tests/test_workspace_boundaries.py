from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MELLOW_SOURCE_ROOTS = {
    "benchmarks",
    "examples",
    "frameworks",
    "mellow_packages",
    "native",
    "project_template",
    "starter_packages",
    "stdlib",
    "tests",
}
ROOT_IMPLEMENTATION_FILES = {"main.py", "setup.py"}
IMPLEMENTATION_SUFFIXES = {".py", ".c", ".h", ".js", ".ts"}
ROOT_ARTIFACT_SUFFIXES = {".exe", ".pdb", ".dll", ".obj", ".lib", ".o", ".zip"}
STRUCTURE_DOC = "docs/PROJECT_STRUCTURE.md"


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def test_standalone_runtime_never_reaches_the_python_layer() -> None:
    offenders = [
        path
        for path in _tracked_files()
        if path.startswith("native/standalone/") and path.endswith((".c", ".h"))
    ]
    for path in offenders:
        text = (ROOT / path).read_text(encoding="utf-8", errors="ignore")
        assert "mellowlang" not in text, f"{path} references the Python layer"


def test_repository_root_stays_free_of_implementation_files() -> None:
    extras = [
        path
        for path in _tracked_files()
        if "/" not in path and Path(path).suffix in IMPLEMENTATION_SUFFIXES
    ]
    assert sorted(extras) == sorted(ROOT_IMPLEMENTATION_FILES)


def test_repository_root_stays_free_of_build_artifacts() -> None:
    artifacts = [
        path
        for path in _tracked_files()
        if "/" not in path and Path(path).suffix.lower() in ROOT_ARTIFACT_SUFFIXES
    ]
    assert not artifacts, f"commit build output under an ignored directory instead: {artifacts}"


def test_mellow_sources_live_only_under_declared_roots() -> None:
    stray = sorted(
        {
            path.split("/", 1)[0]
            for path in _tracked_files()
            if Path(path).suffix in {".mellow", ".mel"}
        }
        - MELLOW_SOURCE_ROOTS
    )
    assert not stray, f"Mellow sources outside declared roots: {stray}"


def test_registry_fixture_tree_has_no_installed_output() -> None:
    offenders = [
        path for path in _tracked_files() if path.startswith("mellow_packages/registry/") and "/installed/" in path
    ]
    assert not offenders, f"installed package output committed under registry: {offenders}"


def test_every_top_level_directory_is_documented() -> None:
    documented = (ROOT / STRUCTURE_DOC).read_text(encoding="utf-8")
    tracked_dirs = sorted({path.split("/", 1)[0] for path in _tracked_files() if "/" in path})
    missing = [name for name in tracked_dirs if f"`{name}" not in documented]
    assert not missing, f"add {missing} to {STRUCTURE_DOC}"


def test_every_native_surface_is_documented() -> None:
    documented = (ROOT / STRUCTURE_DOC).read_text(encoding="utf-8")
    surfaces = {
        path.split("/")[1]
        for path in _tracked_files()
        if path.startswith("native/") and len(path.split("/")) > 2
    }
    missing = sorted(name for name in surfaces if f"`native/{name}/" not in documented)
    assert not missing, f"native/ holds several surfaces; document {missing} in {STRUCTURE_DOC}"
