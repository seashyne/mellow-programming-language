# Release Notes v2.9.4

Date: 2026-06-21

## Summary

2.9.4 is a runtime-structure and portability patch. It reduces oversized Python
entrypoints, makes subsystem ownership explicit, and introduces a verifiable
ARM64 path for the standalone C runtime.

## Runtime Structure

- CLI command families now live under `src/mellowlang/cli/commands/`.
- Package services now live under `src/mellowlang/packages/`.
- Python VM debugger and storage behavior now live in focused mixins.
- Architecture tests prevent entrypoints from growing back into monoliths.

## ARM64 Runtime

- The standalone runtime exposes `--runtime-info`.
- CMake detects ARM64 and supports MSVC without assuming a separate `libm`.
- CI cross-compiles and executes ARM64 under QEMU against the core fixture.
- ARM64 currently uses `generic-c`; no optimized NEON kernel is claimed.

## Release Gate

```powershell
.\scripts\test-v294-stability.ps1
```

Production ARM performance still requires benchmarks on physical ARM hardware.
