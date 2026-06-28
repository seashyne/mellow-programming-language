# Installing MellowLang 2.9.6

Mellow 2.9.6 is a C-first release. The recommended installation path is the
standalone native `mellow` executable, which can run and check `.mellow` files
without Python.

Python tooling still exists for development-only features such as the legacy
package CLI surface, LSP backend, extended tests, and some experimental tools.
Install it only when you need those tools.

## What gets installed

The native install is intentionally small:

```text
mellow.exe / mellow      native C CLI
mellowrt.exe / mellowrt  native runtime alias
```

Supported native commands in 2.9.6:

```text
mellow help
mellow run <file.mellow>
mellow check <file.mellow>
mellow doctor
mellow status
mellow --runtime-info
mellow --version
```

Expected native doctor output includes:

```text
Runtime       : mellow-c standalone
Python        : not required
[OK] python_free: this command did not require Python
```

## Windows

### Fresh install from Git

```powershell
git clone https://github.com/seashyne/mellow-programming-language.git
cd mellow-programming-language
.\scripts\install-native.ps1
mellow doctor
mellow run examples\hello.mellow
```

If you downloaded a ZIP instead of using Git, extract it, open PowerShell inside
the extracted folder, then run:

```powershell
.\scripts\install-native.ps1
```

### Recommended: one-command native install

From the repository root:

```powershell
.\scripts\install-native.ps1
```

This builds the native C runtime, installs it to:

```text
%LOCALAPPDATA%\MellowLang\bin\mellow.exe
```

and moves that directory to the front of your user PATH.

Open a new terminal and verify:

```powershell
where mellow
mellow doctor
```

Uninstall the native CLI:

```powershell
.\scripts\install-native.ps1 -Uninstall
```

Install to a custom directory:

```powershell
.\scripts\install-native.ps1 -Prefix E:\tools\mellow\bin
```

### Manual native install from source

Requirements:

- Windows 10 or newer
- CMake 3.16+
- Visual Studio Build Tools, MSVC, clang-cl, or another C compiler supported by CMake

From the repository root:

```powershell
cmake -S native\standalone -B build\standalone-release -DCMAKE_BUILD_TYPE=Release
cmake --build build\standalone-release --config Release
New-Item -ItemType Directory -Force -Path bin | Out-Null
Copy-Item build\standalone-release\Release\mellow.exe bin\mellow.exe -Force
Copy-Item build\standalone-release\Release\mellowrt.exe bin\mellowrt.exe -Force
```

Add the `bin` directory to the front of your user PATH:

```powershell
$nativeBin = "E:\software\MellowLang\bin"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$parts = @()
if ($userPath) { $parts = $userPath -split ";" | Where-Object { $_ -and $_ -ne $nativeBin } }
[Environment]::SetEnvironmentVariable("Path", ($nativeBin + ";" + ($parts -join ";")).TrimEnd(";"), "User")
```

Open a new terminal and verify:

```powershell
where mellow
mellow doctor
mellow run E:\software\MellowLang\examples\hello.mellow
```

`where mellow` should show the native executable before any Python launcher:

```text
E:\software\MellowLang\bin\mellow.exe
```

### Portable usage without PATH

You can run directly from the repository:

```powershell
E:\software\MellowLang\bin\mellow.exe doctor
E:\software\MellowLang\bin\mellow.exe run E:\software\MellowLang\examples\hello.mellow
```

The root wrappers also use the native binary when `bin\mellow.exe` exists:

```powershell
.\mellow.cmd doctor
.\mellow.ps1 run examples\hello.mellow
```

### Remove the old Python launcher

If an older Python install shadows the native CLI:

```powershell
where mellow
python -m pip uninstall mellowlang -y
```

Then open a new terminal and run:

```powershell
where mellow
mellow doctor
```

## Linux

### Fresh install from Git

