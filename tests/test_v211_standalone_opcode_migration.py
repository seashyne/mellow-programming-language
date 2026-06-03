from pathlib import Path
from mellowlang.standalone_runtime import standalone_runtime_status


def test_standalone_opcode_status_and_core_module():
    info = standalone_runtime_status()
    assert info["opcode_migration"]["call_return"] is True
    assert info["opcode_migration"]["syscall_bridge"] is True
    assert info["core_module_present"] is True
    assert Path(info["core_module_existing"][0]).name in {"core.mellow", "core.mel"}
