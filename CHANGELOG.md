# Changelog

## 2.5.0 - 2026-06-13

### Production Scripting Core
- Add Decimal-backed `std.money` helpers for exact money-style rules.
- Add top-level money aliases such as `money(...)`, `money_add(...)`, and `money_format(...)`.
- Add `--sandbox=finance` for stricter rule-script execution: no ask/wait/storage/save/network and Python VM routing until native sandbox parity is complete.
- Teach the IR compiler path to lower money stdlib calls without treating them as user skills.
- Add core tests for money precision and finance sandbox enforcement.

### Deferred
- Native C VM parity for `std.money`.
- A full language-level `decimal` literal/type syntax.
- Audit-log and immutable ledger primitives.

## 2.4.0 - 2026-06-13

### Native Core Parity
- Add `tests/native` as the strict Python VM vs native C VM parity gate for the stable language core.
- Fix the Python-to-C VM bridge so current native extensions can run without accidental `host=` keyword failures.
- Add native C support for compiled `range(...)` calls used by stable `for` loops.
- Report native parity as `stable-core` while keeping debugger, event, and record/replay fallback status explicit.
- Build the native extension in CI before running native parity tests.

### Stable
- Bump package and runtime version to `2.4.0`.
- Keep `frameworks.mellow_ui` in the release verification set.

### Deferred
- Native debugger pause/inspect parity.
- Native event handler execution parity.
- Native record/replay parity.

## 2.3.5 - 2026-06-13

### Release Polish
- Treat `tests/core` as the stable release gate.
- Limit GitHub Actions to stable core tests while legacy and experimental suites are being triaged.
- Add stable-core documentation and a release checklist.
- Add a Windows native build helper script for the optional C extension.
- Make `frameworks.mellow_ui` installable and runnable as a Python framework package.
- Add JSON rendering support for Mellow UI framework previews/tools.

### Deferred
- Full legacy and experimental test suite cleanup.
- Broader native VM parity beyond core execution.
- Packaging binary artifacts for release downloads.

## 2.3.4 - 2026-06-04

### Stable
- Added `tests/core` as the stable language gate.
- Improved `mellow doctor` output and optional feature reporting.
- Split optional dependencies out of the default install.
- Fixed core language regressions around functions, `range(...)`, and indexed values.
- Fixed Windows native VM build issues in source.

### Experimental
- Native VM can run core examples through `--engine=c`, but the Python VM remains needed for record/replay, event handlers, and debugger parity.
- Agent, MMG, desktop, registry, and full legacy test surfaces are not release gates yet.
