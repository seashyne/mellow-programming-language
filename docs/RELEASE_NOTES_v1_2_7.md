# MellowLang v1.2.7 (Hybrid C VM)

This release focuses on **C VM parity + error UX**.

## ✅ C VM improvements
- **TRY/CATCH parity**: runtime errors raised inside a `TRY` block are now caught and control jumps to the `catch_pc` stored in the TRY frame (matching the legacy Python VM behavior).
- **PC error markers**: C VM errors now raise a structured exception (`mellowlang._mellowvm.CVMError`) that carries:
  - `pc`  (program counter)
  - `kind` (RUNTIME/SANDBOX/ERROR)
  - `msg` (message)
  This allows Python to map the error to **filename:line:col** and print a **code frame**.

## ✅ Python-side UX
- When the C VM raises `CVMError`, the VM facade maps it to `MellowLangRuntimeError` using `program.line_map/col_map`.
- `--engine=auto` remains the recommended mode: it prefers C, but falls back to Python for unsupported opcodes.

## Notes
- Unsupported opcode handling is preserved (`CVM_UNSUPPORTED_OPCODE:<op>`), so the auto-fallback behavior is unchanged.
