from mellowlang.vm import MellowVM, RunConfig
from mellowlang.compiler import Compiler
from mellowlang.error_core import MellowLangRuntimeError
from mellowlang.vm import cbridge


class _FakeExt:
    def __init__(self):
        self.calls = 0

    def run(self, **kwargs):
        self.calls += 1
        return 123


def test_run_bytecode_ex_reports_native_engine(monkeypatch):
    fake = _FakeExt()
    monkeypatch.setattr(cbridge, '_load_ext', lambda: fake)
    out = cbridge.run_bytecode_ex(bytecode=[('HALT',)], host=None, config={}, allow_fallback=True)
    assert out.engine == 'c'
    assert out.used_fallback is False
    assert out.result == 123


def test_native_required_raises_before_python_fallback(monkeypatch):
    monkeypatch.setattr(cbridge, '_load_ext', lambda: None)
    program = Compiler().compile("print(1)\n", filename='<test>')
    vm = MellowVM()
    try:
        vm.run(program, config=RunConfig(engine='c', native_allow_fallback=False, native_require=True))
    except MellowLangRuntimeError as e:
        assert 'native' in str(e).lower()
    else:
        raise AssertionError('expected NATIVE_REQUIRED error')
