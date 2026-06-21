from __future__ import annotations

import json
from pathlib import Path

import mellowlang

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "spec" / "mellow-2.9.3-stability.json"
EXPERIMENTAL = ROOT / "docs" / "experimental" / "README.md"
CORE_DOCS = ROOT / "docs" / "CORE_DOCS.md"


def test_release_version_is_2_9_3() -> None:
    assert mellowlang.__version__ == "2.9.3"


def test_patch_stability_manifest_exists() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["version"] == "2.9.3"
    assert manifest["status"] == "released"
    assert "tests/core" in manifest["required_gates"]
    assert "tests/language" in manifest["required_gates"]
    assert "release-gate" in manifest["required_gates"]
    assert "legacy_boundaries" not in manifest
    assert manifest["experimental_index"] == "docs/experimental/README.md"


def test_core_docs_index_points_to_stable_and_experimental_split() -> None:
    text = CORE_DOCS.read_text(encoding="utf-8")
    assert "STABLE_CORE.md" in text
    assert "experimental/README.md" in text
    assert "mellow-2.9.3-stability.json" in text


def test_removed_compatibility_modules_do_not_return() -> None:
    assert not (ROOT / "src" / "mellowlang" / "compiler" / "legacy.py").exists()
    assert not (ROOT / "src" / "mellowlang" / "host" / "legacy.py").exists()
    assert not (ROOT / "src" / "mellowlang" / "vm" / "legacy.py").exists()
    assert not (ROOT / "docs" / "LEGACY_BOUNDARIES.md").exists()


def test_direct_script_mode_is_not_advertised() -> None:
    parser_text = (ROOT / "src" / "mellowlang" / "cli" / "parser.py").read_text(encoding="utf-8")
    assert "_build_legacy_parser" not in parser_text
    assert "--legacy" not in parser_text


def test_experimental_index_lists_agents_and_mmg() -> None:
    text = EXPERIMENTAL.read_text(encoding="utf-8")
    assert "AGENT_REGISTRY.md" in text
    assert "MMG_RUNTIME.md" in text
    assert (ROOT / "docs" / "experimental" / "AGENT_REGISTRY.md").is_file()
    assert (ROOT / "docs" / "experimental" / "MMG_RUNTIME.md").is_file()
