# Mellow v2.0.3 Native VM Runtime Parity Pack

## Highlights

- Native-first execution metadata via `run_bytecode_ex()`
- Explicit `native_allow_fallback` and `native_require` runtime controls
- VM facade now reports whether a run used the C engine or a Python fallback
- C extension source now exports `capabilities()` when rebuilt
- Native VM status reports recommended run mode and remaining Python-only gaps

## Honest status

This release moves the execution path contract closer to a native-only Mellow VM, but it does not eliminate the Python VM in every scenario yet. In v2.0.3, Python is still required for:

- record/replay parity
- event-handler execution parity
- paused debugger parity

For normal bytecode execution, the native bridge now supports a strict mode so callers can fail fast instead of silently falling back.
