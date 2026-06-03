# Mellow v2.1.2 — Standalone Mellow VM Pack

This release makes the standalone runtime actually useful as a native Mellow VM by adding a standalone image pipeline.

## Added

- `src/mellowlang/standalone_image.py`
- `mellow standalone compile <file.mellow> -o <file.mvi>`
- `mellow standalone run <file.mvi>`
- native standalone image loader in `native/standalone/src/mellowrt_main.c`
- string concat support in standalone `ADD`
- auto-rebuild cleanup for stale CMake caches in standalone builds

## What works now

- compile supported `.mellow` programs into `.mvi` standalone images
- load `.mvi` images from the native standalone binary
- execute top-level globals via slot lowering
- native print syscall for standalone runs
- run the bundled `examples/hello.mellow` without the Python VM in the execution path

## Current limits

- standalone image lowering is still a subset bridge from compiler bytecode
- unsupported bytecode will fail fast during standalone image compile
- standalone VM still focuses on core execution, not full hosted workflow/runtime parity
