# Release Notes — v1.3.3 (Checklist/QA)

Focus: **Stabilization + quality gates** (docs cleanup, test coverage, small config fix).

## What changed

### ✅ Docs (source of truth)
- Updated `docs/SYNTAX_REFERENCE.md` to v1.3.3 (indentation rules, call-as-statement, named args, determinism flags)
- Added `docs/STDLIB_REFERENCE.md` (practical list of built-ins + CLI commands)

### ✅ Fixes
- Removed duplicate `RunConfig.fs_read_allow/fs_write_allow` fields (no behavior change; just correctness/clarity)

### ✅ Quality gates
- Test suite expanded to **30 passing tests** (formatter idempotency, CLI exit codes, sandbox traversal, error codeframe, step budget)

## Compatibility
- v1.x policy preserved: **no breaking syntax changes**.
