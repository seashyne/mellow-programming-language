from __future__ import annotations

import os
import platform
import sysconfig
from pathlib import Path
from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext


class OptionalBuildExt(build_ext):
    """Build C extensions if possible, but do not fail installation if a compiler isn't available.

    This keeps `pip install mellowlang` usable on machines without build tools.
    To force-disable the native extension build, set: MELLOW_NO_EXT=1
    """

    def run(self):
        if os.environ.get("MELLOW_NO_EXT") == "1":
            self.extensions = []
            return
        try:
            super().run()
        except Exception as e:
            print(f"[mellowlang] Warning: native extension build skipped: {e}")
            self.extensions = []

    def build_extension(self, ext):
        try:
            super().build_extension(ext)
        except Exception as e:
            print(f"[mellowlang] Warning: failed to build {ext.name}: {e}")


# Optional C-accelerated VM extension.
def _python_include_dirs() -> list[str]:
    cfg = sysconfig.get_paths()
    vals = []
    for key in ("include", "platinclude"):
        v = cfg.get(key)
        if v and v not in vals:
            vals.append(v)
    version_tag = f"python{sysconfig.get_python_version()}"
    for extra in (Path(sysconfig.get_config_var('prefix') or sysconfig.get_paths().get('data', '')) / 'include' / version_tag, Path('/usr/include') / version_tag):
        s = str(extra)
        if s not in vals:
            vals.append(s)
    return vals


def _native_arch_macros() -> list[tuple[str, str | None]]:
    machine = (platform.machine() or "").lower().replace("-", "_")
    macros: list[tuple[str, str | None]] = [("PY_SSIZE_T_CLEAN", None), ("MELLOW_BACKEND_GENERIC_C", "1")]
    if machine in {"amd64", "x86_64", "x64"}:
        macros.append(("MELLOW_ARCH_X86_64", "1"))
    elif machine in {"arm64", "aarch64", "armv8"}:
        macros.append(("MELLOW_ARCH_ARM64", "1"))
    elif machine.startswith("arm"):
        macros.append(("MELLOW_ARCH_ARM32", "1"))
    else:
        macros.append(("MELLOW_ARCH_UNKNOWN", "1"))
    return macros


ext_modules = [
    Extension(
        "mellowlang._mellowvm",
        sources=["native/mellowvm/src/mellowvm_module.c"],
        depends=[
            "native/mellowvm/include/mellowvm.h",
            "native/mellowvm/src/mellowvm_exec.inc",
            "native/mellowvm/src/mellowvm_syscalls.inc",
        ],
        include_dirs=["native/mellowvm/include", *_python_include_dirs()],
        define_macros=_native_arch_macros(),
        extra_compile_args=[],
        extra_link_args=["/MANIFEST:NO"] if os.name == "nt" else [],
    ),
    Extension(
        "mellowlang._mellowllm",
        sources=[
            "native/mellowllm/src/mellowllm_core.c",
            "native/mellowllm/src/mellowllm_module.c",
        ],
        include_dirs=["native/mellowllm/include", *_python_include_dirs()],
        define_macros=_native_arch_macros(),
        extra_compile_args=[],
        extra_link_args=["/MANIFEST:NO"] if os.name == "nt" else [],
    ),
    Extension(
        "mellowlang._melv",
        sources=[
            "native/melv/src/melv_native.c",
            "native/melv/src/melv_module.c",
        ],
        include_dirs=["native/melv/include", *_python_include_dirs()],
        define_macros=_native_arch_macros(),
        extra_compile_args=[],
        extra_link_args=["/MANIFEST:NO"] if os.name == "nt" else [],
    ),
]

setup(
    ext_modules=ext_modules,
    cmdclass={"build_ext": OptionalBuildExt},
)
