<p align="center">
  <img src="assets/mellow-logo.png" alt="Mellow logo" width="72">
</p>

# Mellow Runtime

Mellow Runtime is the experimental C embedding layer for running Mellow from a
host application. The standalone C runtime remains the main supported execution
path right now; this ABI is being introduced early so it can evolve in-tree
before it is declared stable.

The initial ABI lives in:

- `native/standalone/include/mellow_runtime.h`
- `native/standalone/src/mellow_runtime.c`

## Current provisional API surface

- `mellow_runtime_new`
- `mellow_runtime_free`
- `mellow_runtime_set_argv`
- `mellow_runtime_compile_source`
- `mellow_runtime_compile_file`
- `mellow_runtime_run_program`
- `mellow_runtime_program_free`
- `mellow_runtime_gc_collect`
- `mellow_runtime_gc_stats`

## Direction

This ABI is the future boundary between host applications and the Mellow VM. For
now it is a trial layer over the existing standalone compiler, VM, syscalls, and
GC. The CLI and release path should continue to prioritize the direct C runtime
until this ABI is hardened.

Next runtime milestones:

- module registry ABI for native modules;
- import/package loading in C;
- stable error/result object ownership;
- performance-specialized numeric opcodes and loop dispatch;
- scheduler API for green threads and channels.
