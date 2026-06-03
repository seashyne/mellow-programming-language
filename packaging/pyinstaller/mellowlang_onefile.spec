# -*- mode: python ; coding: utf-8 -*-
# MellowLang v2.3.4 — onefile spec (single portable .exe, slower first launch)
# Output: dist/mellow_onefile.exe
# Usage:  pyinstaller packaging/pyinstaller/mellowlang_onefile.spec --clean --noconfirm
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

HERE  = os.path.abspath(SPECPATH)
ROOT  = os.path.abspath(os.path.join(HERE, "..", ".."))
SRC   = os.path.join(ROOT, "src")
ENTRY = os.path.join(HERE, "run_mellowlang.py")
VINFO = os.path.join(HERE, "..", "windows", "version_info.txt")

hidden = collect_submodules("mellowlang")
datas  = collect_data_files("mellowlang", includes=["playground/assets/*"])

for _rt in [
    os.path.join(ROOT, "native", "standalone", "build", "Release", "mellowrt.exe"),
    os.path.join(ROOT, "native", "standalone", "build", "mellowrt.exe"),
    os.path.join(ROOT, "native", "standalone", "build", "mellowrt"),
]:
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
    runtime_hooks=[],
    excludes=["tkinter", "test", "unittest"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name="mellow_onefile",
    debug=False, strip=False, upx=True, console=True,
    runtime_tmpdir=None,      # extract to temp dir each launch
    version=VINFO if os.path.isfile(VINFO) else None,
)
