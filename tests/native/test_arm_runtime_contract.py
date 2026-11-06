from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_standalone_cmake_detects_arm64_and_builds_platform_api() -> None:
    cmake = (ROOT / "native" / "standalone" / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "CMAKE_SYSTEM_PROCESSOR" in cmake
    assert 'MELLOW_TARGET_ARCH "arm64"' in cmake
    assert "src/mellowrt_platform.c" in cmake
    assert "if(NOT MSVC)" in cmake


def test_arm64_ci_cross_builds_and_executes_the_runtime() -> None:
    workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert "native-arm64:" in workflow
    assert "aarch64-linux-gnu-gcc" in workflow
    assert "qemu-aarch64" in workflow
    assert "--runtime-info" in workflow
    assert "full_native_core.mellow" in workflow


def test_native_architectures_are_primary_release_gates() -> None:
    workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert "native-x64:" in workflow
    assert "native-arm64:" in workflow
    assert "native-safety:" in workflow
    assert "tooling-reference:" in workflow
    assert "needs: [native-x64, native-arm64, native-safety, tooling-reference]" in workflow
    assert "full_native_core.expected" in workflow
    assert 'MELLOW_NO_EXT: "1"' in workflow


def test_arm_backend_claim_matches_implemented_kernels() -> None:
    platform = (ROOT / "native" / "standalone" / "src" / "mellowrt_platform.c").read_text(encoding="utf-8")
    assert 'platform.backend = "generic-c"' in platform
    assert "platform.optimized_kernels = 0" in platform


def test_release_workflow_packages_windows_linux_and_arm64_native_artifacts() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "target: windows-x64" in workflow
    assert "target: linux-x64" in workflow
    assert "target: linux-arm64" in workflow
    assert "target: macos-arm64" in workflow
    assert "aarch64-linux-gnu-gcc" in workflow
    assert "qemu-aarch64" in workflow
    assert "package-native-release.ps1" in workflow
    assert "package-native-release.sh" in workflow
    assert "dist/*.SHA256SUMS" in workflow


def test_native_release_packagers_ship_registry_starters_and_checksums() -> None:
    powershell_packager = (ROOT / "scripts" / "package-native-release.ps1").read_text(encoding="utf-8")
    shell_packager = (ROOT / "scripts" / "package-native-release.sh").read_text(encoding="utf-8")
    for packager in (powershell_packager, shell_packager):
        assert "starter_packages" in packager
        assert "mellow_packages" in packager
        assert "registry" in packager
        assert "SHA256SUMS" in packager
        assert "manifest.json" in packager
