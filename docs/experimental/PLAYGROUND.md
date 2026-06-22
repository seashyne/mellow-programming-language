# Mellow Playground

Mellow Playground is a local browser-based environment for writing, compiling, and running Mellow scripts.

## Start it

```bash
mellow playground
```

Open the printed URL in your browser.

## Build static assets only

```bash
mellow playground --build-only --out .mellow/playground
```

## What the UI includes

- code editor
- run and compile-only actions
- example loader
- VM selector (`auto`, `py`, `c`)
- optimization toggle
- compiler inspector for AST, IR, CFG, SSA

## API endpoints

- `GET /api/health`
- `GET /api/examples`
- `POST /api/run`
- `POST /api/compile`

The playground server is intended for local development and demos.
