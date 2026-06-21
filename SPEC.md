# Mellow Programming Language Specification

This is the top-level specification entry point for Mellow.

## Current Normative Baseline

The frozen language baseline is:

- Language line: `2.9`
- Profile: `core`
- Normative document: `docs/LANGUAGE_SPEC_2_9.md`
- Machine-readable manifest: `spec/mellow-2.9-core.json`
- Conformance fixture: `tests/fixtures/full_native_core.mellow`

When user-facing guides and the normative specification disagree, the
normative specification wins.

## v3 Stability Track

Mellow v3.0.0 is planned as the first Language Stability Release. Its purpose
is not to add as many features as possible; it is to make the language
credible, testable, and safe to build on.

The v3 track is governed by:

- `docs/V3_STABILITY_PLAN.md`
- `docs/LANGUAGE_SPEC_3_0.md`
- `docs/RUNTIME_PARITY_3_0.md`
- `spec/mellow-3.0-stability.json`
- `tests/language/`

## Compatibility Rules

- Patch releases must not change the meaning of valid Core Profile programs.
- Minor releases may add syntax only when the spec, manifest, tests, and docs
  are updated together.
- Major releases may remove or change previously stable syntax, but must
  document migration steps.
- Experimental and host-specific features must be labeled as such.
- A feature is not stable until it has a spec entry and an automated test.

## Implementation Targets

Mellow may have multiple runtimes, but the language contract is shared:

- Python VM: reference and tooling-friendly implementation.
- Native C VM: default runtime direction for stable-core execution.
- Host modules: capability-gated standard and integration APIs.
- Package ecosystem: versioned packages with registry, lockfile, checksum, and
  install/update workflows.

## Release Gate

Stable **2.9.3** patch releases must pass:

```powershell
.\scripts\test-v293-stability.ps1
```

The v3 track baseline remains:

```powershell
py -3.11 -m pytest -q tests/core tests/language -p no:cacheprovider
```

Native-core releases must also pass:

```powershell
py -3.11 -m pytest -q tests/native -p no:cacheprovider
```

## Patch Release 2.9.3

- Manifest: `spec/mellow-2.9.3-stability.json`
- Canonical runtime modules: `compiler/bytecode.py`, `host/runtime.py`, and
  `vm/python_vm.py`
- Experimental docs index: `docs/experimental/README.md`
