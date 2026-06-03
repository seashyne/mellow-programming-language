import os
import sys
from pathlib import Path
import tempfile
import textwrap

import pytest

sys.path.insert(0, str((Path(__file__).resolve().parents[1] / "src")))

from mellowlang.compiler.compiler import Compiler
from mellowlang.vm.vm import MellowVM, RunConfig
from mellowlang.error_core import MellowLangRuntimeError


def run_source(src: str, *, cfg: RunConfig | None = None):
    src = textwrap.dedent(src).lstrip("\n")
    comp = Compiler()
    prog = comp.compile(src, filename="<test>")
    vm = MellowVM()
    return vm.run(prog, config=cfg or RunConfig())


def test_secure_save_roundtrip_and_list(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        monkeypatch.setenv("XDG_DATA_HOME", str(td))
        src = """
        save_init("my.game")
        save_set("hp", 120)
        save_set("stage", 3)
        save_commit("slot1")
        save_clear()
        let ok = save_load("slot1")
        print(ok)
        print(save_get("hp", 0))
        print(save_list())
        """
        # just ensure no crash
        res = run_source(src)
        # Verify file exists
        p = td / "my.game" / "saves" / "slot1.msav"
        assert p.exists()


def test_secure_save_tamper_detected(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        monkeypatch.setenv("XDG_DATA_HOME", str(td))

        run_source('save_init("my.game")\nsave_set("hp", 1)\nsave_commit("slot1")\n')
        p = td / "my.game" / "saves" / "slot1.msav"
        assert p.exists()
        data = bytearray(p.read_bytes())
        # flip a byte in ciphertext area
        data[-1] ^= 0x01
        p.write_bytes(bytes(data))

        src = 'save_init("my.game")\nsave_load("slot1")\n'
        with pytest.raises(MellowLangRuntimeError) as ei:
            run_source(src)
        assert "SAVE_TAMPERED" in str(ei.value)


def test_secure_save_quota_bytes(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        monkeypatch.setenv("XDG_DATA_HOME", str(td))
        cfg = RunConfig(save_bytes_max=64)
        src = """
        save_init("my.game")
        # create a payload > 64 bytes
        let big = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        save_set("blob", big)
        save_commit("slot1")
        """
        with pytest.raises(MellowLangRuntimeError) as ei:
            run_source(src, cfg=cfg)
        assert "SAVE_QUOTA_BYTES" in str(ei.value)
