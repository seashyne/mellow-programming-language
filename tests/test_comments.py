import io
import contextlib
import textwrap
from pathlib import Path
import sys

# Allow running tests without installing the package
sys.path.insert(0, str((Path(__file__).resolve().parents[1] / "src")))

from mellowlang.compiler.compiler import Compiler
from mellowlang.vm.vm import MellowVM, RunConfig
from mellowlang.cli import _cmd_check


def run_source(src: str):
    src = textwrap.dedent(src).lstrip("\n")
    prog = Compiler().compile(src, filename="<test>")
    vm = MellowVM()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        vm.run(prog, config=RunConfig())
    return buf.getvalue()


def test_hash_comment_lines_and_inline():
    out = run_source("""
        # full-line comment
        let x = 1  # inline comment
        print(x)
    """)
    assert out.strip().endswith("1")


def test_check_directory(tmp_path: Path):
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "a.mellow").write_text("print(1)\n", encoding="utf-8")
    (d / "b.mellow").write_text("print(2)\n", encoding="utf-8")
    rc = _cmd_check(str(d), json_out=False)
    assert rc == 0
