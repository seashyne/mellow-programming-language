# Cross-language benchmark — 2026-11-02 (Mellow 2.9.8, full native C)

Raw data: `RESULTS_2026-11-02-2.9.8-15reps.json` (suite harness, 15 repeats;
local run output, not committed) plus the floor/scaling probes described below. Host: Windows 11 26200, Python 3.14.3,
Zig 0.16.0 (`tools/zig`), gcc 13.2.0 MinGW (`-O3`), Lua 5.4.6, Node 24.14.0.
Mellow binary: `build/standalone-release/Release/mellow.exe`, MSVC `/O2 /Ob2 /DNDEBUG`,
`--runtime-info` reports `backend=generic-c, optimized_kernels=false`.

## TL;DR (สรุป)

1. ตัวเลข ~8 ms ที่เคยโชว์ใน standard report ว่า "สูสี C/Zig" มาจาก **pattern matching
   เฉพาะ loop 5 shape** ใน `native/standalone/src/mellowc.c` (`emit_fast_i64_sum_loop`,
   `emit_fast_i64_branch_mod2_loop`, `emit_fast_i64_list_mod_loop`, ...) — เปลี่ยน
   `i % 2` เป็น `i % m` ตัวเดียว ผลร่วงจาก 0.14 ns/iter เป็น 47.5 ns/iter (~350 เท่า)
2. ในทางกลับกันฝั่ง C/Zig ถูก optimizer ลบ loop ทิ้ง (closed form) เลยวัดได้ ~0 —
   ตารางเดิมจึงเปรียบเทียบ "startup" กันเอง ไม่ใช่ speed ของภาษา
3. เมื่อใช้ workload ที่ optimizer แกล้งไม่ได้ (serialized modulo chain):
   Mellow 45.9 ns/iter = เร็วกว่า CPython 2.07 เท่า แต่ช้ากว่า Lua 4.7 เท่า
   ช้ากว่า gcc -O3 11.4 เท่า — Mellow อยู่ระดับ "VM กลางๆ" ไม่ใช่ systems speed
4. จุดที่แย่ที่สุดไม่เกี่ยวกับ loop ทั่วไป แต่คือ **builtin call ใน standalone**:
   `money_add` = 553 µs/op และโตแบบ quadratic (3000 calls 1.77 s, 9000 calls 16.7 s)
   สาเหตุ: heap registry เป็น linked list ที่ `heap_find()` ไล่ linear ทุกครั้ง
   และ GC ไม่เคยทำงาน (`collections: 0, heap_freed: 0` แม้ money 16 blocks/op)
5. จุดที่ Mellow ชนะจริงคือ startup: 6.23 ms เทียบกับ Node 43.75 ms และ Python 55.65 ms

## Startup floor (median of 15 runs, program that does no work)

| Runtime | Floor ms |
| --- | ---: |
| Zig (ReleaseFast exe) | 4.86 |
| C (gcc -O3 exe) | 5.39 |
| Mellow standalone exe | 6.23 |
| Lua 5.4.6 | 6.44 |
| Node 24 | 43.75 |
| Python 3.14.3 | 55.65 |

Everything below ~50 ms on Windows is process-spawn noise, which is why the
suite's whole-process timing cannot separate Mellow from C at small workloads.

## Suite workloads (whole-process median, 15 repeats)

| Workload | iters | Mellow | C | Zig | Python | Lua |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| sum_loop | 2,000,000 | 6.33 | 5.48 | 5.66 | 220.96 | 16.43 |
| function_calls | 200,000 | 5.56 | 5.24 | 4.16 | 73.95 | 10.24 |
| list_index | 500,000 | 6.93 | 6.01 | 5.05 | 105.57 | 14.26 |
| branch_mod | 500,000 | 5.99 | 5.30 | 4.37 | 101.51 | 12.94 |
| string_concat | 2,000 | 5.81 | 5.06 | 5.85 | 55.16 | 8.27 |

Subtracting each runtime's floor leaves at most ~1 ms of visible work in every
row. Zig's maxima (17–27 ms against 4–6 ms medians) show first-run/disk-cache
noise, so these rows are a startup comparison, not a throughput comparison.

## Shape cliff: the recognized fast loops

Measured on the standalone binary, same `sum_loop` body modulo one token:

| Program shape | n | median ms | ns/iter |
| --- | ---: | ---: | ---: |
| `total = total + i` (matches `emit_fast_i64_sum_loop`) | 100,000,000 | 19.9 | 0.14 |
| `total = total + (i % m)` where `let m = 3` (no recognizer) | 100,000,000 | 4,753 | 47.5 |

