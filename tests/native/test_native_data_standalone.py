"""Standalone C parity for the std.data read side.

JSONL/CSV streaming and the row transforms are deterministic, so the
standalone binary must print the same values as the Python reference engine.
Each case compiles one source twice and compares printed output; rows travel
through `json.encode` so containers compare without display differences.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import random
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from mellowlang.compiler import Compiler
from mellowlang.vm import MellowVM, RunConfig


ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "native" / "standalone"


def _compiler() -> str | None:
    return shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")


@pytest.fixture(scope="module")
def native_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    compiler = _compiler()
    if not compiler:
        pytest.skip("C compiler is not available")
    build = tmp_path_factory.mktemp("mellow-data-native")
    binary = build / ("mellow.exe" if os.name == "nt" else "mellow")
    command = [
        compiler,
        "-std=c99",
        "-I",
        str(NATIVE / "include"),
        "-I",
        str(ROOT / "native" / "sm" / "include"),
        str(NATIVE / "src" / "mellowrt_core.c"),
        str(NATIVE / "src" / "mellowrt_debug.c"),
        str(NATIVE / "src" / "mellowrt_ledger.c"),
        str(NATIVE / "src" / "mellowrt_money.c"),
        str(NATIVE / "src" / "mellowrt_platform.c"),
        str(NATIVE / "src" / "mellowrt_packages.c"),
        str(NATIVE / "src" / "mellowrt_scheduler.c"),
        str(NATIVE / "src" / "mellowrt_server.c"),
        str(NATIVE / "src" / "mellowrt_sm_cli.c"),
        str(NATIVE / "src" / "mellowrt_storage.c"),
        str(NATIVE / "src" / "mellowrt_syscalls.c"),
        str(NATIVE / "src" / "mellowc.c"),
        str(NATIVE / "src" / "mellowc_lexer.c"),
        str(NATIVE / "src" / "mellowc_modules.c"),
        str(NATIVE / "src" / "mellowc_parser.c"),
        str(ROOT / "native" / "sm" / "src" / "sm_native.c"),
        str(NATIVE / "src" / "mellowrt_main.c"),
        "-o",
        str(binary),
        "-lm",
    ]
    if os.name == "nt":
        command.append("-lws2_32")
    built = subprocess.run(command, capture_output=True, text=True, check=False)
    assert built.returncode == 0, built.stderr
    return binary


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "data"
    folder.mkdir()
    for name in ("records.jsonl", "records.csv"):
        shutil.copy(ROOT / "tests" / "data" / name, folder / name)
    (folder / "quoting.csv").write_text(
        'name,note,extra_col\r\n"a,b","line1\nline2",\r\n\r\n"say ""hi""",x\r\nplain\r\np,q,r,s\r\n',
        encoding="utf-8",
        newline="",
    )
    return tmp_path


def _write_case(source: str, cwd: Path) -> Path:
    script = cwd / "case.mellow"
    script.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")
    return script


def _run_native(binary: Path, source: str, cwd: Path, seed: int = 42) -> str:
    script = _write_case(source, cwd)
    result = subprocess.run(
        [str(binary), "run", str(script), "--seed", str(seed)],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return result.stdout


def _run_python(source: str, cwd: Path, *, seed: int = 42) -> str:
    program = Compiler().compile(textwrap.dedent(source).lstrip("\n"), filename="<native-data>")
    vm = MellowVM()
    output = io.StringIO()
    previous = os.getcwd()
    os.chdir(cwd)
    random.seed(seed)
    try:
        with contextlib.redirect_stdout(output):
            vm.run(program, config=RunConfig(engine="py", seed=seed))
    finally:
        os.chdir(previous)
    return output.getvalue()


def _same_json(left, right) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == pytest.approx(right, rel=1e-9, abs=1e-12)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_same_json(a, b) for a, b in zip(left, right))
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(_same_json(left[k], right[k]) for k in left)
    return left == right


def _assert_equivalent(native_output: str, python_output: str) -> None:
    native_lines = native_output.strip().splitlines()
    python_lines = python_output.strip().splitlines()
    assert len(native_lines) == len(python_lines), (native_lines, python_lines)
    for native_line, python_line in zip(native_lines, python_lines):
        if native_line == python_line:
            continue
        try:
            left = json.loads(native_line)
            right = json.loads(python_line)
        except ValueError:
            assert native_line == python_line, (native_line, python_line)
            continue
        assert _same_json(left, right), (native_line, python_line)


