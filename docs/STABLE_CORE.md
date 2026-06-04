# Stable Core

This document defines the stable surface for Mellow Programming Language releases.

`tests/core` is the release gate. A release may be tagged when this suite passes, `mellow doctor` runs, and the README and `pyproject.toml` versions agree.

## Stable Language Features

- `let` assignment and reassignment
- `def` functions and return values
- `if`, `while`, and `for`
- `range(...)`
- list literals and indexing
- map literals and indexing
- strings, numbers, booleans, and `none`/`null`
- basic math/string/list/map/json host helpers

## Stable CLI

- `mellow --version`
- `mellow run <file>`
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
- native VM: optional C extension
- `frameworks.mellow_ui`: Python UI framework with an in-memory renderer

## Experimental Or Legacy

These surfaces may be present in the repository but should not block a stable release until they have their own green gates:

- full legacy test suite
- agent runtime and hosted platform
- package registry workflows
- MMG and video runtime
- desktop/playground runtimes
- standalone/native parity beyond core execution

## Release Rule

A release is considered stable when:

- `python -m pytest -q tests/core -p no:cacheprovider` passes
- `python -m pytest -q frameworks/mellow_ui/tests -p no:cacheprovider` passes when framework files change
- `mellow doctor` runs without crashing
- `mellow run examples/hello.mellow` works
- README version matches `pyproject.toml`
- `CHANGELOG.md` has an entry for the release
