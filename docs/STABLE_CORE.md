# Stable Core

This document defines the stable implementation surface for Mellow Programming Language releases.
The normative grammar and semantics for the 2.9 release line are frozen in
[`LANGUAGE_SPEC_2_9.md`](LANGUAGE_SPEC_2_9.md).
The top-level specification entry point is [`../SPEC.md`](../SPEC.md), and the
v3 stability track is defined in [`V3_STABILITY_PLAN.md`](V3_STABILITY_PLAN.md).

Core documentation index: [`CORE_DOCS.md`](CORE_DOCS.md)

Experimental surfaces are indexed separately in
[`experimental/README.md`](experimental/README.md).

`tests/core` plus `tests/language` are the language release gate. Starting in
v2.4.0, `tests/native` is also required for releases that claim native C parity
for the stable core.

## Stable Language Features

- `let` assignment and reassignment
- `def` functions and return values
- `if`, `while`, and `for`
- `range(...)`
- list literals and indexing
- map literals and indexing
- strings, numbers, booleans, and `none`/`null`
- basic math/string/list/map/json/money/data/ledger host helpers
- `mellow-sdk` OpenAI-compatible provider package (extended host; see `MELLOW_SDK.md`)

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
- `mellow release-gate` (includes stability pytest gates in 2.9.3+)

## Optional But Supported

These features are allowed to be missing from a default install and should be reported by `mellow doctor`:

- `lsp`: language server support
- `net`: websocket/network helpers
- `security`: signing and secure-save helpers
- `video`: MELV video encode/decode
- native VM: default engine with stable-core, money, data, and ledger parity
- Full Native C CLI: lexer, compiler, bytecode VM, and Core built-ins
- finance sandbox profile: supports native execution with storage denial enforced in the C VM
- data processing core: bounded JSONL/CSV streams and parameterized SQLite on both Python and C engines
- ledger core: immutable balanced entries with deterministic hash-chain verification
- `frameworks.mellow_ui`: Python UI framework with an in-memory renderer

## Experimental And Extended

These surfaces may be present in the repository but must not block a stable
release unless they are explicitly added to a release gate:

- extended regression suite (`tests/test_v*` outside the 2.9.3 smoke list)
- agent runtime and hosted platform → [`experimental/README.md`](experimental/README.md)
- MMG and video runtime → [`experimental/README.md`](experimental/README.md)
- desktop/playground runtimes → [`experimental/README.md`](experimental/README.md)

## Release Rule

A **2.9.3** patch release is considered stable when:

```powershell
.\scripts\test-v293-stability.ps1
```

This runs:

- `tests/core`
- `tests/language`
- package/registry smoke tests
- `mellow release-gate`

Additional native requirements:

- `python -m pytest -q tests/native -p no:cacheprovider` passes for native-core releases
- `tests/fixtures/full_native_core.mellow` produces the frozen conformance output in both runtimes
- README version matches `pyproject.toml`
- `CHANGELOG.md` has an entry for the release

For the v3 stability track, see [`V3_STABILITY_PLAN.md`](V3_STABILITY_PLAN.md).
