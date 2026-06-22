# Starter packages that ship with Mellow

These packages are published into the local registry and also included as editable source under `starter_packages/`.
All starter package entries are authored in `.mel` and also ship with a `.mellow` mirror for compatibility.
Core package manifests are marked with `authors = ["Mellow Code Team"]`,
`license = "MIT"`, an `official` badge, and focused keywords for registry
search. `core-save` is additionally marked `deprecated`; use `core-storage` for
new projects.

## Essential

- `core-print` — output helpers
- `core-strings` — string helpers
- `core-collections` — list/map helpers
- `core-math` — clamp, lerp, and distance helpers
- `core-json` — JSON wrappers
- `core-time` — clock/timing helpers

These are the default starter set for `mellow new`.

## Application

- `core-storage` — save/load statement helpers
- `core-http` — request and route descriptors for host integrations
- `core-workflow` — job/event payload helpers
- `core-save` — compatibility persistence helpers; prefer `core-storage`

## Domain

- `core-money` — decimal-backed money helpers
- `core-data` — bounded data transforms and file/SQLite host wrappers
- `core-ledger` — double-entry ledger helpers

## Optional Surfaces

- `core-ai` — AI runtime wrappers
- `mellow-sdk` — OpenAI-compatible chat SDK (OpenAI, DeepSeek, compatible APIs)
- `core-gamekit` — game helpers
- `core-window` — desktop window declarations
- `core-mmg` — Mellow Magic Graphics declarations

`core-sm` and `core-melv` currently have source stubs and local-registry
packages, but are not included by `seed-core` until their starter manifests
are complete.

## Local source
```bash
starter_packages/<package>/src/main.mel
```

## Generate again
```bash
mellow seed-core ./starter_packages --publish-local
```

`seed-core` copies the package manifests and sources already stored under
`starter_packages/`; it does not maintain a second set of generated templates.

All starter package entries compile with the Mellow 2.9 block syntax. New
feature releases use immutable package versions such as `0.2.0`; old `0.1.0`
local registry versions remain available for compatibility.
