# Mellow 1.6.5.1 - LSP Compatibility Hotfix

## Fixed
- Mellow LSP now supports both pygls v1 and pygls v2 import layouts.
- `mellow doctor` now reports LSP backend readiness and surfaces pygls import issues.
- `mellow doctor --strict` now fails when LSP compatibility problems are detected.
- `mellow lsp` now shows an actionable setup message instead of a vague missing-pygls failure.

## Packaging
- Relaxed and clarified the `pygls` dependency range to `>=1.3.1,<3`.

## Recommended reinstall
```bash
python -m pip uninstall mellowlang
python -m pip install -e .
```