```bash
git clone https://github.com/seashyne/mellow-programming-language.git
cd mellow-programming-language
sh scripts/install-native.sh --add-path
export PATH="$HOME/.local/bin:$PATH"
mellow doctor
mellow run examples/hello.mellow
```

If you downloaded a ZIP instead of using Git, extract it, open a shell inside
the extracted folder, then run:

```bash
sh scripts/install-native.sh --add-path
```

### Recommended: one-command native install

From the repository root:

```bash
sh scripts/install-native.sh --add-path
```

This builds the native C runtime and installs it to:

```text
~/.local/bin/mellow
```

Open a new shell or run `export PATH="$HOME/.local/bin:$PATH"`, then verify:

```bash
which mellow
mellow doctor
```

Uninstall:

```bash
sh scripts/install-native.sh --uninstall
```

Install to a custom prefix:

```bash
sh scripts/install-native.sh --prefix /opt/mellow --add-path
```

### Manual native build from source

Requirements:

- glibc-based Linux distribution, Ubuntu 20.04+ recommended
- `cmake`
- `gcc` or `clang`

Install build tools on Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y build-essential cmake
```

Build and install to `~/.local/bin`:

```bash
cmake -S native/standalone -B build/standalone-release -DCMAKE_BUILD_TYPE=Release
cmake --build build/standalone-release --parallel
mkdir -p ~/.local/bin
cp build/standalone-release/mellow ~/.local/bin/mellow
cp build/standalone-release/mellowrt ~/.local/bin/mellowrt
chmod +x ~/.local/bin/mellow ~/.local/bin/mellowrt
```

Make sure `~/.local/bin` is on PATH:

```bash
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc ;;
esac
```

Open a new shell or run:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Verify:

```bash
which mellow
mellow doctor
mellow run examples/hello.mellow
```

### System-wide Linux install

For machines where you control `/usr/local/bin`:

```bash
sudo install -m 0755 build/standalone-release/mellow /usr/local/bin/mellow
sudo install -m 0755 build/standalone-release/mellowrt /usr/local/bin/mellowrt
mellow doctor
```

Use this for CI images, containers, and shared development boxes where the
native CLI should be available to every user.

## macOS

### Fresh install from Git

```bash
git clone https://github.com/seashyne/mellow-programming-language.git
cd mellow-programming-language
sh scripts/install-native.sh --add-path
export PATH="$HOME/.local/bin:$PATH"
mellow doctor
mellow run examples/hello.mellow
```

If you downloaded a ZIP instead of using Git, extract it, open Terminal inside
the extracted folder, then run:

```bash
sh scripts/install-native.sh --add-path
```

### Recommended: one-command native install

From the repository root:

```bash
sh scripts/install-native.sh --add-path
```

This builds the native C runtime and installs it to:

```text
~/.local/bin/mellow
```

Open a new terminal or run `export PATH="$HOME/.local/bin:$PATH"`, then verify:

```bash
which mellow
mellow doctor
```

Uninstall:

```bash
sh scripts/install-native.sh --uninstall
```

Install to a custom prefix:

```bash
sh scripts/install-native.sh --prefix /opt/mellow --add-path
```

### Manual native build from source

Requirements:

- macOS 12+
- Xcode Command Line Tools
- CMake

Install tools:

```bash
xcode-select --install
brew install cmake
```

Build and install to `~/.local/bin`:

```bash
cmake -S native/standalone -B build/standalone-release -DCMAKE_BUILD_TYPE=Release
cmake --build build/standalone-release --parallel
mkdir -p ~/.local/bin
cp build/standalone-release/mellow ~/.local/bin/mellow
cp build/standalone-release/mellowrt ~/.local/bin/mellowrt
chmod +x ~/.local/bin/mellow ~/.local/bin/mellowrt
```

Add the path for zsh:

```bash
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc ;;
esac
export PATH="$HOME/.local/bin:$PATH"
```

Verify:

```bash
which mellow
mellow doctor
mellow run examples/hello.mellow
```

### System-wide macOS install

```bash
sudo install -m 0755 build/standalone-release/mellow /usr/local/bin/mellow
sudo install -m 0755 build/standalone-release/mellowrt /usr/local/bin/mellowrt
mellow doctor
```

## Recommended usage

### Run scripts

```bash
mellow run hello.mellow
```

Direct invocation also works in the native CLI:

```bash
mellow hello.mellow
```

Prefer `mellow run` in docs and tutorials because it is clearer for beginners.

### Check scripts in editors or CI

```bash
mellow check src/main.mellow
```

The native checker compiles the source and reports syntax/compiler errors without
running the program.

### Use from another app

The simplest embedding path today is process-based:

```bash
mellow run path/to/script.mellow
```

For host applications that want an in-process API, 2.9.6 includes the
experimental C embedding header:

```text
native/standalone/include/mellow_runtime.h
```

This ABI is intentionally marked experimental. Use it for prototypes and host
runtime experiments, but keep the standalone `mellow` process path as the stable
deployment surface for now.

### Use in CI

Minimal native gate:

```bash
mellow doctor
mellow check tests/fixtures/full_native_core.mellow
mellow run tests/fixtures/full_native_core.mellow
```

This gate does not require Python.

## npm install

Mellow also provides an npm package wrapper for developers who prefer:

```bash
npm install -g mellowlang
```

The npm package is still native-first. Node.js is only used as an
installer/wrapper; the command it runs is the standalone C `mellow` executable.

From a source checkout today:

```bash
npm install -g ./packages/npm/mellowlang
mellow doctor
mellow run examples/hello.mellow
```

Expected output still includes:

```text
Python        : not required
```

If the npm wrapper cannot find a native executable, install CMake and a C
compiler, then reinstall the package. You can also force a native executable
path:

```bash
MELLOW_NATIVE_EXE=/path/to/mellow mellow doctor
```

## Optional Python tooling

Only install the Python package when you need compatibility tooling:

```bash
python -m pip install -e .[lsp]
python -m pip install -e .[all]
```

Use cases:

- LSP backend during editor development
- extended package/registry commands not yet migrated to C
- full pytest suite
- experimental AI, media, MELV bridge, and framework tooling

If you install Python tooling and native Mellow on the same machine, keep the
native `bin` directory before Python `Scripts` on PATH.

## VS Code extension

The VS Code extension lives in:

```text
vscode-extension/
```

Install the local VSIX:

```powershell
code --install-extension E:\software\MellowLang\vscode-extension\mellowlang-2.9.6.vsix --force
```

Set `MellowLang: Executable Path` to the native CLI if auto-detection does not
find it:

```text
E:\software\MellowLang\bin\mellow.exe
```

## Troubleshooting

### `mellow doctor` still shows Python

Your PATH is still finding a Python launcher first.

Windows:

```powershell
where mellow
python -m pip uninstall mellowlang -y
```

Linux/macOS:

```bash
which -a mellow
python -m pip uninstall mellowlang -y
```

Then move the native install directory to the front of PATH and open a new
terminal.

### `mellow` is not found after editing PATH

Open a new terminal. On Windows, environment variable changes are not always
visible to already-open shells.

### `--help` or old commands behave differently

The native 2.9.6 CLI intentionally exposes the stable native surface first:
`help`, `run`, `check`, `doctor`, `status`, `--runtime-info`, and `--version`.
Extended commands remain Python tooling until they are migrated to C.

## System requirements

| Requirement | Windows | Linux | macOS |
| --- | --- | --- | --- |
| OS | Windows 10+ | Ubuntu 20.04+ or equivalent | macOS 12+ |
| Build tool | Visual Studio Build Tools / MSVC / clang-cl | gcc or clang | Xcode Command Line Tools |
| Build system | CMake 3.16+ | CMake 3.16+ | CMake 3.16+ |
| Python | Optional tooling only | Optional tooling only | Optional tooling only |
| Disk | about 2 MB for native binaries | about 2 MB for native binaries | about 2 MB for native binaries |
