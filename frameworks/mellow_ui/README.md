# Mellow UI Framework v1

Mellow UI is a lightweight React-like UI framework for the Mellow Programming Language ecosystem.

It provides a declarative way to describe interfaces using virtual elements, function components, reusable built-in components, and root rendering. Version 1 focuses on the UI core and an in-memory renderer so it can be tested safely before adding a Roblox renderer.

## Goals

- React-like `createElement`
- Function components
- `createRoot(...).render(...)`
- Built-in UI components
- Simple state object via `useState`
- In-memory normalized UI tree output
- Foundation for a future Roblox/Luau renderer

## Python runtime usage

```python
import frameworks.mellow_ui as UI


def Hello(props):
    return UI.createElement("TextLabel", {
        "Text": "Hello " + props["name"]
    })


def App(props):
    return UI.createElement("Screen", {
        "Name": "Main",
        "Children": [
            UI.createElement(Hello, {"name": "Mellow"}),
            UI.Button("Play", {"Size": [220, 54]}),
        ]
    })

root = UI.createRoot("App")
tree = root.render(UI.createElement(App, {}))
print(tree)
```

You can also run a built-in demo renderer:

```bash
python -m frameworks.mellow_ui
```

It prints a normalized JSON UI tree that tools, previews, or future renderers can consume.

## Target Mellow syntax (planned)

```mellow
let UI = import("mellow.ui")

def App(props):
    return UI.createElement("Screen", {
        "Name": "Main",
        "Children": [
            UI.createElement("TextLabel", {
                "Text": "Hello Mellow UI"
            })
        ]
    })

let root = UI.createRoot("App")
root.render(UI.createElement(App, {}))
```

The Python framework is the stable v1 surface. Direct `import("mellow.ui")` from Mellow scripts is planned for a later bridge layer.

## Built-in components

- `Screen(props)`
- `Frame(props)`
- `TextLabel(text, props)`
- `Button(text, props)`
- `ProgressBar(value, props)`

## Roadmap

### v1

- Virtual element core
- Function component rendering
- Built-in component helpers
- Simple state object
- Tests and examples

### v2

- Real hook lifecycle
- Re-render scheduling
- Diff and patch
- Event bridge

### v3

- Roblox renderer
- Luau export
- Rojo project templates
- UI preview tooling

## Notes

This framework is inspired by declarative component UI frameworks, but it is an original small implementation for the Mellow ecosystem. It does not copy React Luau source code.
