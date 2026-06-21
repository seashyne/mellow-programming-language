from __future__ import annotations

from pathlib import Path

import pytest

from mellowlang.compiler import Compiler
from mellowlang.constants import Op
from mellowlang.error_core import MellowLangRuntimeError
from mellowlang.standalone_image import compile_source_to_standalone_image


ROOT = Path(__file__).resolve().parents[2]


def test_core_and_standalone_share_the_v3_pipeline() -> None:
    fixture = ROOT / "tests" / "fixtures" / "full_native_core.mellow"
    source = fixture.read_text(encoding="utf-8")

    program = Compiler().compile(source, filename=str(fixture))
    image = compile_source_to_standalone_image(source, filename=str(fixture))

    assert program.pipeline.startswith("v3-ir-")
    assert image.pipeline == program.pipeline


def test_package_import_lowers_to_v3_import_opcode() -> None:
    program = Compiler().compile('import "pkg:core-print" as out\n')
    assert (Op.IMPORT, "pkg:core-print", "out") in program.bytecode


def test_unsupported_extended_syntax_never_falls_back() -> None:
    source = "try:\n    print(1)\ncatch err:\n    print(err)\n"
    with pytest.raises(MellowLangRuntimeError) as exc:
        Compiler().compile(source)

    assert exc.value.error_type == "COMPILER"
    assert "Compiler v3 does not support" in exc.value.message