`branch_mod` in the suite uses the literal `i % 2`, which is exactly what
`emit_fast_i64_branch_mod2_loop` matches. Five workloads, five bespoke
recognizers — the published cross-language table is a fast-path demo, and it is
worthless as a general throughput claim.

## Honest throughput: serialized chain

`total = (total + i) % 1000000007` keeps a loop-carried dependency, so neither
gcc nor Zig can closed-form it, and all six runtimes were verified to print the
same value at every size (2M / 20M / 100M).

| Runtime | 2M ms | 20M ms | 100M ms | ns/iter (20M→100M slope) |
| --- | ---: | ---: | ---: | ---: |
| C (gcc -O3) | 10.1 | 61.2 | 285.7 | 2.81 |
| Node 24 | 48.2 | 124.8 | 416.9 | 3.65 |
| Zig 0.16 ReleaseFast | 12.3 | 82.0 | 403.1 | 4.01 |
| Lua 5.4.6 | 25.4 | 202.8 | 982.6 | 9.75 |
| **Mellow 2.9.8 native** | 100.8 | 891.6 | 4,567.0 | **45.94** |
| Python 3.14.3 | 255.7 | 1,978.3 | 9,586.1 | 95.10 |

Mellow sits between Lua and CPython on general interpreter work: about 2x
CPython, about 4.7x slower than Lua, about 11x slower than compiled C. The
comparisons use the same source algorithm; C/Zig are additionally advantaged
because their modulus is a compile-time constant that strength-reduces to a
multiply, which an interpreter cannot do.

## Business-arithmetic lane (the part no cross-language table covers)

Standalone binary, same shape as the suite's `money_add`, line-oriented source:

| Ops | median ms | µs per `money_add` |
| ---: | ---: | ---: |
| 300 | 0.07 (incl. 6 ms floor) | ~0.02 amortised, not linear |
| 3,000 | 1,770 | 553 |
| 9,000 | 17,130 | 1,714 |

Time grows ~quadratically in call count, and it is not accumulation: replacing
`total = money_add(total, step)` with `total = money_add(step, step)` gives the
same curve. `gc_stats()` after 200 ops reports `heap_blocks: 3204, heap_freed: 0,
collections: 0`; after 800 ops `heap_blocks: 12804, heap_freed: 0, collections: 0`
— 16 leaked heap blocks per money operation and no automatic collection ever.

Root cause: `native/standalone/src/mellowrt_core.c:26-34` keeps every allocation
in a singly linked `g_heap_blocks` list and `heap_find()` walks it linearly; that
walk is on the free path (`mvalue_free`, lines 176-190). Cost per syscall is
therefore O(blocks allocated so far).

Python reference doing the equivalent exact-decimal work: 56 ns per `Decimal`
add. This is also the most likely explanation for `ledger_post` showing 0.66x
(native slower than the Python VM) in `benchmarks/reports/standard/`.

> **Addendum 2026-11-05:** commit `13b67178` replaced the linear `heap_find`
> walk with a pointer-keyed bucket index. On the same probe, 3,000 calls drop
> from 1,770 ms to 21.3 ms and 9,000 calls from 17,130 ms to 57.8 ms. Block
> growth (16 per call) and the absence of automatic collection are unchanged.
> See `RESULTS_2026-11-05_HEAP-INDEX.md`.

## What this means for the positioning decision

* "Fast language" is not currently a defensible claim outside five special-cased
  micro-shapes; general Mellow throughput is ~2x CPython.
* "Instant to run" is defensible: 6.23 ms floor vs 43.75 ms Node and 55.65 ms
  Python, and no interpreter process in the loop.
* The data/business lane is blocked by one fixable runtime defect (heap registry
  linear scan + never-triggering GC), not by language design. Fixing it is the
  difference between 553 µs and microseconds per builtin call.

## Reproducing

```
python benchmarks/native_vs_zig/run_compare.py --mellow-binary build/standalone-release/Release/mellow.exe --zig tools/zig/zig-x86_64-windows-0.16.0/zig.exe --lua "D:/Program/ZeroBraneStudioEduPack-2.01-win32/bin/lua54.exe" --repeats 15 --json-out benchmarks/native_vs_zig/RESULTS_2026-11-02-2.9.8-15reps.json
```

The floor, serialized-chain and money probes used for this report are
scratch tools (`.tmp/bench/`), not part of the tracked suite: they need to run
the same loop shapes against per-runtime floors, which `run_compare.py` does not
do. Fold them into the suite only if these numbers become something the project
publishes.