def _parity(binary: Path, source: str, cwd: Path) -> None:
    _assert_equivalent(_run_native(binary, source, cwd), _run_python(source, cwd))


def test_jsonl_stream_and_transforms_match_python(native_binary: Path, data_dir: Path) -> None:
    source = """
        let stream = data_open_jsonl("data/records.jsonl", 2)
        let first = data_next(stream)
        let sales = data_where(first, "kind", "==", "sale")
        println(get json.encode(first))
        println(get json.encode(sales))
        println(get json.encode(data_sum(sales, "amount")))
        println(get json.encode(data_info(stream)))
        let second = data_next(stream)
        println(get json.encode(second))
        println(get json.encode(data_info(stream)))
        println(get json.encode(data_next(stream)))
        println(get json.encode(data_info(stream)))
    """
    _parity(native_binary, source, data_dir)


def test_csv_quoting_and_projection_match_python(native_binary: Path, data_dir: Path) -> None:
    source = """
        let plain = data_open_csv("data/records.csv", 3)
        let rows = data_next(plain)
        println(get json.encode(rows))
        println(get json.encode(data_project(rows, ["id", "kind"])))
        println(get json.encode(data_info(plain)))
        println(get json.encode(data_close(plain)))
        println(get json.encode(data_close(plain)))
        let quoted = data_open_csv("data/quoting.csv", 10)
        let weird = data_next(quoted)
        println(get json.encode(weird))
        println(get json.encode(data_project(weird, ["name", "note"])))
        println(get json.encode(data_info(quoted)))
    """
    _parity(native_binary, source, data_dir)


def test_row_transforms_match_python(native_binary: Path, data_dir: Path) -> None:
    source = """
        let rows = [{"id": 1, "kind": "sale", "amount": 10, "tags": ["new", "paid"]}, {"id": 2, "kind": "refund", "amount": 2.5, "tags": ["review"]}, {"id": 3, "kind": "sale", "amount": 7}, "ignored"]
        let projected = data_project(rows, ["id", "missing"])
        let sales = data_where(rows, "kind", "==", "sale")
        let tagged = data_where(rows, "tags", "contains", "paid")
        let large = data_where(rows, "amount", ">=", 7)
        println(get json.encode(projected))
        println(len(sales))
        println(len(tagged))
        println(len(large))
        println(get json.encode(data_sum(rows, "amount")))
        println(get json.encode(data_sum(rows, "missing")))
        println(get json.encode(data_where(rows, "kind", "!=", "sale")))
        println(get json.encode(data_where(rows, "amount", "<", 3)))
        println(get json.encode(data_where([], "x", "==", 1)))
        println(get json.encode(data_project([], ["a"])))
    """
    _parity(native_binary, source, data_dir)


@pytest.mark.parametrize(
    ("source", "fragment"),
    [
        (
            'let rows = [{"amount": 1}]\nprintln(get json.encode(data_where(rows, "amount", "~=", 1)))\n',
            "unsupported data.where operator: ~=",
        ),
        (
            'let stream = data_open_jsonl("data/records.jsonl", 2)\n'
            "println(get json.encode(data_close(stream)))\n"
            "println(get json.encode(data_next(stream)))\n",
            "unknown or closed data stream: data:1",
        ),
        (
            'let stream = data_open_jsonl("data/records.jsonl", 1001)\n',
            "data batch size must be 1-1000",
        ),
        (
            'let stream = data_open_jsonl("data/missing.jsonl")\n',
            "data: cannot open data/missing.jsonl",
        ),
        (
            'let a = data_open_jsonl("data/records.jsonl")\n'
            'let b = data_open_jsonl("data/records.jsonl")\n'
            'let c = data_open_jsonl("data/records.jsonl")\n'
            'let d = data_open_jsonl("data/records.jsonl")\n'
            'let e = data_open_jsonl("data/records.jsonl")\n'
            'let f = data_open_jsonl("data/records.jsonl")\n'
            'let g = data_open_jsonl("data/records.jsonl")\n'
            'let h = data_open_jsonl("data/records.jsonl")\n'
            'let i = data_open_jsonl("data/records.jsonl")\n',
            "too many open data streams (max 8)",
        ),
    ],
)
def test_native_data_errors(
    native_binary: Path, data_dir: Path, source: str, fragment: str
) -> None:
    script = _write_case(source, data_dir)
    result = subprocess.run(
        [str(native_binary), "run", str(script)],
        capture_output=True,
        text=True,
        cwd=data_dir,
        check=False,
    )
    assert result.returncode == 1, result.stdout
    assert fragment in result.stderr, result.stderr
