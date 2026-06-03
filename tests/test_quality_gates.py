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

from mellowlang.cli import main as cli_main, _print_pretty_error
from mellowlang.compiler.compiler import Compiler
from mellowlang.vm.vm import MellowVM, RunConfig
from mellowlang.error_core import MellowLangRuntimeError
from mellowlang.lint import format_source


def _run_vm(src: str, *, cwd: Path | None = None, cfg: RunConfig | None = None) -> str:
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


def test_formatter_idempotent():
    src = """
    def add(a,b):
      return a+b

    print( add(1,2) )
    """
    once = format_source(textwrap.dedent(src))
    twice = format_source(once)
    assert once == twice


def test_cli_fmt_check_exit_code():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "x.mellow"
        # Intentionally uses a TAB (formatter should convert to 4 spaces)
        p.write_text("def f():\n\tprint(1)\n", encoding="utf-8")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli_main(["fmt", str(p), "--check"])
        assert code == 1
        assert "would format" in buf.getvalue().lower()


def test_cli_fmt_write_then_check_clean():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "x.mellow"
        p.write_text("def f():\n\tprint(1)\n", encoding="utf-8")

        assert cli_main(["fmt", str(p), "--write"]) == 0
        assert cli_main(["fmt", str(p), "--check"]) == 0


def test_cli_check_nonzero_on_syntax_error():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "bad.mellow"
        p.write_text("print(1)\nend\n", encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli_main(["check", str(p)])
        assert code != 0
        out = buf.getvalue()
        assert "error:" in out.lower()
        assert ":" in out  # includes file:line:col


def test_pretty_error_includes_code_frame_and_caret():
    src = "print(1)\nend\n"
    comp = Compiler()
    with pytest.raises(MellowLangRuntimeError) as e:
        comp.compile(src, filename="bad.mellow")

    # Render with our pretty printer and ensure it includes a caret.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _print_pretty_error(e.value, filename="bad.mellow", source_lines=src.splitlines(True), use_color=False)
    out = buf.getvalue()
    assert "^" in out
    assert "|" in out  # frame gutter


def test_sandbox_blocks_parent_traversal_in_file_api():
    with tempfile.TemporaryDirectory() as td:
        cwd = Path(td)
        src = "file_write(\"../hack.txt\", \"x\", mode=\"w\")\n"
        with pytest.raises(MellowLangRuntimeError) as e:
            _run_vm(src, cwd=cwd)
        assert e.value.error_type in ("SANDBOX", "RUNTIME", "STORAGE")
        assert "travers" in (e.value.message or str(e.value)).lower() or "blocked" in (e.value.message or str(e.value)).lower()


def test_sandbox_blocks_absolute_paths_in_file_api():
    with tempfile.TemporaryDirectory() as td:
        cwd = Path(td)
        # Use a Unix-like absolute path. The sandbox should reject it even on Windows.
        src = "file_write(\"/tmp/hack.txt\", \"x\", mode=\"w\")\n"
        with pytest.raises(MellowLangRuntimeError) as e:
            _run_vm(src, cwd=cwd)
        assert e.value.error_type in ("SANDBOX", "RUNTIME", "STORAGE")


def test_storage_atomic_write_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        cwd = Path(td)
        src = """
        mkdir(".")
        save_data("p", {"a": 1})
        let x = load_data("p")
        print(x["a"])
        """
        out = _run_vm(src, cwd=cwd)
        assert "1" in out


def test_record_replay_overrides_nondeterministic_seed():
    with tempfile.TemporaryDirectory() as td:
        cwd = Path(td)
        log = cwd / "run.jsonl"
        src = """
        print(random(1, 100))
        print(random(1, 100))
        """
        out1 = _run_vm(src, cwd=cwd, cfg=RunConfig(record_path=str(log), seed=1))
        out2 = _run_vm(src, cwd=cwd, cfg=RunConfig(replay_path=str(log), seed=9999))
        assert out1 == out2


def test_ai_timeline_writes_jsonl_when_enabled():
    with tempfile.TemporaryDirectory() as td:
        cwd = Path(td)
        timeline = cwd / "ai.jsonl"
        src = """
        import "ai" as ai
        call(ai["decide"], "combat", "see_enemy")
        call(ai["decide"], "combat", "attack")
        print("ok")
        """
        out = _run_vm(src, cwd=cwd, cfg=RunConfig(ai_timeline=str(timeline)))
        assert "ok" in out
        txt = timeline.read_text(encoding="utf-8")
        assert "combat" in txt
        assert "attack" in txt


def test_project_mode_detects_manifest_and_locks_storage():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "mellow.json").write_text(
            """{
  \"entry\": \"main.mellow\",
  \"sandbox_root\": \".sandbox\",
  \"permissions\": {\"allow_storage\": true}
}""",
            encoding="utf-8",
        )
        (root / "main.mellow").write_text("save {\"x\": 1} into \"p\"\n", encoding="utf-8")

        # Run as project dir; should create sandbox root and saves under it.
        assert cli_main(["run", str(root)]) == 0
        assert (root / ".sandbox").exists()


def test_step_budget_trips_on_infinite_loop():
    src = """
    let i = 0
    while true:
        i = i + 1
    """
    with pytest.raises(MellowLangRuntimeError) as e:
        _run_vm(src, cfg=RunConfig(max_steps=1000))
    assert e.value.error_type in ("SANDBOX", "RUNTIME")
