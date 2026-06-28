# Native package resolver

Mellow's standalone C runtime includes a minimal package resolver for the
runtime path. It is intentionally smaller than the Python package manager.

Native resolver responsibilities:

- Find the nearest project root from `mellow.json` or `mellow.toml`.
- Accept package imports in native source compilation:
  - `use package-name as alias`
  - `need package-name as alias`
  - `import "pkg:package-name" as alias`
- Resolve installed packages from:
  - `<project>/mellow_packages/installed/<name>/current/package`
  - `<project>/mellow_packages/registry/<name>/0.1.0`
  - `<cwd>/starter_packages/<name>`
  - `<cwd>/mellow_packages/registry/<name>/0.1.0`
- Read package entry metadata from `manifest.json`, `mellow.pkg.json`, or
  `mellow.toml`.
- Reject missing package imports before native bytecode execution.

Still handled by the Python package manager:

- Online registry install/publish.
- Version range solving beyond the local `current` install path.
- Signatures, trust policy, and package archive creation.
- Auto-installing missing packages.

This keeps `mellow run`/`mellow check` on the C path from needing Python for
already-installed package imports, while leaving higher-level package workflows
in Python until they are migrated deliberately.
