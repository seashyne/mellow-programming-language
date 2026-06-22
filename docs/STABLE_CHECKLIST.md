# Stable Checklist (Language Platform Ready)

This checklist describes the bar for **Stable**. For the v3 language stability
track, `SPEC.md`, `docs/V3_STABILITY_PLAN.md`, and `tests/language` define the
release contract.

## Language core
- [x] Grammar and block rules documented (indentation rules are explicit)
- [x] Syntax reference complete for v1.3.x core + runnable examples
- [x] Top-level `SPEC.md` entry point
- [x] Machine-readable spec manifests under `spec/`
- [x] v3 stability plan and tests/language gate
- [x] No crashes on invalid input (all errors are `MellowLangRuntimeError`)
- [x] Deterministic mode documented (seed + replay)

## Error UX (must)
- [x] SYNTAX errors include accurate `line:col` + code-frame + caret
- [x] RUNTIME errors include accurate `line:col` + code-frame + caret
- [ ] Call stack shows user frames first (file + line + function)
- [x] `mellow check` output matches `mellow run` formatting

## Tooling
- [ ] VS Code extension: syntax highlight + diagnostics + LSP basics
- [x] Formatter (`mellow fmt`) is idempotent (running twice gives same output)
- [x] Linter (`mellow check`) returns non-zero on issues

## Sandbox + permissions (game/mod safe)
- [x] Default sandbox: no network, no arbitrary filesystem
- [x] Explicit permissions/flags for: ask/input, wait/sleep, storage/files
- [x] Path traversal protection (no `..`, no absolute escapes)

## Storage & files
- [x] System base dir: `mellow_saves/`
- [x] No auto-creation of user subfolders
- [x] Atomic writes on save
- [x] Clear file modes: r/w/a + rb/wb/ab
- [x] Secure Save standard (`*.msav`): encrypted + tamper-evident (v1.3.4)

## Performance (game loop ready)
- [x] Step budget / time budget options
- [ ] Profiler or timing hooks for scripts
- [ ] Stress test: 10k loop iterations without slowdown surprises

## Quality gates (required)
- [x] Tests: parser + runtime + error formatting (>= 30 cases recommended)
- [x] `tests/core` release gate
- [x] `tests/language` spec-contract gate
- [ ] CI: tests run on push/PR (GitHub Actions)
- [ ] Releases: portable ZIP + VSIX (optional installer)

## Demos (make it real)
- [ ] Game demo: deterministic replay for gameplay logic
- [ ] AI demo: behavior/state machine or utility AI example
