from __future__ import annotations

from mellowlang.native_vm import cpu_runtime_profile, native_vm_status


def test_native_vm_status_shape():
    info = native_vm_status()
    assert 'available' in info
    assert 'build_command' in info
    assert 'source_files_present' in info
    assert isinstance(info.get('python_header_candidates'), list)
    assert info['portable_backend'] == 'generic-c'
    assert 'generic-c' in info['available_native_backends']
    assert info['native_backend'] in info['available_native_backends']
    assert info['multi_core_workers'] >= 1


def test_cpu_runtime_profile_x86_64():
    info = cpu_runtime_profile('AMD64')
    assert info['normalized_arch'] == 'x86_64'
    assert info['preferred_backend'] == 'generic-c'
    assert 'generic-c' in info['available_backends']
    assert info['x86_64_ready'] is True
    assert info['optimized_kernels'] is False


def test_cpu_runtime_profile_arm64():
    info = cpu_runtime_profile('aarch64')
    assert info['normalized_arch'] == 'arm64'
    assert info['preferred_backend'] == 'generic-c'
    assert 'generic-c' in info['available_backends']
    assert info['arm64_ready'] is True
    assert 'neon-baseline' in info['cpu_features']
    assert info['optimized_kernels'] is False
