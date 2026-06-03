import io
import os
import sys
import contextlib
import textwrap
from pathlib import Path
import tempfile

import pytest

# Allow running tests without installing the package
sys.path.insert(0, str((Path(__file__).resolve().parents[1] / "src")))

from mellowlang.compiler.compiler import Compiler
from mellowlang.vm.vm import MellowVM, RunConfig
from mellowlang.error_core import MellowLangRuntimeError


def _run(src: str, *, cwd: Path, cfg: RunConfig):
    src = textwrap.dedent(src).lstrip("\n")
    comp = Compiler()
    prog = comp.compile(src, filename="<test>")
    vm = MellowVM()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        old = os.getcwd()
        os.chdir(cwd)
        try:
            vm.run(prog, config=cfg)
        finally:
            os.chdir(old)
    return buf.getvalue()


def test_project_mode_blocks_storage_escape():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        cfg = RunConfig(project_mode=True, project_root=str(root), sandbox_root="saves")
        src = """
        storage_dir("..")
        """
        with pytest.raises(MellowLangRuntimeError) as e:
            _run(src, cwd=root, cfg=cfg)
        assert "storage_dir" in str(e.value)
        assert "blocked" in str(e.value).lower()


def test_project_mode_fs_write_denied_by_default():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        cfg = RunConfig(project_mode=True, project_root=str(root), sandbox_root="saves")
        src = """
        fs_write("exports/out.txt", "hi")
        """
        with pytest.raises(MellowLangRuntimeError) as e:
            _run(src, cwd=root, cfg=cfg)
        msg = str(e.value)
        assert "fs access denied" in msg
        assert "permission" in msg.lower()


def test_project_mode_fs_write_allowlist_allows():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "exports").mkdir(parents=True, exist_ok=True)
        cfg = RunConfig(
            project_mode=True,
            project_root=str(root),
            sandbox_root="saves",
            fs_read_allow="exports",
            fs_write_allow="exports",
        )
        src = """
        fs_write("exports/out.txt", "hi")
        print(fs_read("exports/out.txt"))
        """
        out = _run(src, cwd=root, cfg=cfg)
        assert "hi" in out
        assert (root / "exports" / "out.txt").exists()
