# MellowLang 1.6.5

## What changed

- Polished VS Code + LSP experience
- Added hover docs for keywords and builtins
- Added document symbols for skills, events, and top-level variables
- Added go-to-definition for local `skill` declarations
- Improved diagnostics severity mapping in the language server
- Extended VS Code extension auto-detection for local virtual environments
- Added `MellowLang: Run Doctor` command in VS Code
- Upgraded `mellow doctor` to detect version/install mismatches automatically
- Added `mellow doctor --strict` to fail CI when a mismatch is detected

## Recommended commands

```bash
mellow doctor
mellow doctor --strict
mellow lsp
```
