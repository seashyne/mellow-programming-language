# MellowLang v1.6.3

## New
- Interactive suggestions for `mellow add` and `mellow search`
- Install aliases stored in `.mellow_aliases.json`
- `mellow diagnose-imports <dir>` for import diagnostics and package suggestions

## CLI
- `mellow add core-ai --interactive --project-dir .`
- `mellow add @owner/pkg --alias ai --project-dir .`
- `mellow search core --interactive`
- `mellow diagnose-imports .`

## Notes
- Installing a package now remembers a default alias for faster project resolution.
- Import diagnostics report missing dependencies, alias resolution, and suggestions from the registry.
