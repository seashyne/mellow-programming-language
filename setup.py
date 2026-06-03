from __future__ import annotations

import os
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


ext_modules = [
    Extension(
        "mellowlang._mellowvm",
        sources=["native/mellowvm/src/mellowvm_module.c"],
        include_dirs=["native/mellowvm/include", *_python_include_dirs()],
        define_macros=[('PY_SSIZE_T_CLEAN', None)],
        extra_compile_args=[],
        extra_link_args=["/MANIFEST:NO"] if os.name == "nt" else [],
    )
]

setup(
    ext_modules=ext_modules,
    cmdclass={"build_ext": OptionalBuildExt},
)
