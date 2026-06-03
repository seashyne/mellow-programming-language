# MellowLang v1.5.8

- Added recursive dependency install for remote packages.
- Added `mellow.lock` generation for project-aware installs.
- Added `sync-imports` command to scan `.mellow` files, install missing declared dependencies, and generate `.mellow_imports.json`.
- Added lightweight semver support for `*`, exact, `^`, `~`, and `>=` package specs.
