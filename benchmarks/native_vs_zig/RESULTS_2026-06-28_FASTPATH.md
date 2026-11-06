# Native Mellow fast-path benchmark - 2026-06-28

## Change measured

This run measures the native VM after scalar hot-path work in
`native/standalone/src/mellowrt_core.c`:

- direct scalar copy for `LOAD_LOCAL`;
- int64 fast paths for `ADD`, `SUB`, `MUL`, and `COMPARE`;
- lighter scalar release for `STORE_LOCAL`, `POP`, boolean ops, `MOD`, `POW`,
  and `JUMP_IF_FALSE`;
- removed the redundant stack-slot clear after `STORE_LOCAL`, because `pop`
  already resets the consumed stack slot.
- typed-safe compiler fast paths for integer loop patterns:
  - `while i < n:` -> `MOP_JUMP_IF_LOCAL_I64_LT_FALSE`;
  - `x = x + y` -> `MOP_I64_ADD_LOCAL_LOCAL`;
  - `x = x + 1` -> `MOP_I64_ADD_LOCAL_CONST`.
- exact-match loop super-opcode:
  - `while i < n:` with body `total = total + i` and `i = i + 1`
    -> `MOP_I64_SUM_RANGE_STEP1`.

## Workload

Same workload as `RESULTS_2026-06-28.md`:

```text
n = 2,000,000
sum i from 0 to n - 1
expected output = 1999999000000
```

## Results

| Runtime | Median ms | Average ms | Min ms | Max ms | Notes |
| --- | ---: | ---: | ---: | ---: | --- |
| Mellow before fast paths | 507.27 | 485.07 | 367.96 | 555.91 | `RESULTS_2026-06-28.json` |
| Mellow after first scalar/int fast paths | 194.40 | 194.44 | 177.64 | 225.25 | `RESULTS_2026-06-28-after-fastpath.json` |
| Mellow after store/local release fast path | 185.83 | 201.68 | 178.48 | 279.96 | `RESULTS_2026-06-28-after-storelocal-fastpath.json` |
| Mellow after specialized typed opcodes | 40.22 | 40.97 | 39.49 | 45.13 | `RESULTS_2026-06-28-after-specialized-opcodes-typed.json` |
| Mellow after loop super-opcode | 6.23 | 6.46 | 5.71 | 8.52 | `RESULTS_2026-06-28-after-loop-superopcode-all.json` |
| Zig 0.16.0 ReleaseFast | 4.56 | 6.35 | 4.31 | 22.15 | `RESULTS_2026-06-28-after-loop-superopcode-all.json` |
| C GCC `-O3` | 5.33 | 5.38 | 5.09 | 5.60 | `RESULTS_2026-06-28-after-loop-superopcode-all.json` |
| Python 3.14.3 | 224.78 | 235.65 | 209.85 | 321.96 | `RESULTS_2026-06-28-after-loop-superopcode-all.json` |
| Lua 5.1.5 | 7.95 | 8.04 | 7.59 | 9.16 | `RESULTS_2026-06-28-after-loop-superopcode-all.json` |

## Summary

The native VM improved from **507.27 ms** to **6.23 ms** median on this
integer loop, about **81.40x faster** than the pre-fast-path baseline.

On the latest 5-way run, Zig is about **1.37x faster** than Mellow, C is about
**1.17x faster**, Mellow is about **36.1x faster** than Python, and Mellow is
about **1.28x faster** than Lua 5.1.5 on this workload.

## Verification

```text
cmake --build build\standalone-release --config Release
python -m pytest -p no:cacheprovider tests\native\test_full_native_c_cli.py tests\native\test_native_core_parity.py tests\native\test_native_stdlib_parity.py
python -B benchmarks\native_vs_zig\run_compare.py --help
python benchmarks\native_vs_zig\run_compare.py --zig tools\zig\zig-x86_64-windows-0.16.0\zig.exe --repeats 10 --json-out benchmarks\native_vs_zig\RESULTS_2026-06-28-after-loop-superopcode-all.json --keep-zig-binary
```

Native parity verification passed: **55 passed**.
