# Mellow v2.1.5 Package Runtime Integration Pack

## Added
- `mellow new` command to scaffold a project with starter packages preloaded.
- Project-local package installation for starter/core packages.
- Project-aware package resolution for `.mellow_runtime.json` and `pkg:` imports.
- Automatic starter package preload from `mellow.json -> starter_packages` during runtime resolution.
- Local-first package install path before remote registry fallback.

## Included starter preload set
- `core-print`
- `core-strings`
- `core-math`
- `core-workflow`

## Notes
- `mellow init` stays available as the minimal legacy template command.
- `mellow new` is the recommended entry point for new projects.
