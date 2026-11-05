"""Standalone C parity for the data standard library.

`std.string`, `std.list`, `std.map`, `std.type`, `std.json`, and `std.math`
ship in the native runtime, so the standalone binary must agree with the
Python reference engine. Every case compiles one source twice and compares
the printed output; values travel as JSON so containers and floats stay
comparable across the two display rules.

Two behaviours cannot match by construction and are pinned instead:
native lists and maps are value types, so mutators return new collections
instead of changing the receiver (see the value-semantics test below).
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
    build = tmp_path_factory.mktemp("mellow-std-native")
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
    program = Compiler().compile(textwrap.dedent(source).lstrip("\n"), filename="<native-std>")
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


def test_string_surface_matches_python(native_binary: Path, tmp_path: Path) -> None:
    source = """
        println(get json.encode(get string.len("hello world")))
        println(get json.encode(get string.lower("ABC")))
        println(get json.encode(get string.upper("abc")))
        println(get json.encode(get string.trim("  hi  ")))
        println(get json.encode(get string.replace("a b c", " ", "|")))
        println(get json.encode(get string.replace("abc", "", "_")))
        println(get json.encode(get string.find("hello", "ll")))
        println(get json.encode(get string.find("hello", "zz")))
        println(get json.encode(get string.split("a,b,c", ",")))
        println(get json.encode(get string.split("a  b   c")))
        println(get json.encode(get string.join(["a", "b", "c"], ",")))
        println(get json.encode(get string.starts_with("hello", "he")))
        println(get json.encode(get string.ends_with("hello", "lo")))
        println(get json.encode(get string.contains("hello", "ell")))
        println(get json.encode(get string.repeat("ab", 3)))
        println(get json.encode(get string.pad_left("7", 3, "0")))
        println(get json.encode(get string.pad_right("7", 3, ".")))
        println(get json.encode(get string.format("{} + {} = {}", 1, 2, 3)))
        println(get json.encode(get string.format("{0} {0}", "x")))
        println(get json.encode(get string.chr(65)))
        println(get json.encode(get string.ord("A")))
        println(get json.encode(get string.tostr(none)))
        println(get json.encode(get string.tostr(true)))
        println(get json.encode(get string.tostr(1.0)))
    """
    _parity(native_binary, source, tmp_path)


def test_list_surface_matches_python(native_binary: Path, tmp_path: Path) -> None:
    source = """
        println(get json.encode(get list.push([3, 1, 2], 4)))
        println(get json.encode(get list.pop([3, 1, 2])))
        println(get json.encode(get list.pop([])))
        println(get json.encode(get list.len([3, 1, 2])))
        println(get json.encode(get list.insert([3, 1, 2], 1, 9)))
        println(get json.encode(get list.insert([3, 1, 2], 9, 9)))
        println(get json.encode(get list.remove([3, 1, 2], 1)))
        println(get json.encode(get list.remove([3, 1, 2], 8)))
        println(get json.encode(get list.has([3, 1, 2], 2)))
        println(get json.encode(get list.find([3, 1, 2], 2)))
        println(get json.encode(get list.find([3, 1, 2], 8)))
        println(get json.encode(get list.slice([3, 1, 2], 1, 3)))
        println(get json.encode(get list.slice([3, 1, 2], 1)))
        println(get json.encode(get list.sort([3, 1, 2])))
        println(get json.encode(get list.sorted([3, 1, 2], true)))
        println(get json.encode(get list.reverse([3, 1, 2])))
        println(get json.encode(get list.reversed([3, 1, 2])))
        println(get json.encode(get list.count([3, 1, 2], 2)))
        println(get json.encode(get list.enumerate("ab")))
        println(get json.encode(get list.enumerate([3, 1, 2])))
        println(get json.encode(get list.zip([1, 2], [3, 4, 5])))
        println(get json.encode(get list.any([0, 1])))
        println(get json.encode(get list.all([1, 1])))
        println(get json.encode(get list._extend([3, 1, 2], [7, 8])))
        println(get json.encode(get list._append_to_top([3, 1, 2], 7)))
    """
    _parity(native_binary, source, tmp_path)


def test_map_and_type_surface_matches_python(native_binary: Path, tmp_path: Path) -> None:
    source = """
        println(get json.encode(get map.get({"a": 1}, "a")))
        println(get json.encode(get map.get({"a": 1}, "z")))
        println(get json.encode(get map.get({"a": 1}, "z", 5)))
        println(get json.encode(get map.set({"a": 1}, "b", 2)))
        println(get json.encode(get map.set({"a": 1}, "a", 9)))
        println(get json.encode(get map.keys({"b": 2, "a": 1})))
        println(get json.encode(get map.values({"b": 2, "a": 1})))
        println(get json.encode(get map.has({"a": 1}, "a")))
        println(get json.encode(get map.has({"a": 1}, "z")))
        println(get json.encode(get type.is_number(1)))
        println(get json.encode(get type.is_number(true)))
        println(get json.encode(get type.is_string("x")))
        println(get json.encode(get type.is_bool(false)))
        println(get json.encode(get type.is_list([])))
        println(get json.encode(get type.is_map({})))
        println(get json.encode(get type.is_none(none)))
        println(get json.encode(get type.of(none)))
        println(get json.encode(get type.of(1.5)))
        println(get json.encode(get type.of("s")))
        println(get json.encode(get type.to_int("42")))
        println(get json.encode(get type.to_int("bad")))
        println(get json.encode(get type.to_int(true)))
        println(get json.encode(get type.to_float("1.5")))
        println(get json.encode(get type.to_bool([])))
        println(get json.encode(get type.to_bool({})))
        println(get json.encode(get type.to_bool("false")))
        println(get json.encode(get type.to_list({"a": 1, "b": 2})))
        println(get json.encode(get type.to_list(5)))
        println(get json.encode(get type.to_list(none)))
    """
    _parity(native_binary, source, tmp_path)


def test_json_surface_matches_python(native_binary: Path, tmp_path: Path) -> None:
    source = """
        println(get json.encode(get json.encode({"a": [1, 2.5, true, none], "b": "text"})))
        println(get json.encode(get json.decode('{"a": [1, 2.5, true, null], "b": "text"}')))
        println(get json.encode(get json.decode("[1, 2, 3]")))
        println(get json.encode(get json.decode(get string.join(["tr", "ue"], ""))))
        println(get json.encode(get json.decode(get string.join(["nu", "ll"], ""))))
        println(get json.encode(get json.decode('{"k": {"n": 1}}')))
    """
    _parity(native_binary, source, tmp_path)


def test_math_surface_matches_python(native_binary: Path, tmp_path: Path) -> None:
    source = """
        println(get json.encode(get math.round(2.5)))
        println(get json.encode(get math.round(3.5)))
        println(get json.encode(get math.round(-2.5)))
        println(get json.encode(get math.pow(2, 10)))
        println(get json.encode(get math.sin(0.5)))
        println(get json.encode(get math.cos(0.5)))
        println(get json.encode(get math.tan(0.5)))
        println(get json.encode(get math.atan2(1, 2)))
        println(get json.encode(get math.pi()))
        println(get json.encode(get math.sign(-4)))
        println(get json.encode(get math.sign(0)))
        println(get json.encode(get math.fmod(-7, 3)))
        println(get json.encode(get math.fmod(7, -3)))
        println(get json.encode(get math.deg_to_rad(180)))
        println(get json.encode(get math.rad_to_deg(3.141592653589793)))
        println(get json.encode(get math.distance([0, 0], [3, 4])))
        println(get json.encode(get math.angle_between([0, 0], [1, 1])))
        println(get json.encode(get math.sum([1, 2, 3])))
        println(get json.encode(get math.sum([1, 2.5, 3])))
        println(get json.encode(get math.sum(["1", "2"])))
        println(get json.encode(get math.sum(["x"])))
        println(get json.encode(get math.vec2(1, 2)))
        println(get json.encode(get math.vec3(1, 2, 3)))
        println(get json.encode(get math.vector(3, 1, 2, 3)))
        println(get json.encode(get math.vector([1, 2])))
        println(get json.encode(get math.vec_add([1, 2], [3, 4])))
        println(get json.encode(get math.vec_sub([1, 2], [3, 4])))
        println(get json.encode(get math.vec_mul([1, 2], 3)))
        println(get json.encode(get math.vec_dot([1, 2], [3, 4])))
        println(get json.encode(get math.vec_len([3, 4])))
        println(get json.encode(get math.vec_norm([3, 4])))
        println(get json.encode(get math.vec_dist([0, 0], [3, 4])))
        println(get json.encode(get math.vec_dim([1, 2, 3])))
        println(get json.encode(get math.vec_axis([1, 2, 3], 1)))
        println(get json.encode(get math.vec_lerp([0, 0], [10, 20], 0.5)))
        println(get json.encode(get math.vec_limit([10, 0], 5)))
    """
    _parity(native_binary, source, tmp_path)


def test_collections_are_value_types_in_the_native_runtime(native_binary: Path, tmp_path: Path) -> None:
    """Python mutates the receiver; the native runtime returns new values."""
    source = """
        let xs = [3, 1, 2]
        let pushed = list.push(xs, 4)
        let inserted = list.insert(xs, 1, 9)
        let removed = list.remove(xs, 1)
        let data = {"a": 1}
        let extended = map.set(data, "b", 2)
        println(json.encode(xs))
        println(json.encode(pushed))
        println(json.encode(inserted))
        println(json.encode(removed))
        println(json.encode(data))
        println(json.encode(extended))
        println(json.encode(list.pop(xs)))
        println(json.encode(xs))
    """
    output = _run_native(native_binary, source, tmp_path).strip().splitlines()
    assert output == [
        "[3, 1, 2]",
        "[3, 1, 2, 4]",
        "[3, 9, 1, 2]",
        "[3, 2]",
        '{"a": 1}',
        '{"a": 1, "b": 2}',
        "2",
        "[3, 1, 2]",
    ]


def test_assert_failures_use_python_messages(native_binary: Path, tmp_path: Path) -> None:
    script = _write_case("println(get assert.check(false))\n", tmp_path)
    result = subprocess.run(
        [str(native_binary), "run", str(script)],
        capture_output=True, text=True, cwd=tmp_path, check=False,
    )
    assert result.returncode != 0
    assert "AssertionError: assertion failed" in (result.stderr + result.stdout)

    script = _write_case('println(get assert.eq(1, 2, "custom"))\n', tmp_path)
    result = subprocess.run(
        [str(native_binary), "run", str(script)],
        capture_output=True, text=True, cwd=tmp_path, check=False,
    )
    assert result.returncode != 0
    assert "AssertionError: custom" in (result.stderr + result.stdout)

    script = _write_case("println(get assert.ne(1, 1))\n", tmp_path)
    result = subprocess.run(
        [str(native_binary), "run", str(script)],
        capture_output=True, text=True, cwd=tmp_path, check=False,
    )
    assert result.returncode != 0
    assert "AssertionError: expected 1 != 1" in (result.stderr + result.stdout)


def test_time_builtins_progress(native_binary: Path, tmp_path: Path) -> None:
    source = """
        let first = time.now()
        let unix = time.unix()
        let ms = time.ms()
        let second = time.now()
        println(second >= first)
        println(unix > 1700000000)
        println(ms > 1700000000000)
    """
    output = _run_native(native_binary, source, tmp_path).strip().splitlines()
    assert output == ["true", "true", "true"]
