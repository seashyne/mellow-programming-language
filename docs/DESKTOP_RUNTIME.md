# Desktop Runtime

Mellow desktop projects can now define simple cross-platform windows directly in `.mel` files.

## Supported surface

- `win.window(...)`
- `win.vstack(...)`
- `win.hstack(...)`
- `win.grid(...)`
- `win.menu(...)`
- `win.menu_item(...)`
- `win.label(...)`
- `win.input(..., bind: name)`
- `win.textarea(..., bind: notes)`
- `win.checkbox(..., bind: enabled)`
- `win.select(..., options: ["A", "B"], bind: mode)`
- `win.button(..., "inc:count")`

## Event actions

- `close`
- `print:message`
- `set:key=value`
- `inc:key`
- `toggle:key`

## Build flow

```bash
mellow desktop build src/main.mel --out dist/desktop
```

This command creates:

- a launcher script
- a PyInstaller spec
- Windows and Linux helper build scripts
- `bundle.json` metadata

When PyInstaller is installed, Mellow will also invoke it automatically.
