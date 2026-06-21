# Mellow v3.0.0 Stability Plan

Status: planned

Goal: make Mellow a credible language platform by freezing the stable surface,
removing ambiguity from docs, and requiring tests for every stable behavior.

## Definition Of Done

Mellow v3.0.0 is ready when these gates are green:

- `SPEC.md` points to the current normative language contract.
- `docs/LANGUAGE_SPEC_2_9.md` remains the frozen 2.9 baseline until the v3 spec
  is promoted.
- `docs/LANGUAGE_SPEC_3_0.md` defines the draft v3 classification model.
- `docs/RUNTIME_PARITY_3_0.md` reports Python VM and Native C VM parity.
- `spec/mellow-3.0-stability.json` lists the v3 gate and release criteria.
- `tests/core` passes.
- `tests/language` passes.
- package/registry smoke tests pass.
- native C core parity is either green or documented as partial with a precise
  parity matrix.
- `mellow doctor` reports actionable status.
- README, docs, and `pyproject.toml` agree on the released version.

## Known Language Gaps To Close

- Additional loop forms beyond `while` and `for ... in range(...)` need a single
  normative iteration rule in `LANGUAGE_SPEC_3_0.md` and parity tests before
  promotion.
- Native C behavior must not silently diverge from Python VM behavior for stable
  core programs.

## Workstreams

### 1. Language Specification

- Keep `SPEC.md` as the top-level contract.
- Keep machine-readable manifests under `spec/`.
- Treat user guides as secondary to the normative spec.
- Require a test for every syntax or semantic rule marked stable.

### 2. Runtime Parity

- Python VM remains the reference implementation.
- Native C VM is the default runtime direction.
- Any feature missing from native must be marked `partial`, `fallback`, or
  `unsupported`.
- Stable-core programs must produce the same output on both engines.

### 3. Tests

- `tests/core`: stable core and host module gates.
- `tests/language`: spec and language-contract gates.
- `tests/native`: native runtime parity gates.
- Extended regression tests may remain, but must not define the v3 release contract unless
  they are migrated into the gates above.
- `mellow test` supports exact stdout golden files with `.mellow.out` siblings
  and can require native execution with `--engine=c --native-required`.

### 4. Tooling

- CLI commands must have help text and stable exit codes.
- `mellow check` must be safe for CI.
- LSP diagnostics, hover, completion, and formatting should be tracked as
  tooling maturity items.

### 5. Ecosystem

- Package commands must support search, info, install, add, update, publish,
  lockfiles, and checksums.
- Official starter packages must compile and publish cleanly.
- Registry behavior must be documented and covered by smoke tests.

### 6. Interop

- Interop is stable only through explicit allowlists.
- External runtimes communicate with Mellow through JSON stdin/stdout.
- Direct shell execution is not part of the stable contract.

### 7. Real Demos

The repository keeps small v3-oriented demos under `examples/`:

- `v3_cli_automation.mellow`
- `v3_package_core_usage.mellow`
- `v3_finance_ledger.mellow`
- `v3_interop_node.mellow`
- `v3_game_script.mellow`

## Release Rule

No syntax, runtime, package, or CLI feature should be advertised as stable until
it appears in all three places:

1. specification or stability plan,
2. automated test,
3. user-facing documentation.
