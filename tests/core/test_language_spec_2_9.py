from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path

from mellowlang import __version__
from mellowlang.compiler import Compiler
from mellowlang.vm import MellowVM, RunConfig


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "spec" / "mellow-2.9-core.json"
DOCUMENT = ROOT / "docs" / "LANGUAGE_SPEC_2_9.md"


def test_language_spec_manifest_is_frozen_and_versioned() -> None:
    spec = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert spec["language"] == "Mellow Programming Language"
    assert spec["version"] == "2.9"
    assert spec["profile"] == "core"
    assert spec["status"] == "frozen"
    assert __version__.startswith(f'{spec["version"]}.')
    assert spec["normative_document"] == "docs/LANGUAGE_SPEC_2_9.md"


def test_frozen_spec_and_conformance_fixtures_match_locked_digests() -> None:
    spec = json.loads(MANIFEST.read_text(encoding="utf-8"))
    locked_files = (
        (spec["normative_document"], spec["normative_document_sha256"]),
        (spec["conformance_fixture"], spec["conformance_fixture_sha256"]),
        (spec["conformance_output_fixture"], spec["conformance_output_sha256"]),
    )
    for relative_path, expected_digest in locked_files:
        payload = (ROOT / relative_path).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == expected_digest, relative_path


def test_normative_spec_contains_required_contract_sections() -> None:
    text = DOCUMENT.read_text(encoding="utf-8")
    for heading in (
        "## 1. Compatibility Contract",
        "## 3. Lexical Grammar",
        "## 4. Program Grammar",
        "## 5. Expression Grammar",
        "## 8. Standard Built-ins",
        "## 10. Core Conformance Program",
        "## 11. Non-Core Syntax",
        "## 12. Change Process",
    ):
        assert heading in text


def test_python_runtime_matches_frozen_core_conformance_output() -> None:
    spec = json.loads(MANIFEST.read_text(encoding="utf-8"))
    fixture = ROOT / spec["conformance_fixture"]
    program = Compiler().compile(
        fixture.read_text(encoding="utf-8"),
        filename=str(fixture),
    )
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        MellowVM().run(program, config=RunConfig(engine="py"))
    assert output.getvalue().splitlines() == spec["conformance_output"]
