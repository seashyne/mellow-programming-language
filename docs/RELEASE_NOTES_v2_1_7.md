# Mellow v2.1.7 Desktop Runtime Pack

## Highlights

- richer desktop host for Windows and Linux via Tkinter-backed runtime
- layout primitives: `vstack`, `hstack`, `grid`
- menu support: `menu`, `menu_item`
- event actions: `close`, `print:*`, `set:key=value`, `inc:key`, `toggle:key`
- state binding for labels and inputs with `{{state.name}}` interpolation and `bind:`
- desktop bundle scaffolding with `mellow desktop build`
- generated PyInstaller spec plus Windows/Linux helper scripts

## Commands

```bash
mellow desktop status
mellow desktop run src/main.mel
mellow desktop run src/main.mel --dump-spec
mellow desktop build src/main.mel --out dist/desktop --onefile
```

## Notes

- runtime is cross-platform for Windows and Linux where Python + Tk are available
- bundle build uses PyInstaller when installed on the target OS
- if PyInstaller is missing, Mellow still generates a spec and build scripts so the app can be packaged later
