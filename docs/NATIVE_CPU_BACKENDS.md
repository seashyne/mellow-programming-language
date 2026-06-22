# Native CPU Backends

Mellow native runtime targets portable performance first, then architecture tuned
paths for hot loops.

## Backend Contract

Every native build uses `generic-c`. Architecture detection reports available
CPU features, but does not claim an optimized backend until tuned kernels exist:

- `x86_64` / `AMD64` -> `generic-c`, SSE2 capability reported
- `arm64` / `aarch64` -> `generic-c`, NEON capability reported
- unknown targets -> `generic-c`

The CLI exposes this through:

```text
mellow native status
mellow native status --json
```

## ARM64 Goal

ARM64 is a first-class portable target. The standalone runtime cross-builds for
ARM64 and is executed under QEMU in CI. It reports `generic-c` as the backend,
with `arm_neon_available=true` on ARM64. This is intentionally not called
`arm64-neon` because no VM kernel currently uses NEON intrinsics.

Future hot host APIs should use this model:

1. portable scalar implementation in C;
2. optional ARM64 NEON kernel for tight numeric/data loops;
3. runtime status reports which backend is selected;
4. benchmark gates compare generic and architecture-specific paths when both are
   available.

## Build Metadata

`setup.py` defines architecture macros for native extensions:

- `MELLOW_BACKEND_GENERIC_C`
- `MELLOW_ARCH_X86_64`
- `MELLOW_ARCH_ARM64`
- `MELLOW_ARCH_ARM32` or `MELLOW_ARCH_UNKNOWN`

Backend macros must only be added with a tuned kernel, ARM hardware benchmarks,
and a release gate that compares it with `generic-c`.

## ARM64 Verification

The `native-arm64` GitHub Actions job cross-compiles with
`aarch64-linux-gnu-gcc`, runs the ARM64 executable through QEMU, checks runtime
metadata, and executes the frozen native core fixture. This proves ARM64 build
and functional portability. Performance still requires benchmark results from
real ARM hardware such as Apple Silicon, Raspberry Pi 5, or AWS Graviton.
