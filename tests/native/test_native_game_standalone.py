"""Standalone C parity for std.game and the AI steering/perception helpers.

Both surfaces are deterministic pure functions, so the standalone binary must
produce the same values as the Python reference engine. Every case compiles
one source twice and compares printed output; results travel through
`json.encode` so containers and floats compare without display differences.
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
    build = tmp_path_factory.mktemp("mellow-game-native")
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
    program = Compiler().compile(textwrap.dedent(source).lstrip("\n"), filename="<native-game>")
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


def test_easing_and_tween_match_python(native_binary: Path, tmp_path: Path) -> None:
    source = """
        println(get json.encode(get game.ease_linear(0.5)))
        println(get json.encode(get game.ease_in_quad(0.25)))
        println(get json.encode(get game.ease_out_quad(0.25)))
        println(get json.encode(get game.ease_in_out_quad(0.25)))
        println(get json.encode(get game.ease_in_out_quad(0.75)))
        println(get json.encode(get game.ease_in_cubic(0.5)))
        println(get json.encode(get game.ease_out_cubic(0.5)))
        println(get json.encode(get game.ease_in_out_cubic(0.75)))
        println(get json.encode(get game.ease_in_back(0.6)))
        println(get json.encode(get game.ease_out_back(0.6)))
        println(get json.encode(get game.ease_out_bounce(0.1)))
        println(get json.encode(get game.ease_out_bounce(0.4)))
        println(get json.encode(get game.ease_out_bounce(0.7)))
        println(get json.encode(get game.ease_out_bounce(0.95)))
        println(get json.encode(get game.ease_out_elastic(0.0)))
        println(get json.encode(get game.ease_out_elastic(0.5)))
        println(get json.encode(get game.ease_out_elastic(1.0)))
        println(get json.encode(get game.tween(0, 10, 0.5)))
        println(get json.encode(get game.tween(0, 10, 0.5, "in_quad")))
        println(get json.encode(get game.tween(0, 10, 0.5, "ease_out_quad")))
        println(get json.encode(get game.tween(10, -10, 0.25, "unknown")))
    """
    _parity(native_binary, source, tmp_path)


def test_grid_and_pathfinding_match_python(native_binary: Path, tmp_path: Path) -> None:
    source = """
        println(get json.encode(get game.neighbors4(0, 0, 3, 3)))
        println(get json.encode(get game.neighbors4(1, 1, 3, 3)))
        println(get json.encode(get game.neighbors8(0, 0, 3, 3)))
        println(get json.encode(get game.neighbors8(1, 1, 3, 3)))
        println(get json.encode(get game.astar([[0,0,0],[0,0,0],[0,0,0]], [0,0], [2,2])))
        println(get json.encode(get game.astar([[0,0,0],[0,0,0],[0,0,0]], [0,0], [2,2], true)))
        println(get json.encode(get game.astar([[0,0,0],[0,1,0],[0,0,0]], [0,0], [2,2])))
        println(get json.encode(get game.astar([[0,0,0],[0,1,0],[0,0,0]], [0,0], [2,2], true)))
        println(get json.encode(get game.astar([[0,0,0],[1,1,1],[0,0,0]], [0,0], [0,2])))
        println(get json.encode(get game.astar([[0,1],[1,0]], [0,0], [1,1])))
        println(get json.encode(get game.astar([[0,0],[0,0]], [9,9], [1,1])))
        println(get json.encode(get game.astar([[0,0],[0,0]], [0,0], [0,0], true)))
        println(get json.encode(get game.astar([[0,0,0],[0,0,0]], [0,0], [1,1], true)))
    """
    _parity(native_binary, source, tmp_path)


def test_scene_entity_physics_anim_match_python(native_binary: Path, tmp_path: Path) -> None:
    source = """
        println(get json.encode(get game.scene_create("level")))
        println(get json.encode(get game.scene_create("level", 10, 20)))
        println(get json.encode(get game.entity_create("hero")))
        println(get json.encode(get game.entity_create("hero", 1, 2, 3, 4)))
        println(get json.encode(get game.entity_create("hero", 1, 2, 3, 4, ["player", "fast"])))
        println(get json.encode(get game.entity_move({"id": "hero", "pos": [1, 2], "size": [3, 4], "vel": [0, 0]}, 2, 3)))
        println(get json.encode(get game.entity_move({"pos": [5, 6]}, -1)))
        println(get json.encode(get game.collide_aabb({"pos": [0, 0], "size": [2, 2]}, {"pos": [1, 1], "size": [2, 2]})))
        println(get json.encode(get game.collide_aabb({"pos": [0, 0], "size": [2, 2]}, {"pos": [2, 0], "size": [2, 2]})))
        println(get json.encode(get game.collide_aabb({"pos": [0, 0], "size": [2, 2]}, {"pos": [3, 0], "size": [2, 2]})))
        println(get json.encode(get game.anim_frame(4, 0.5)))
        println(get json.encode(get game.anim_frame(3, 2.5, 4, false)))
        println(get json.encode(get game.anim_frame(3, -0.5, 4, true)))
        println(get json.encode(get game.anim_frame(1, 9)))
    """
    _parity(native_binary, source, tmp_path)


def test_steering_helpers_match_python(native_binary: Path, tmp_path: Path) -> None:
    source = """
        println(get json.encode(get ai.seek([0, 0], [3, 4])))
        println(get json.encode(get ai.seek([0, 0], [3, 4], 2)))
        println(get json.encode(get ai.seek([1, 1], [1, 1])))
        println(get json.encode(get ai.flee([0, 0], [3, 4], 2)))
        println(get json.encode(get ai.flee([2, 2], [2, 2])))
        println(get json.encode(get ai.arrive([0, 0], [100, 0], 10)))
        println(get json.encode(get ai.arrive([0, 0], [100, 0], 10, 50)))
        println(get json.encode(get ai.arrive([45, 0], [100, 0], 10, 50)))
        println(get json.encode(get ai.arrive([0, 0], [0, 0], 10)))
        println(get json.encode(get ai.arrive([0, 0], [100, 0], 10, 0)))
        println(get json.encode(get ai.wander([0, 0], 0)))
        println(get json.encode(get ai.wander([0, 0], 1.0, 2.0, 0.5)))
        println(get json.encode(get ai.patrol([0, 0], [[10, 0], [20, 0]], 0, 5)))
        println(get json.encode(get ai.patrol([18, 0], [[10, 0], [20, 0]], 1, 5)))
        println(get json.encode(get ai.patrol([0, 0], [], 0)))
        println(get json.encode(get ai.patrol([10, 0], [[10, 0], [20, 0]], 0, 5)))
    """
    _parity(native_binary, source, tmp_path)


def test_perception_helpers_match_python(native_binary: Path, tmp_path: Path) -> None:
    source = """
        println(get json.encode(get ai.in_range([0, 0], [3, 4], 5)))
        println(get json.encode(get ai.in_range([0, 0], [3, 4], 4.9)))
        println(get json.encode(get ai.in_sight([0, 0], 0, [10, 0])))
        println(get json.encode(get ai.in_sight([0, 0], 180, [-10, 0])))
        println(get json.encode(get ai.in_sight([0, 0], 0, [-10, 0])))
        println(get json.encode(get ai.in_sight([0, 0], 0, [10, 10])))
        println(get json.encode(get ai.in_sight([0, 0], 45, [10, 10])))
        println(get json.encode(get ai.in_sight([0, 0], 0, [10, 0], 30)))
        println(get json.encode(get ai.in_sight([0, 0], 0, [300, 0], 90, 200)))
        println(get json.encode(get ai.in_sight([0, 0], 0, [0, 0])))
        println(get json.encode(get ai.nearest([0, 0], [[5, 5], {"pos": [1, 1]}])))
        println(get json.encode(get ai.nearest([0, 0], [[5, 5], [2, 2], [2, 2]])))
        println(get json.encode(get ai.nearest([0, 0], [])))
        println(get json.encode(get ai.filter_range([0, 0], [[1, 1], [10, 10], {"pos": [2, 0]}], 5)))
        println(get json.encode(get ai.filter_range([0, 0], [], 5)))
    """
    _parity(native_binary, source, tmp_path)


def test_astar_tie_breaking_matches_python(native_binary: Path, tmp_path: Path) -> None:
    grids = [
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0], [0, 1, 0], [0, 0, 0]],
        [[0, 0, 0, 0, 0], [0, 1, 1, 1, 0], [0, 0, 0, 1, 0]],
        [[0, 0, 0, 1, 0], [1, 1, 0, 1, 0], [0, 0, 0, 0, 0], [0, 1, 1, 1, 0]],
    ]
    lines = []
    for grid in grids:
        literal = json.dumps(grid)
        goal = [len(grid[0]) - 1, len(grid) - 1]
        for diagonal in ("false", "true"):
            lines.append(
                f'println(get json.encode(get game.astar({literal}, [0, 0], {goal}, {diagonal})))'
            )
    _parity(native_binary, "\n".join(lines), tmp_path)
