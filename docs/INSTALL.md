# Installing MellowLang v2.6.0

## Linux

### Option A — .deb package (Ubuntu / Debian)
```bash
bash packaging/linux/build_deb.sh
sudo dpkg -i dist/mellowlang_2.6.0_amd64.deb
mellow --version
```
Installs `mellow` + `mellowrt` to `/usr/bin/`, registers `.mellow` MIME type.

### Option B — install.sh (all distros)
```bash
chmod +x install.sh && ./install.sh
# options:
./install.sh --dev              # include dev deps
./install.sh --prefix /opt/ml   # custom location
./install.sh --uninstall        # remove
```

---

## macOS

### Option A — .pkg installer
```bash
bash packaging/macos/build_pkg.sh
# then double-click dist/MellowLang-2.6.0.pkg
# or: sudo installer -pkg dist/MellowLang-2.6.0.pkg -target /
mellow --version
```

### Option B — install.sh (same script as Linux)
```bash
chmod +x install.sh && ./install.sh
```

---

## Windows

### Option A — .exe installer (recommended for end-users)
Double-click `MellowLang_Setup_2.6.0.exe` -> Next -> Install.

Two installer variants:
| File | Size | Notes |
|---|---|---|
| `MellowLang_Setup_2.6.0.exe` | ~25 MB | onedir - fast startup |
| `MellowLang_Setup_2.6.0_portable.exe` | ~12 MB | onefile - single portable .exe |

Both add to PATH and associate `.mellow` files.

### Option B — Build from source
```cmd
packaging\windows\build_exe.bat
```
Produces both installers automatically.  Requirements: Python 3.10+, optional Inno Setup 6.

### Option C — Portable ZIP (no install)
```cmd
mellow.cmd run examples\hello.mellow
```

---

## Building installers (all platforms)

| Platform | Command | Output |
|---|---|---|
| Windows onedir | `build_exe.bat` | `dist/MellowLang_Setup_2.6.0.exe` |
| Windows onefile | `build_exe.bat` | `dist/MellowLang_Setup_2.6.0_portable.exe` |
| macOS | `bash packaging/macos/build_pkg.sh` | `dist/MellowLang-2.6.0.pkg` |
| Linux .deb | `bash packaging/linux/build_deb.sh` | `dist/mellowlang_2.6.0_amd64.deb` |
| Linux generic | `bash install.sh` | installs to `~/.local/bin/` |

---

## Build the standalone C runtime (Python-free execution)

All build scripts build `mellowrt` automatically if cmake is available.

```bash
# Manual build
cmake -S native/standalone -B native/standalone/build -DCMAKE_BUILD_TYPE=Release
cmake --build native/standalone/build

# Use it
mellow standalone compile script.mellow -o script.mvi
./native/standalone/build/mellowrt script.mvi   # no Python needed
```

---

## System requirements

| | Minimum |
|---|---|
| OS | Windows 10+, Ubuntu 20.04+, macOS 12+ |
| Python | 3.10+ (compiler + Python VM) |
| C compiler | gcc / clang / MSVC (optional, standalone runtime) |
| cmake | 3.16+ (optional, standalone runtime) |
| Disk | 30 MB (Python install) / 2 MB (standalone binary) |
