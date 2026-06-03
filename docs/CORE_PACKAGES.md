# Starter packages that ship with Mellow

These packages are published into the local registry and also included as editable source under `starter_packages/`.
All starter package entries are authored in `.mel` and also ship with a `.mellow` mirror for compatibility.

## Included
- `core-print` — output helpers
- `core-strings` — string helpers
- `core-json` — JSON wrappers
- `core-time` — clock/timing helpers
- `core-math` — clamp/lerp/distance helpers
- `core-collections` — list/map wrappers
- `core-save` — save/load helpers
- `core-ai` — AI runtime wrappers
- `core-gamekit` — game helpers
- `core-workflow` — job/event payload helpers

## Local source
```bash
starter_packages/<package>/src/main.mel
```

## Generate again
```bash
mellow seed-core ./starter_packages --publish-local
```
