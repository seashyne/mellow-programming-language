# Mellow Project Map

You do not need to understand every directory before working on Mellow. Pick the
area that matches the task and stay inside it.

## Start Here

| Task | Directory |
| --- | --- |
| Change syntax, compiler, CLI, or Python compatibility runtime | `src/mellowlang/` |
| Change the default C compiler/runtime | `native/` |
| Change the language contract | `spec/`, `SPEC.md` |
| Add built-in library behavior | `stdlib/` |
| Add or update tests | `tests/` |
| Measure performance or read benchmark reports | `benchmarks/` |
| Work on packages or frameworks | `starter_packages/`, `mellow_packages/`, `frameworks/` |
| Work on integrations | `sdk/`, `plugin_sdk/`, `vscode-extension/` |
| Build releases or deploy services | `packaging/`, `deploy/`, `.github/` |
| Learn the language or add examples | `docs/`, `examples/` |

## Directory Groups

### Language

- `src/mellowlang/` - Compiler v3 pipeline, CLI, compatibility VM, package manager, LSP, and host services.
- `native/` - Native C compiler/runtime and CMake targets used by the default engine.
- `spec/` - Machine-readable syntax locks and language conformance material.
- `stdlib/` - Built-in standard-library modules.

### Quality

- `tests/` - Core, native parity, package, CLI, and integration tests.
- `benchmarks/` - Benchmark programs, runners, raw results, and reports.

### Ecosystem

- `starter_packages/` - Source for official starter packages published to the registry.
- `mellow_packages/` - Curated local registry fixtures; installed packages are ignored.
- `frameworks/` - Optional framework packages maintained with the repository.
- `sdk/`, `plugin_sdk/` - Host-language and plugin integration surfaces.

### Tools And Delivery

- `scripts/` - Development, verification, release, and cleanup commands.
- `vscode-extension/` - Editor extension source.
- `project_template/` - Template copied into new user projects.
- `.github/` - CI and GitHub configuration.
- `packaging/` - Native/distribution packaging configuration.
- `deploy/` - Registry and service deployment projects.

### Documentation

- `docs/` - Current manuals, specifications, policies, and release notes.
- `examples/` - Small maintained Mellow programs.

## Root Files

- `README.md`, `SPEC.md`, `CHANGELOG.md`, `LICENSE` - public project documents.
- `pyproject.toml`, `setup.py` - Python tooling and compatibility distribution metadata.
- `main.py`, `mellow.cmd`, `mellow.ps1`, `install.sh` - thin launch/install wrappers.

New implementation code should not be added at the repository root.

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
- `mellow_models/`

Run `scripts/clean-worktree.ps1` to preview generated files, then
`scripts/clean-worktree.ps1 -Apply` to remove them.

## Package Data

`mellow_packages/registry/` is currently used as an in-repo registry fixture. Keep only curated package versions there. Installed packages and local cache output belong under `mellow_packages/installed/` and are ignored.

Longer term, prefer this layout:

```text
mellow_packages/
  registry/       curated registry fixtures
  README.md       explains fixture policy
```

Local installs should live outside the repository or under ignored cache directories.

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
