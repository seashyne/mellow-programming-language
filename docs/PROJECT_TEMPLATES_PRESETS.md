# Mellow v2.1.6 Project Templates + Presets

Presets available through `mellow new`:

- `starter`
- `app`
- `automation`
- `ai-agent`
- `gamekit`
- `api-webhook`

## Examples

```bash
mellow new hello-app --preset app
mellow new orders-bot --preset automation
mellow new studio-agent --preset ai-agent
mellow new pixel-runner --preset gamekit
mellow new webhook-api --preset api-webhook
```

## Desktop windows from `.mel`

The `app` preset ships with `core-window` and works with:

```bash
mellow desktop run src/main.mel
```

Supported declarative calls in the source file:

```mel
import "pkg:core-window" as win

keep app = win.window(title: "Mellow App", width: 960, height: 640)
win.label(app, "Hello from Mellow")
win.input(app, "Type here")
win.button(app, "Close", "close")
win.run(app)
```
