# Mellow v2.1.3 — Standalone Runtime Parity Pack

This release pushes the standalone Mellow VM closer to runtime parity with the main runtime.

## Highlights

- Introduces a real binary standalone image format: **MLVI v2**
- Adds function, event, and module metadata tables to standalone images
- Carries a core-module loading hint into native runtime images
- Expands the native syscall surface with:
  - `print`
  - `len`
  - `clock_ms`
  - `getenv`
  - `str`
  - `type`
- Makes standalone `.mvi` execution fully native in the C runtime once the image has been compiled

## Notes

- `IMPORT` is now recognized by the standalone runtime as module metadata parity and currently behaves as a no-op at execution time.
- Module/core loading in this release is metadata-driven. It is not yet a full package/module loader with dependency resolution.
- Event table parity is present in the image format for future runtime dispatch work.

## Commands

```bash
mellow standalone build
mellow standalone compile examples/hello.mellow -o examples/hello.mvi
mellow standalone run examples/hello.mvi
```
