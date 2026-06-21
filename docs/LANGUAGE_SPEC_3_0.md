# Mellow Programming Language Specification 3.0

Status: **Draft for the Mellow v3.0.0 Language Stability Release**

This document is the candidate v3 specification. Until v3.0.0 is promoted, the
frozen normative baseline remains `docs/LANGUAGE_SPEC_2_9.md`.

## 1. Stability Model

Every language feature must be classified:

- `core`: stable, portable, and release-gated.
- `extended`: supported but outside the minimum portable profile.
- `experimental`: available for feedback; behavior may change.

A feature is not stable unless it has:

1. a spec entry,
2. an automated test,
3. user-facing documentation.

## 2. Core Profile

The v3 Core Profile starts from the frozen 2.9 Core Profile:

- UTF-8 `.mellow` source files
- indentation blocks using four spaces
- `let` and `keep` declarations
- assignment
- `def` functions and `return`
- `if` / `else`
- `while`
- `for ... in range(...)`
- list and map literals
- indexing
- arithmetic, comparison, and boolean operators
- `true`, `false`, and `none`
- standard built-ins listed in `spec/mellow-2.9-core.json`

## 3. Extended Profile

The Extended Profile may include:

- package imports: `use <package> as <alias>` and `need <package> as <alias>`
- host modules through `get module.function(...)`
- package registry commands
- interop through the `interop` host module
- framework packages

Extended features must have docs and tests, but may depend on host runtime
capabilities.

## 4. Experimental Profile

The following areas are experimental until promoted:

- agent runtime and hosted platform
- MMG/video runtimes
- desktop runtime beyond documented declarative subsets
- standalone image loading beyond the stable core
- native runtime features marked partial in `docs/RUNTIME_PARITY_3_0.md`

## 5. Runtime Contract

Python VM is the reference implementation. Native C is the default runtime
direction. Any behavior difference must be listed in
`docs/RUNTIME_PARITY_3_0.md`.

## 6. Package And Interop Contract

Package and interop behavior is part of the platform, not the minimal language
grammar.

- Packages must use versioned manifests and lockfiles.
- Registry installs must validate checksums when available.
- Interop must be deny-by-default and allowlisted by command.
- Interop uses JSON stdin/stdout; shell execution is not stable.

## 7. Conformance

The v3 draft gate is:

```powershell
py -3.11 -m pytest -q tests/core tests/language -p no:cacheprovider
```

Package ecosystem smoke:

```powershell
.\scripts\test-v3-stability.ps1
```
