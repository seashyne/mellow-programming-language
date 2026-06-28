# mellow-web

Experimental Mellow web UI package that targets React TSX without making React
part of the core language.

Use it in a project:

```bash
mellow add mellow-web
```

```mellow
use mellow-web as web

page Counter
  state count = 0

  view:
    Stack(gap: 12)
      Title("Mellow Counter")
      Text("Count: {count}")
      Button("Add", onClick: count += 1)
```

Generate TSX:

```bash
mellow web build src/Counter.mellow --out src/Counter.tsx
```

Run a React/Vite dev server directly:

```bash
mellow web dev
```

By default, `mellow web dev` looks for `web.entry` in `mellow.json` or
`mellow.toml`, then falls back to common files like `src/main.mellow` or
`src/App.mellow`. You can still pass a file explicitly:

```bash
mellow web dev src/Counter.mellow
```

Recommended `mellow.json` config:

```json
{
  "name": "my-web-app",
  "web": {
    "entry": "src/App.mellow",
    "out_dir": ".mellow/web-dev",
    "host": "127.0.0.1",
    "port": 5179
  }
}
```

CLI flags override config:

```bash
mellow web dev --port 5180 --dir .mellow/preview
```

`mellow web dev` checks for the `mellow-web` package in the current project and
installs the local starter package when it is missing. The web syntax remains in
the package layer; the core command is only a launcher for the package target.

If you want an npm-style project command, add this to your project
`package.json`:

```json
{
  "scripts": {
    "dev": "mellow web dev"
  }
}
```

Initial supported UI nodes:

- `Stack(gap: 12)`
- `Row(gap: 8)`
- `Card(...)`
- `Title("...")`
- `Subtitle("...")`
- `Text("Count: {count}")`
- `Button("Add", onClick: count += 1)`

The package name is `mellow-web`; React is the first backend target. If this
later ships to npm, `@mellow/react` is a good companion package name for the
React-specific runtime/tooling.
