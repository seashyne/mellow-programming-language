from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC_ENTRY = ROOT / "SPEC.md"
V3_PLAN = ROOT / "docs" / "V3_STABILITY_PLAN.md"
V3_SPEC = ROOT / "docs" / "LANGUAGE_SPEC_3_0.md"
PARITY = ROOT / "docs" / "RUNTIME_PARITY_3_0.md"
V3_MANIFEST = ROOT / "spec" / "mellow-3.0-stability.json"
BASELINE_MANIFEST = ROOT / "spec" / "mellow-2.9-core.json"


def test_top_level_spec_declares_current_baseline_and_v3_track() -> None:
    text = SPEC_ENTRY.read_text(encoding="utf-8")
    assert "docs/LANGUAGE_SPEC_2_9.md" in text
    assert "spec/mellow-2.9-core.json" in text
    assert "docs/V3_STABILITY_PLAN.md" in text
    assert "docs/LANGUAGE_SPEC_3_0.md" in text
    assert "docs/RUNTIME_PARITY_3_0.md" in text
    assert "spec/mellow-3.0-stability.json" in text
    assert "A feature is not stable until it has a spec entry and an automated test." in text


def test_v3_manifest_is_planned_stability_release() -> None:
    manifest = json.loads(V3_MANIFEST.read_text(encoding="utf-8"))
    baseline = json.loads(BASELINE_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["language"] == "Mellow Programming Language"
    assert manifest["target_version"] == "3.0"
    assert manifest["status"] == "planned"
    assert manifest["goal"] == "Language Stability Release"
    assert manifest["baseline"]["version"] == baseline["version"]
    assert manifest["baseline"]["manifest"] == "spec/mellow-2.9-core.json"
    assert manifest["draft_spec"] == "docs/LANGUAGE_SPEC_3_0.md"
    assert manifest["runtime_parity"] == "docs/RUNTIME_PARITY_3_0.md"
    assert manifest["compiler"]["documentation"] == "docs/COMPILER_V3.md"
    assert manifest["compiler"]["legacy_fallback"] is False
    assert "tests/core" in manifest["required_gates"]
    assert "tests/language" in manifest["required_gates"]


def test_v3_plan_names_required_workstreams_and_release_rule() -> None:
    text = V3_PLAN.read_text(encoding="utf-8")
    for heading in (
        "## Definition Of Done",
        "### 1. Language Specification",
        "### 2. Runtime Parity",
        "### 3. Tests",
        "### 4. Tooling",
        "### 5. Ecosystem",
        "### 6. Interop",
        "## Release Rule",
    ):
        assert heading in text
    assert "specification or stability plan" in text
    assert "automated test" in text
    assert "user-facing documentation" in text


def test_v3_draft_spec_classifies_stable_surfaces() -> None:
    text = V3_SPEC.read_text(encoding="utf-8")
    for label in ("core", "extended", "experimental"):
        assert f"`{label}`" in text
    assert "Python VM is the reference implementation" in text
    assert "Interop must be deny-by-default" in text


def test_runtime_parity_matrix_marks_native_gaps_honestly() -> None:
    text = PARITY.read_text(encoding="utf-8")
    assert "| Surface | Python VM | Native C VM | v3 Status | Notes |" in text
    assert "| Debugger | pass | partial | tooling |" in text
    assert "| Agents | pass | unsupported | experimental |" in text
