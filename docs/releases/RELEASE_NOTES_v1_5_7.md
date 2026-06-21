# MellowLang v1.5.7

## Added
- `mellow seed-core <dir>` and `mellow pkg seed-core <dir>` to generate recommended starter packages.
- Seven core package templates for common Mellow tasks: console output, strings, JSON, HTTP, storage, game scripting, and AI helpers.

## Fixed
- `publish` now reports a clear error when the target directory does not contain `mellow.toml` or `mellow.pkg.json`.
- Package publishing no longer crashes with a raw `PermissionError` when run from the wrong directory.

## Recommended starter packages
- `core-print`
- `core-strings`
- `core-json`
- `core-http`
- `core-storage`
- `core-gamekit`
- `core-ai`
