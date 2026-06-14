from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "native" / "standalone"


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
    assert result.stdout.strip() == "Mellow Programming Language 2.9.0 (Full Native C)"


def test_full_native_compiles_checks_and_runs_source(native_binary: Path) -> None:
    source = ROOT / "tests" / "fixtures" / "full_native_core.mellow"
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
    assert ran.stdout.splitlines() == ["30", "mellow", "3"]
