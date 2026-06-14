# Stable Core

This document defines the stable surface for Mellow Programming Language releases.

`tests/core` is the language release gate. Starting in v2.4.0, `tests/native` is also required for releases that claim native C parity for the stable core.

## Stable Language Features

- `let` assignment and reassignment
- `def` functions and return values
- `if`, `while`, and `for`
- `range(...)`
- list literals and indexing
- map literals and indexing
- strings, numbers, booleans, and `none`/`null`
- basic math/string/list/map/json/money/data/ledger host helpers

## Stable CLI

- `mellow --version`
- `mellow run <file>`
- Native C is the default engine; unsupported runtime features fall back to Python
- `mellow run <file> --sandbox=finance`
- `mellow run <file> --sandbox=data`
- `mellow check <file-or-dir>`
- `mellow fmt <files...>`
- `mellow modules --json`
- `mellow doctor`

## Optional But Supported

These features are allowed to be missing from a default install and should be reported by `mellow doctor`:

- `lsp`: language server support
- `net`: websocket/network helpers
- `security`: signing and secure-save helpers
- `video`: MELV video encode/decode
- native VM: default engine with stable-core, money, data, and ledger parity in v2.8.0; installations without the extension fall back to Python
- finance sandbox profile: supports native execution with storage denial enforced in the C VM
- data processing core: bounded JSONL/CSV streams and parameterized SQLite on both Python and C engines
- ledger core: immutable balanced entries with deterministic hash-chain verification
- `frameworks.mellow_ui`: Python UI framework with an in-memory renderer

## Experimental Or Legacy

These surfaces may be present in the repository but should not block a stable release until they have their own green gates:

- full legacy test suite
- agent runtime and hosted platform
- package registry workflows
- MMG and video runtime
- desktop/playground runtimes
- standalone/native parity beyond the stable core, money, data, and ledger surfaces

## Release Rule

A release is considered stable when:

- `python -m pytest -q tests/core -p no:cacheprovider` passes
- `python setup.py build_ext --inplace` succeeds before native parity checks
- `python -m pytest -q tests/native -p no:cacheprovider` passes for native-core releases
- `python -m pytest -q frameworks/mellow_ui/tests -p no:cacheprovider` passes when framework files change
- `mellow doctor` runs without crashing
- `mellow run examples/hello.mellow` works
- README version matches `pyproject.toml`
- `CHANGELOG.md` has an entry for the release
