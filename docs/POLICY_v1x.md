# v1.x Compatibility Policy (Lock Policy)

MellowLang follows **SemVer**.

## What is locked in v1.x (no breaking changes)
- **CLI surface**: existing commands and flags keep working (we only add new ones).
- **Core contracts**
  - `Compiler.compile(source, *, filename=None) -> CompiledProgram`
  - `MellowVM.run(program, *, config=RunConfig(...)) -> Any`
- **Error UX contract**
  - All user-facing errors are `MellowLangRuntimeError`
  - Includes: `error_type`, `filename`, `line_num`, `col`
  - CLI prints: header + code-frame + caret
- **Storage/file APIs**
  - `mkdir`, `save_data`, `load_data`, `file_read`, `file_write`, `file_append`, `file_exists`, `file_delete`

## What may change in v1.x (non-breaking improvements)
- Performance and VM internals
- New syntax sugar (aliases) that compiles to the same core semantics
- New stdlib modules and helper functions
- Better diagnostics (more precise columns, richer messages)

## Deprecation
- If we ever deprecate something in v1.x, it will:
  1. Keep working
  2. Emit a warning (when possible)
  3. Be removed only in v2.0

## Versioning rules
- Patch (1.0.x): bug fixes, docs, tests, non-breaking improvements
- Minor (1.x.0): new features, new CLI commands/flags, new stdlib modules (still non-breaking)
- Major (2.0.0): allowed breaking changes
