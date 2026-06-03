from mellowlang.playground.server import start_debug_session
from mellowlang.vm import MellowVM, RunConfig
from mellowlang.compiler import Compiler
from mellowlang.vm.cbridge import c_vm_capabilities


def test_c_capabilities_shape():
    caps = c_vm_capabilities()
    assert 'available' in caps
    assert 'native_execution' in caps
    assert 'conditional_breakpoints' in caps
    assert 'watch_expressions' in caps


def test_vm_reports_engine_detail_for_debug_bridge():
    program = Compiler().compile('print(1)\n', filename='<test>')
    vm = MellowVM()
    vm.run(program, config=RunConfig(engine='c', debug_pause_on_start=True))
    assert vm.last_engine == 'py'
    assert vm.last_engine_detail
    assert isinstance(vm.last_debug_capabilities, dict)


def test_debug_session_typed_frames_and_native_caps_present():
    started = start_debug_session('keep score = 1\nprint(score)\n', watch='score')
    stop = started['stop']
    assert 'typed_frames' in stop
    assert 'source_span_text' in stop
    caps = started['debug_capabilities']['native_c_capabilities']
    assert 'native_execution' in caps
