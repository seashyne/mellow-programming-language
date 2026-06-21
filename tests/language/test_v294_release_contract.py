from __future__ import annotations

import json
from pathlib import Path

import mellowlang

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "spec" / "mellow-2.9.4-stability.json"
CORE_DOCS = ROOT / "docs" / "CORE_DOCS.md"


def test_release_version_is_2_9_4() -> None:
    assert mellowlang.__version__ == "2.9.4"


def test_patch_stability_manifest_exists() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["version"] == "2.9.4"
    assert manifest["status"] == "released"
    for gate in ("tests/core", "tests/language", "tests/native", "native-arm64-ci", "release-gate"):
        assert gate in manifest["required_gates"]


def test_core_docs_index_points_to_current_patch() -> None:
    text = CORE_DOCS.read_text(encoding="utf-8")
    assert "mellow-2.9.4-stability.json" in text


def test_release_gate_runs_native_suite() -> None:
    source = (ROOT / "src" / "mellowlang" / "release_gate.py").read_text(encoding="utf-8")
    assert '["tests/native"]' in source
