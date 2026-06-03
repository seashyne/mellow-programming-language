from __future__ import annotations

from mellowlang.native_vm import native_vm_status


def test_native_vm_status_shape():
    info = native_vm_status()
    assert 'available' in info
    assert 'build_command' in info
    assert 'source_files_present' in info
    assert isinstance(info.get('python_header_candidates'), list)
