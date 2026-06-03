import sys
from pathlib import Path
import textwrap
import io
import contextlib

# Allow running tests without installing the package
sys.path.insert(0, str((Path(__file__).resolve().parents[1] / "src")))

from mellowlang.compiler.compiler import Compiler
from mellowlang.vm.vm import MellowVM, RunConfig


def run_source(src: str):
    src = textwrap.dedent(src).lstrip("\n")
    comp = Compiler()
    prog = comp.compile(src, filename="<test>")
    vm = MellowVM()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        vm.run(prog, config=RunConfig())
    return buf.getvalue()


def test_game_module_get_and_easing():
    src = """
    g = get("game")
    v = call(g["ease_in_quad"], 0.5)
    print(v)
    """
    out = run_source(src)
    # 0.5^2 = 0.25
    assert "0.25" in out


def test_game_astar_basic():
    src = """
    g = get("game")
    grid = [
      [0,0,0,0],
      [1,1,0,1],
      [0,0,0,0]
    ]
    path = call(g["astar"], grid, [0,0], [3,2], false)
    print(path)
    """
    out = run_source(src)
    # Expect a non-empty path ending at [3,2]
    assert "[3, 2]" in out
