# Recommended Project Structure (MellowLang)

This repo is arranged to support:
- building `mellowlang.exe` (PyInstaller)
- creating a Windows installer (Inno Setup)
- VS Code syntax + LSP

## Required (runtime / distribution)
- `dist/mellowlang.exe` (after build)
- `docs/` (manual, release notes)
- `examples/` (sample scripts)
- `project_template/` (starter project template)
- `assets/` (icons, installer images)
- `vscode-extension/` (source) and/or a built `.vsix`

## Can be removed from releases
- `build/` (PyInstaller temp)
- `__pycache__/` (Python cache)
- `frinds_saves/` (user local data)
- `*.spec` (PyInstaller spec) if you build only via `build_exe.bat`

## Updating workflow (easy upgrades)
1) Update version in:
   - `src/frinds/__init__.py`
   - `pyproject.toml`
   - `packaging/windows/version_info.txt`
   - `packaging/windows/mellowlang.iss`
2) Rebuild:
   - `packaging/windows/build_exe.bat`
   - (optional) `packaging/windows/build_vsix.bat`
3) Compile installer in Inno Setup.


## v1.0.3 Internal Layout

```
src/mellowlang/
├─ cli.py
├─ compiler/
│  ├─ compiler.py
│  ├─ bytecode.py
│  └─ errors.py
├─ vm/
│  ├─ vm.py
│  └─ runtime.py
├─ host/
│  ├─ modules.py
│  ├─ registry.py
│  └─ python_vm.py
└─ ... (parser/lexer/stdlib/lsp)
```
