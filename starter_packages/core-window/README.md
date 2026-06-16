# core-window

Starter package for desktop-window style Mellow apps on Windows and Linux.

Use it with:

```bash
mellow desktop run src/main.mel
mellow desktop build src/main.mel --out dist/desktop
```

Supported calls in the `.mel` source:

- `win.window(...)`
- `win.vstack(...)` / `win.hstack(...)` / `win.grid(...)`
- `win.label(...)`
- `win.button(...)`
- `win.input(...)`
- `win.textarea(...)`
- `win.checkbox(...)`
- `win.select(...)`
- `win.menu(...)`
- `win.menu_item(...)`
- `win.run(...)`

Use positional arguments in compiled Mellow source:

```mel
keep app = win.window("Demo", 800, 520)
win.label(app, "Hello")
win.button(app, "Close", "close")
win.run(app)
```
