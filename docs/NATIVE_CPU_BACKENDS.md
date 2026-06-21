# Native CPU Backends

Mellow native runtime targets portable performance first, then architecture tuned
paths for hot loops.

## Backend Contract

Every native build must keep `generic-c` available. Architecture backends are
selected as preferred paths only when the CPU family is known:

- `x86_64` / `AMD64` -> `x86_64-simd`
- `arm64` / `aarch64` -> `arm64-neon`
- unknown targets -> `generic-c`

The CLI exposes this through:

```text
mellow native status
mellow native status --json
```

## ARM64 Goal

ARM64 is a first-class target. The runtime reports `arm64-neon` as the preferred
backend on ARM64 machines and always keeps `generic-c` as the fallback path.

Future hot host APIs should use this model:

1. portable scalar implementation in C;
2. optional ARM64 NEON kernel for tight numeric/data loops;
3. runtime status reports which backend is selected;
4. benchmark gates compare generic and architecture-specific paths when both are
   available.

## Build Metadata

`setup.py` defines architecture macros for native extensions:

- `MELLOW_BACKEND_GENERIC_C`
- `MELLOW_ARCH_X86_64` and `MELLOW_BACKEND_X86_64_SIMD`
- `MELLOW_ARCH_ARM64` and `MELLOW_BACKEND_ARM64_NEON`
- `MELLOW_ARCH_ARM32` or `MELLOW_ARCH_UNKNOWN`

These macros are capability markers. Code must still fall back to `generic-c`
unless a tuned kernel is present and tested.
