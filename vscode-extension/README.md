# MellowLang Language Support

VS Code support for `.mellow` and `.mel` files:

- Syntax highlighting
- Diagnostics
- Completion and hover
- Document symbols
- Go to definition

The extension starts `mellow lsp` automatically. Install Mellow with LSP support:

```powershell
python -m pip install -e ".[lsp]"
mellow doctor
```

Set `mellowlang.executablePath` in VS Code settings if `mellow` is not available
on PATH. See `../docs/LSP.md` for complete setup and troubleshooting instructions.
