# MellowLang Language Support

VS Code support for `.mellow` and `.mel` files:

- Syntax highlighting for Mellow 2.9.7 native syntax and built-ins
- Diagnostics
- Completion and hover
- Document symbols
- Go to definition
- Mellow logo file icon theme

The grammar recognizes the 2.9.7 native C surface, including `var`, `keep`,
`null`, `none`, `elif`, `wait`, `stop`, `break`, `continue`, builtin modules
(`io`, `sys`, `math`, `time`, `gc`, `thread`, `chan`), and native built-ins such
as `gc_collect`, `gc_stats`, `spawn`, `yield`, `channel`, `send`, and `recv`.

The extension starts `mellow lsp` automatically. Install Mellow with LSP support:

```powershell
python -m pip install -e ".[lsp]"
mellow doctor
```

Set `mellowlang.executablePath` in VS Code settings if `mellow` is not available
on PATH. See `../docs/LSP.md` for complete setup and troubleshooting instructions.

## File icon

To show the small Mellow logo on `.mellow` and `.mel` files:

1. Open **Preferences: File Icon Theme**.
2. Select **Mellow File Icons**.
