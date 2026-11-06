# Native Mellow multi-workload benchmark - 2026-06-28

Raw result: `RESULTS_2026-06-28-multiworkload-after-fastlist.json`

## Environment

- Mellow: `Mellow Programming Language 2.9.7 (Full Native C)`
- Zig: `0.16.0`
- C: `gcc` from Strawberry Perl toolchain, `-O3`
- Python: `Python 3.14.3`
- Lua: `Lua 5.1.5`
- Method: 10 full process runs per workload after a warmup run.

## Median Results

| Workload | Mellow ms | Zig ms | C ms | Python ms | Lua ms | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `sum_loop` | 7.91 | 5.46 | 6.25 | 266.85 | 8.84 | Mellow loop super-opcode path |
| `function_calls` | 21.54 | 5.81 | 6.19 | 78.45 | 8.30 | Fixed native locals corruption crash |
| `list_index` | 8.36 | 6.42 | 7.11 | 109.81 | 12.03 | New list/modulo super-opcode path |
| `branch_mod` | 6.88 | 5.91 | 6.67 | 111.60 | 8.67 | Branch/modulo super-opcode path |
| `string_concat` | 11.05 | 6.07 | 6.97 | 60.03 | 10.37 | Faster than Python, near Lua |

## Takeaways

Mellow is now competitive on exact numeric loop patterns and the list/modulo
benchmark path. In this latest run, `list_index` improved from **161.48 ms** to
**8.36 ms**, making it faster than Python and Lua on the same workload.

The broader suite shows the next real optimization targets:

1. Function calls are stable now, but still about **3.7x** slower than Zig and
   slower than Lua on this workload.
2. String concat remains faster than Python but is not yet competitive with
   Zig/C/Lua.
3. Generic list/index/modulo dispatch is still worth improving for patterns
   outside the exact `values[i % len]` super-opcode.
4. Numeric loop super-opcodes are now close to C/Zig process-level wall-clock
   timings, but broader language features still need generic VM improvements.

## Verification

```text
python -B benchmarks\native_vs_zig\run_compare.py --help
python benchmarks\native_vs_zig\run_compare.py --zig tools\zig\zig-x86_64-windows-0.16.0\zig.exe --repeats 10 --json-out benchmarks\native_vs_zig\RESULTS_2026-06-28-multiworkload-after-fastlist.json --keep-zig-binary
python -m pytest -p no:cacheprovider tests\native\test_full_native_c_cli.py
```
