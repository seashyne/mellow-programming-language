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


def run_source(src: str, *, cwd: Path | None = None, cfg: RunConfig | None = None):
    src = textwrap.dedent(src).lstrip("\n")
    comp = Compiler()
    prog = comp.compile(src, filename="<test>")
    vm = MellowVM()
    buf = io.StringIO()

    if cfg is None:
        cfg = RunConfig()

    with contextlib.redirect_stdout(buf):
        if cwd is None:
            vm.run(prog, config=cfg)
        else:
            old = os.getcwd()
            os.chdir(cwd)
            try:
                vm.run(prog, config=cfg)
            finally:
                os.chdir(old)

    return buf.getvalue()


def test_hello_prints():
    out = run_source('print("Hello!")\n')
    assert "Hello!" in out


def test_print_multi_values():
    src = """
    let d = {"a": 1}
    print("loaded =", d)
    """
    out = run_source(src)
    assert "loaded =" in out
    # dict should be printed too (Python-style spacing is fine)
    assert "a" in out and "1" in out


def test_def_function_call():
    src = """
    def add(a, b):
        return a + b

    print(add(2, 3))
    """
    out = run_source(src)
    assert "5" in out


def test_for_loop_sum_range():
    src = """
    let s = 0
    for i in range(0, 6):
        s = s + i
    print(s)
    """
    out = run_source(src)
    assert "15" in out  # 0+1+2+3+4+5


def test_while_loop():
    src = """
    let i = 0
    let s = 0
    while i < 4:
        s = s + i
        i = i + 1
    print(s)
    """
    out = run_source(src)
    assert "6" in out  # 0+1+2+3


def test_vectors_basic():
    src = """
    let v = vec(3, 4)
    print(v)
    print(vec_len(v))
    """
    out = run_source(src)
    assert "[" in out
    assert "5" in out  # length 5


def test_storage_save_and_load_roundtrip_creates_base_dir():
    with tempfile.TemporaryDirectory() as td:
        cwd = Path(td)
        src = """
        save {"score": 42, "name": "mellow"} into "profile"
        load "profile" into data
        print(data)
        """
        out = run_source(src, cwd=cwd)
        assert "42" in out
        assert (cwd / "mellow_saves").is_dir()


def test_named_args_in_calls_file_mode():
    with tempfile.TemporaryDirectory() as td:
        cwd = Path(td)
        src = """
        file_write("notes.txt", "hello\\n", mode="w")
        file_append("notes.txt", "world\\n", mode="a")
        print(file_read("notes.txt"))
        """
        out = run_source(src, cwd=cwd)
        assert "hello" in out and "world" in out


def test_dict_arg_is_not_mistaken_for_kwargs():
    """Regression: kwargs are encoded as {"$kwargs": {...}}.
    A user dict argument (common in save_data) must not be stripped."""
    with tempfile.TemporaryDirectory() as td:
        cwd = Path(td)
        src = """
        mkdir(".")
        let data = {"hp": 10, "name": "slime"}
        save_data("profile", data)
        let loaded = load_data("profile")
        print(loaded)
        """
        out = run_source(src, cwd=cwd)
        assert "hp" in out and "10" in out


def test_deterministic_seed_random():
    src = """
    print(random(1, 100))
    print(random(1, 100))
    """
    out1 = run_source(src, cfg=RunConfig(seed=123))
    out2 = run_source(src, cfg=RunConfig(seed=123))
    assert out1 == out2


def test_record_replay_same_output():
    with tempfile.TemporaryDirectory() as td:
        cwd = Path(td)
        log = cwd / "run.jsonl"
        src = """
        print(random(1, 100))
        print(random(1, 100))
        """
        out1 = run_source(src, cwd=cwd, cfg=RunConfig(record_path=str(log), seed=7))
        out2 = run_source(src, cwd=cwd, cfg=RunConfig(replay_path=str(log), seed=999))
        assert out1 == out2


def test_syntax_error_has_line_col():
    src = """\n    print(1)\n    end\n    """
    comp = Compiler()
    with pytest.raises(MellowLangRuntimeError) as e:
        comp.compile(textwrap.dedent(src), filename="bad.mellow")
    assert e.value.error_type == "SYNTAX"
    assert isinstance(e.value.line_num, int)
    assert isinstance(e.value.col, int)


def test_ai_decide_timeline_jsonl():
    with tempfile.TemporaryDirectory() as td:
        cwd = Path(td)
        timeline = cwd / "ai.jsonl"
        src = """
        import "ai" as ai
        call(ai["decide"], "patrol", "start")
        call(ai["decide"], "patrol", "end")
        print("ok")
        """
        out = run_source(src, cwd=cwd, cfg=RunConfig(ai_timeline=str(timeline)))
        assert "ok" in out
        txt = timeline.read_text(encoding="utf-8")
        assert "patrol" in txt
