from __future__ import annotations

import os
import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "native" / "standalone"
SPEC = json.loads((ROOT / "spec" / "mellow-2.9-core.json").read_text(encoding="utf-8"))


def _compiler() -> str | None:
    return shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")


@pytest.fixture(scope="module")
def native_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    compiler = _compiler()
    if not compiler:
        pytest.skip("C compiler is not available")
    build = tmp_path_factory.mktemp("mellow-full-native")
    binary = build / ("mellow.exe" if os.name == "nt" else "mellow")
    command = [
        compiler,
        "-std=c99",
        "-I",
        str(NATIVE / "include"),
        str(NATIVE / "src" / "mellowrt_core.c"),
        str(NATIVE / "src" / "mellowrt_debug.c"),
        str(NATIVE / "src" / "mellowrt_platform.c"),
        str(NATIVE / "src" / "mellowc.c"),
        str(NATIVE / "src" / "mellowrt_main.c"),
        "-o",
        str(binary),
        "-lm",
    ]
    built = subprocess.run(command, capture_output=True, text=True, check=False)
    assert built.returncode == 0, built.stderr
    return binary


def test_full_native_version_has_no_python_runtime(native_binary: Path) -> None:
    result = subprocess.run(
        [str(native_binary), "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "Mellow Programming Language 2.9.4 (Full Native C)"


def test_full_native_reports_runtime_platform(native_binary: Path) -> None:
    result = subprocess.run(
        [str(native_binary), "--runtime-info"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    info = json.loads(result.stdout)
    assert info["runtime"] == "mellow-c"
    assert info["backend"] == "generic-c"
    assert info["architecture"] in {"x86", "x86_64", "arm32", "arm64", "unknown"}
    assert info["pointer_bits"] in {32, 64}
    assert isinstance(info["little_endian"], bool)
    assert isinstance(info["arm_neon_available"], bool)
    assert info["optimized_kernels"] is False


def test_full_native_compiles_checks_and_runs_source(native_binary: Path) -> None:
    source = ROOT / SPEC["conformance_fixture"]
    checked = subprocess.run(
        [str(native_binary), "check", str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stderr
    assert "native-c" in checked.stdout

    ran = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.splitlines() == SPEC["conformance_output"]
