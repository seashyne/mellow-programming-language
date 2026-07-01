# Native Mellow comparison benchmark

This benchmark compares Mellow 2.9.7 Full Native C with Zig ReleaseFast, C,
Python, and Lua across several small workloads:

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
```

The runner measures full process wall-clock time. For Mellow this includes
source parse/compile/runtime startup. For Zig and C it measures already-compiled
executables after a warmup run. For Python and Lua it measures interpreter
startup plus script execution.

Results are emitted as JSON with one section per workload and a `summary`
object containing median timings and ratios.
