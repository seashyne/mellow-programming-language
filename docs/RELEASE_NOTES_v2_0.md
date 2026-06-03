# Mellow v2.0 VM Unification Pack

## Added
- Unified debugger hook contract across VM entrypoints.
- Conditional breakpoints (`debug_break_when`).
- Watch expressions (`debug_watch_exprs`).
- Typed stack/local/global snapshots in debugger payloads.
- Richer source-span metadata (`end_line_map`, `end_col_map`, `span_map`).

## Notes
- Native C execution still prioritizes fast-path execution. When full paused-debug inspection is requested, the runtime routes through the Python inspector facade so both engines expose the same debugger API shape.
- Source-span mapping in this release is instruction-oriented and heuristic for legacy bytecode.
