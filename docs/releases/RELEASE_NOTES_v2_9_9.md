# Release Notes v2.9.9

v2.9.9 is a structure release. No syscall, opcode, bytecode layout, CLI output,
or language rule changed. What changed is where the code lives and the gate that
keeps it there.

## Host registry split

- `src/mellowlang/host/runtime.py` went from 1,470 lines to a 66-line assembler.
  Capability types and the module allowlist moved to `host/base.py`; the 152
  registrations moved into fourteen `host/families/<name>.py` modules that each
  expose `register_<name>_functions(h)`, matching the convention already used by
  `ledger_core`, `interop_core`, `sdk_core`, and `ai_core`.
- `host/families/support.py` holds the argument-shape predicates shared by more
  than one family; the duplicated nested copies are gone.
- Import paths are unchanged: `mellowlang.host`, `mellowlang.host.runtime`,
  `mellowlang.host.registry`, and `mellowlang.host.modules` all still resolve to
  the same objects.
- Equivalence was proven, not reviewed: the 204-syscall registry has the same
  names, insertion order, costs, and argument bounds, handler bytecode differs
  only where a shared helper moved from a closure cell to a module import, and a
  differential battery of 7,020 calls per host produced identical results and
  identical errors.

## Standalone compiler split

- `native/standalone/src/mellowc.c` went from 1,210 lines to 629. The
  while-loop shape recognizers and their fused emitters - twenty file-static
  functions including `emit_fast_i64_sum_loop` and `emit_fast_string_append_loop` -
  now live in `mellowc_fastloops.inc`.
- The fragment is included, not compiled, so CMake needs no change and the
  helpers stay private to the `mellowc.c` translation unit, following the
  `mellowvm_*.inc` pattern.
- Verified with a Release rebuild, CTest 5/5, `tests/native` 91/91, and a
  shape probe that still produces `1999999000000` and `998986007`.

## Gates

- `tests/language/test_source_structure.py` now carries `LINE_CEILINGS`. A file
  over 1,000 lines must be declared there, and a declared file may not exceed
  its ceiling. Ceilings move down or the file gets split.
- New boundary tests assert the host family seam and the compiler fragment seam.
- `tests/test_workspace_boundaries.py` treats `native/standalone/**/*.inc` as C
  surface, so a fragment cannot reach the Python layer either.
- `docs/PROJECT_STRUCTURE.md` gained a Module Boundaries section, and the project
  skill records the seams plus the rule that the `native` job needs an explicit
  `cmake --build build/standalone-release --config Release` first, because CTest
  alone would pass against a stale binary.

## Performance work measured this round

The cross-language rerun is written up in
`benchmarks/native_vs_zig/RESULTS_2026-11-02_CROSS-LANGUAGE-HONEST.md`. Two
findings matter for the next release:

- The published per-workload ratios were startup- and optimizer-dominated. On a
  loop-carried serialized chain that no backend can eliminate, the standalone
  runtime measures 45.9 ns/iter against 2.8 ns/iter for gcc `-O3` and 4.0 ns/iter
  for Zig, so Mellow is a fast-starting interpreter, not a C-competitive
  compiler, and the README must say that.
- `std.money.*` on the standalone surface costs 553 microseconds per call at
  3,000 live blocks and 1,714 at 9,000, because `heap_find()` scans a linked
  list on every free and no GC trigger exists. The Python Decimal path is
  56 ns. This is the single largest measured defect on the native surface.

## Deferred

> Updated in v2.9.10: the standalone heap registry fix landed (pointer-keyed
> bucket index, measured in `RELEASE_NOTES_v2_9_10.md`), and `std.data` plus
> SQLite moved into the native runtime.

- The `package_manager.py` split stayed undone because that file carries
  uncommitted work; it is 1,220 lines against a 1,100 ceiling.
- The encrypted save envelope and MELV standalone CLI hooks remain Python-side.
- Fixing the standalone heap registry (hash-indexed lookup, threshold-triggered
  GC, freeing money temporaries) is queued as its own performance release.
