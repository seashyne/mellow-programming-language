# Native Mellow comparison benchmark

This benchmark compares the current Full Native C build with Zig ReleaseFast, C,
Rust, Python, and Lua across several small workloads:

- `sum_loop`: integer while-loop sum.
- `function_calls`: small function call inside a loop.
- `list_index`: list/array indexing plus modulo.
- `branch_mod`: branch plus modulo.
- `string_concat`: repeated string append and length.

Run:

```powershell
python benchmarks/native_vs_zig/run_compare.py --repeats 10
```

If tools are not in PATH, pass explicit executable paths:

```powershell
python benchmarks/native_vs_zig/run_compare.py --zig C:\path\to\zig.exe --repeats 10
python benchmarks/native_vs_zig/run_compare.py --python C:\path\to\python.exe --lua C:\path\to\lua.exe --repeats 10
python benchmarks/native_vs_zig/run_compare.py --rust C:\path\to\rustc.exe --repeats 10
```

The runner measures full process wall-clock time. For Mellow this includes
source parse/compile/runtime startup. For Zig, C, and Rust it measures
already-compiled executables after a warmup run. For Python and Lua it measures
interpreter startup plus script execution.

Results are emitted as JSON with one section per workload and a `summary`
object containing median timings and ratios.

## Published results

Each file is a dated measurement on the host named inside it, not a standing
claim about the language. Re-run the command above before quoting numbers.

- `RESULTS_2026-11-02_CROSS-LANGUAGE-HONEST.md` - whole-process timings, startup
  floor, fast-loop shape cliff, serialized-chain throughput, and the
  business-arithmetic probe. It found the heap-registry quadratic.
- `RESULTS_2026-11-05_HEAP-INDEX.md` - re-measurement after the heap index
  (`13b67178`): 9,000 `money_add` calls 17,130 ms -> 57.8 ms, with block growth
  and the missing automatic collection unchanged.
- `RESULTS_2026-11-06_RUST.md` - adds Rust to the harness; whole-process
  medians put Rust in the same startup band as C, Zig, and Mellow, with the
  workload deltas inside spawn noise.
