# Mellow Project Structure

This repository should keep source code, fixtures, generated artifacts, and local caches clearly separated.

## Source Of Truth

- `src/mellowlang/` - Python source for the language, compiler, VM, runtimes, package manager, and CLI.
- `native/` - Native C/CMake runtimes and extensions.
- `stdlib/` - Built-in standard library packages.
- `starter_packages/` - Source templates for official starter packages.
- `frameworks/` - Optional framework packages maintained with the repo.
- `tests/` - Test suites and stable fixtures.
- `docs/` - Current manuals, specs, policy docs, and release documentation.
- `examples/` - Hand-written examples that should be readable and intentionally maintained.
- `deploy/` - Deployment projects and infrastructure source only.
- `packaging/` - Distribution scripts/specs.

## Generated Or Local Only

These should not be committed unless there is a specific fixture reason:

- `.ci-logs/`
- `.ci-tmp/`
- `.mellow/`
- `.mellow-release-gate-work/`
- `.mellow-data-benchmark-*`
- `.tmp_*`
- `outputs/`
- `build/`
- `dist/`
- `node_modules/`
- `.wrangler/` in deployment workspaces
- `mellow_packages/installed/`
- `examples/mellow_packages/installed/`
- `native/**/build/`
- root `.mellow_aliases.json`, `.mellow_imports.json`, `.mellow_runtime.json`
- root `mellow.lock` unless it is intentionally used as a project-level fixture

## Package Data

`mellow_packages/registry/` is currently used as an in-repo registry fixture. Keep only curated package versions there. Installed packages and local cache output belong under `mellow_packages/installed/` and are ignored.

Longer term, prefer this layout:

```text
mellow_packages/
  registry/       curated registry fixtures
  README.md       explains fixture policy
```

Local installs should live outside the repository or under ignored cache directories.

## Documentation

Current docs stay in `docs/`. Historical per-version release notes live in `docs/releases/` so `docs/` remains scannable.

Recommended future layout:

```text
docs/
  guides/
  specs/
  policies/
  releases/
```

## CLI Code

The CLI should remain modular:

```text
src/mellowlang/cli/
  main.py          thin entrypoint and command dispatch only
  common.py        shared CLI helpers, JSON output, error formatting, lazy imports
  parser.py        argparse definitions
  ux.py            help, guide, ask, aliases
  commands/
    agents.py      agent runtime, workflow, queue, policy, and marketplace commands
    compiler.py    compile and pack commands
    media.py       desktop, MMG, MELV, and state-machine commands
    packages.py    package and registry commands
    project.py     init, new, check, and format commands
    runtime.py     run, test, record, replay, and diff commands
    standalone.py  standalone native runtime commands
    system.py      doctor, status, config, bench, security, and native commands
```

`main.py` must not define command handlers. New command families belong in
`cli/commands/`; parser definitions remain in `cli/parser.py`.

## Package System

`package_manager.py` is the compatibility facade for existing imports. Focused
implementation lives under `src/mellowlang/packages/`:

```text
packages/
  config.py        registry/auth/trust configuration and aliases
  metadata.py      package names, creators, authors, and versions
  manifest.py      manifest discovery and TOML serialization
  lockfile.py      lockfile, import map, and runtime map handling
  project.py       project roots, presets, local packages, and scaffolding
```

New package features should be implemented in the focused module and exported
through `package_manager.py` only when compatibility requires it.

## VM Code

The Python VM keeps execution and opcode dispatch in `vm/python_vm.py`. Services
with a separate concern are mixed in without changing the public VM class:

- `vm/debugger.py` - breakpoints, snapshots, stepping, and watch expressions.
- `vm/storage.py` - sandboxed paths, filesystem permissions, and JSON storage.

Keep hot opcode execution in the VM core unless profiling proves a different
boundary is better.

## Cleanup Rules

- Do not remove or move dirty tracked files without checking `git status`.
- Add ignores before running generators.
- Keep generated package installs out of `mellow_packages/registry/`.
- If a generated output is needed for a test, place it under `tests/fixtures/` and document why.
