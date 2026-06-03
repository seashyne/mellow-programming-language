# -*- mode: python ; coding: utf-8 -*-
# MellowLang v2.3.4 — PyInstaller spec
# Supports onedir (default) and onefile builds.
# Usage:
#   pyinstaller packaging/pyinstaller/mellowlang.spec              # onedir
#   pyinstaller packaging/pyinstaller/mellowlang.spec --onefile    # onefile
import os, sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

HERE  = os.path.abspath(SPECPATH)
ROOT  = os.path.abspath(os.path.join(HERE, "..", ".."))
SRC   = os.path.join(ROOT, "src")
ENTRY = os.path.join(HERE, "run_mellowlang.py")

# Collect every mellowlang submodule (agents, compiler, vm, etc.)
hidden = collect_submodules("mellowlang")

# Include playground HTML/CSS/JS assets
datas = collect_data_files("mellowlang", includes=["playground/assets/*"])

# Include the standalone mellowrt binary if it exists (Windows: mellowrt.exe)
_rt_candidates = [
    os.path.join(ROOT, "native", "standalone", "build", "Release", "mellowrt.exe"),
    os.path.join(ROOT, "native", "standalone", "build", "mellowrt.exe"),
    os.path.join(ROOT, "native", "standalone", "build", "mellowrt"),
]
for _rt in _rt_candidates:
    if os.path.isfile(_rt):
        datas.append((_rt, "mellowlang/standalone_bin"))
        break

a = Analysis(
    [ENTRY],
    pathex=[ROOT, SRC],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "test", "unittest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="mellow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    version=os.path.join(HERE, "..", "windows", "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="mellow",
)
