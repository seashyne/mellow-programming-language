# Mellow v1.9.5 — Playground Pack

This release adds a first real local Mellow Playground with:

- browser UI for editing and running Mellow code
- compile/run API backed by the existing compiler and VM
- AST / IR / CFG / SSA inspection panes
- example loader for bundled scripts
- new CLI entrypoint: `mellow playground`

## CLI

```bash
mellow playground
mellow playground --port 8787
mellow playground --build-only --out .mellow/playground
```

## Features

- code editor with keyboard shortcut (`Ctrl/Cmd + Enter`)
- output tabs for stdout, result, optimization summary
- compiler inspector for AST, IR, optimized IR, CFG, optimized CFG, SSA, optimized SSA
- sandboxed local execution using a temporary project workspace

## Notes

- the playground defaults to local-only serving on `127.0.0.1`
- networking remains disabled unless the UI explicitly enables it
- scripts execute inside a temporary sandbox directory per run
