# Native C Debug Hook Parity

Mellow v2.0.1 introduces a conservative capability contract for the native C VM.

## Goals
- make parity status explicit instead of implicit
- keep debugger payloads stable across engines
- prepare future native pause/resume and conditional breakpoint hooks

## Current behavior
- normal execution can use the C VM
- debugger-heavy flows still route through the Python debugger runtime when native parity is unavailable
- the facade exposes `last_engine`, `last_engine_detail`, and `last_debug_capabilities`

## Rebuild note
The source for `_mellowvm.capabilities()` is included, but existing prebuilt binaries may not contain it until rebuilt.
