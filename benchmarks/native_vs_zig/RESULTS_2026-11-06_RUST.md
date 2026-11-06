# Cross-language benchmark with Rust — 2026-11-06 (Mellow 2.9.10)

Raw data: `RESULTS_2026-11-06-rust-15reps.json` (15 repeats per runtime, whole
process wall clock). Host: Windows 11 26200, MSVC Release `mellow.exe`
(`backend=generic-c`, `optimized_kernels=false`), gcc 13.2.0, rustc 1.99.1
(2026-10-13), Zig 0.16.0, Python 3.14.3, Lua 5.1.5 (the Lua on PATH is the
ZeroBrane 5.1 build, so its rows are not comparable with the Lua 5.4.6 rows in
`RESULTS_2026-11-02_CROSS-LANGUAGE-HONEST.md`).

Rust was added to the comparison harness as a fifth target (`*.rs` compiled with
`rustc --edition 2021 -O`).

## TL;DR (สรุป)

1. Rust อยู่ในกลุ่มเดียวกับ C และ Zig: เวลารวมต่อโปรเซสเกือบทั้งหมดคือ startup
   ไม่ใช่ตัวงาน — ส่วนต่างระหว่าง Rust กับ Mellow อยู่ที่หลัก 0.1–0.6 ms
   ซึ่งอยู่ในช่วง noise ของ Windows process spawn
2. บน workload ชุดนี้ (2M loop ลงมา) Mellow ไม่ได้ช้ากว่า Rust อย่างมีนัยสำคัญ:
   ratio อยู่ที่ 0.94–1.06 เท่า บางแถว Mellow เร็วกว่าเล็กน้อยเพราะ noise
3. ช่องว่างจริงยังอยู่ที่ interpreter: Mellow เร็วกว่า Python 5.9–23 เท่า และ
   เร็วกว่า Lua 1.15–1.30 เท่าบน wall clock
4. ตัวเลขนี้ยืนยันข้อสรุปเดิมว่า whole-process timing ที่ workload สั้นมาก
   วัด "startup floor" มากกว่าความเร็วภาษา ต้องดู ns/iter ของ chain ยาว
   (ในเอกสาร 2026-11-02) สำหรับ throughput จริง

## Startup floor (median of 15 runs, no-op program)

| Runtime | Floor ms |
| --- | ---: |
| Zig 0.16.0 (ReleaseFast) | 8.61 |
| C (gcc 13.2.0 -O3) | 9.51 |
| Rust 1.99.1 (-O) | 10.00 |
| Mellow 2.9.10 standalone | 10.54 |
| Lua 5.1.5 | 11.67 |
| Python 3.14.3 | 61.55 |

## Workloads (whole-process median, 15 repeats, ms)

| Workload | iters | Mellow | Rust | C | Zig | Python | Lua |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| sum_loop | 2,000,000 | 10.83 | 10.55 | 10.37 | 9.19 | 247.08 | 12.55 |
| function_calls | 200,000 | 10.31 | 10.92 | 10.27 | 9.96 | 84.85 | 11.55 |
| list_index | 500,000 | 11.59 | 10.98 | 10.56 | 9.61 | 114.56 | 15.00 |
| branch_mod | 500,000 | 10.73 | 10.82 | 10.75 | 9.39 | 113.18 | 12.35 |
| string_concat | 2,000 | 10.51 | 10.72 | 10.36 | 9.32 | 61.16 | 12.42 |

## Workload time above each runtime's own floor (ms)

This is the part of the wall clock that is not process startup. Values below
~0.5 ms are inside spawn noise.

| Workload | Mellow | Rust | C | Zig |
| --- | ---: | ---: | ---: | ---: |
| sum_loop | 0.29 | 0.55 | 0.86 | 0.58 |
| function_calls | -0.23 | 0.92 | 0.76 | 1.35 |
| list_index | 1.05 | 0.98 | 1.05 | 1.00 |
| branch_mod | 0.19 | 0.82 | 1.24 | 0.78 |
| string_concat | -0.03 | 0.72 | 0.85 | 0.71 |

Rust's floor sits about 1.4 ms above Zig's, 0.5 ms above C's, and 0.5 ms below
Mellow's, which matches a Rust `std` binary doing more runtime initialization
than a stripped Zig/C `main`. The workload deltas themselves stay within noise,
so these rows only support "same startup band", not a throughput ranking.

## Ratios against Mellow (whole process)

| Workload | Rust faster by | C faster by | Zig faster by | Mellow faster than Python | Mellow faster than Lua |
| --- | ---: | ---: | ---: | ---: | ---: |
| sum_loop | 1.03x | 1.04x | 1.18x | 22.81x | 1.16x |
| function_calls | 0.94x | 1.00x | 1.03x | 8.23x | 1.12x |
| list_index | 1.06x | 1.10x | 1.21x | 9.89x | 1.29x |
| branch_mod | 0.99x | 1.00x | 1.14x | 10.55x | 1.15x |
| string_concat | 0.98x | 1.01x | 1.13x | 5.82x | 1.18x |

A ratio below 1.0 means Mellow was faster in that run.

## Method notes

- `_time_command` does one warmup run, then 15 timed runs; the tables report
  medians.
- Mellow rows include parsing and compiling the `.mellow` source on every run.
  Compiled rows measure an already-built executable.
- The C, Rust, and Zig loops use the same shapes as before, so optimizer
  elision affects them equally; see the 2026-11-02 document for the shape cliff
  and the serialized-chain measurements.
- Re-run `python benchmarks/native_vs_zig/run_compare.py --repeats 15` before
  quoting these numbers; files under `build/` and this host's tool versions
  change the absolute values.
- Absolute medians move with host load: the quick-profile suite run a few
  minutes later measured every compiled runtime at 5–6 ms instead of ~10 ms.
  Compare runtimes inside one run, not across runs.
