# Heap index follow-up — 2026-11-05 (Mellow 2.9.9, full native C)

The 2026-11-02 report (`RESULTS_2026-11-02_CROSS-LANGUAGE-HONEST.md`) measured
`money_add` at 1,770 ms for 3,000 calls and 17,130 ms for 9,000 calls and named
the cause: `heap_find()` walked the global `g_heap_blocks` list, and every
`mvalue_free` calls it, so the free path was O(blocks allocated so far).
Commit `13b67178` replaced that walk with a pointer-keyed bucket index
(`native/standalone/src/mellowrt_heap.inc`). This note records the re-measurement.

Host: Windows 11 26200, Intel64 Family 6 Model 191, Python 3.14.3. Binary:
`build/standalone-release/Release/mellow.exe`, Release build of `13b67178`.

## Re-measurement

Probe shape (one `money_add` per iteration, line-oriented source):

```mellow
let step = money("0.01", "THB")
let total = money("0.00", "THB")
var i = 0
while i < N:
    total = money_add(total, step)
    i = i + 1
print(i)
```

Medians of 5 whole-process runs each, `mellow run <file>`:

| Ops | Before (2026-11-02) | After (2026-11-05) | Speedup | After, µs/op incl. startup |
| ---: | ---: | ---: | ---: | ---: |
| 3,000 | 1,770 ms | 21.3 ms | ~83x | 7.1 |
| 9,000 | 17,130 ms | 57.8 ms | ~296x | 6.4 |

At 300 calls the whole process is now startup-bound (9.6 ms for the probe above,
against a 6.4 ms no-work floor), so only the 3,000 and 9,000 rows are
throughput comparisons. Between 3,000 and 9,000 calls (3x ops) the time grows
2.7x, so the free path no longer scales with the heap; the remaining ~6 µs per
call is the operation itself plus the growing GC list.

## What did not change

`money_add` still allocates 16 heap blocks per call and the standalone runtime
still does not collect automatically. `gc_stats()` unchanged from the earlier
report:

| Ops | heap_blocks | heap_freed | collections |
| ---: | ---: | ---: | ---: |
| 200 | 3,204 | 0 | 0 |
| 800 | 12,804 | 0 | 0 |

So automatic collection remains an open item. The index removes the quadratic
*free* cost; it does not reclaim blocks. A long-running money/ledger workload
still needs an explicit `gc_collect()` or an allocation-triggered collection
policy, and the sweep itself is still O(blocks) because it walks the list.

## Takeaways for the published numbers

- The business-arithmetic lane is no longer blocked by the heap registry: 9,000
  `money_add` calls drop from 17.1 s to 58 ms.
- `ledger_post` at 80 posts drops from 15,128 ms to 29.9 ms. The rest of its
  curve is the per-post clone of the whole book, which is the immutable-data
  contract, not a runtime defect.
- The general interpreter speed claim from the 2026-11-02 report (about 2x
  CPython, about 4.7x slower than Lua) is unaffected: this change only removes
  heap bookkeeping from value release.

## Reproducing

The probe scripts are scratch (`.tmp-bench/`), not tracked; the loop shape is
the block above. `python benchmarks/native_data_transform_benchmark.py --rows
1000 --rounds 250 --repeats 7` remains the tracked benchmark for the data lane.
