# Release Notes v2.3.4 — Standalone Runtime Opcode Parity Pack

## Overview

v2.3.4 closes the gap between the Python VM and the standalone C runtime
(`mellowrt`).  The binary can now execute real Mellow programs — including
boolean logic, user-defined functions, lists, maps, strings, for/while loops,
modulo, power, and recursive functions — **without Python present at runtime**.

Compilation still requires Python (to run `mellow standalone compile`), but
the resulting `.mvi` binary image runs with only the native `mellowrt` binary.

---

## What's new

### Standalone image lowering (`src/mellowlang/standalone_image.py`)

| Change | Detail |
|--------|--------|
| New opcodes | `MOD (20)`, `POW (21)`, `BOOL_AND (22)`, `BOOL_OR (23)`, `BOOL_NOT (24)`, `GETITEM (25)`, `LEN (26)`, `PUSH_FUNC (27)`, `CALL_VAL (28)`, `STOP (29)` |
| Legacy compiler fallback | New IR compiler falls back to legacy for constructs it does not yet lower (`if`, `def`) |
| Syscall name routing | `PUSH('std.len')` / `PUSH('std.range')` before `SYSCALL` are resolved to C runtime IDs at compile time |
| Builtin CALL routing | `CALL('range', 2)`, `CALL('len', 1)` from IR compiler routed to syscall IDs |
| Two-pass JUMP fix | JUMP/JIF targets are recorded in pass 1 and remapped through a `src_pc→img_pc` table in pass 2, correcting targets that shift when `ARG` instructions are skipped |
| Function address remapping | Function body addresses in `func_table` are remapped through the same `src_pc→img_pc` table so nested function calls land at the correct image offset |
| Scope-aware slot allocation | Each function gets its own `var→slot` mapping starting at 0, built by scanning `ARG` sequences; global scope uses a separate flat map |
| Correct `local_count` | `local_count` in `FunctionEntry` now reflects all variables used inside the function (params + locals), not just params |
| Force legacy for standalone | The standalone path always uses the legacy compiler to avoid IR optimizer bugs with list/map variable access |

### C runtime — `native/standalone/src/mellowrt_core.c`

| Change | Detail |
|--------|--------|
| `#include <math.h>` | Required for `pow`, `fmod`, `floor`, `ceil`, `sqrt`, `fabs` |
| `mval_owned_str` | Helper to allocate a heap-owned string copy |
| `mvalue_deep_copy` | Recursive deep-copy for strings, lists, and maps; used by `PUSH_CONST` and `LOAD_LOCAL` to give every stack/local slot independent ownership |
| `MOP_MOD` | Integer modulo (Python-style sign) + float modulo via `fmod` |
| `MOP_POW` | Integer fast-path (binary exponentiation) + float fallback via `pow` |
| `MOP_BOOL_AND/OR/NOT` | Boolean operations using the `truthy` predicate |
| `MOP_GETITEM` | List indexing (with negative index support), map lookup, string character access |
| `MOP_LEN` | Length of list, string, or map |
| `MOP_CALL_VAL` | Call a first-class function value from the stack top |
| `MOP_STOP` | Alias of `MOP_HALT` |
| `CALL` callee position | Fixed: standalone lowering emits `arg0..argN, func_ref, CALL N`; callee is now read from `stack[top-1]` (not `stack[top-1-argc]`) |
| Move semantics | `STORE_LOCAL`, `BUILD_LIST`, `BUILD_MAP` move values off the stack (zero source slots) to prevent double-free |
| `LOAD_LOCAL` deep-copy | Every load produces an independently owned copy, preventing double-free when the same variable is stored in locals and then pushed onto the stack |

### C runtime — `native/standalone/src/mellowrt_main.c`

| Syscall ID | Function | Signature |
|-----------|----------|-----------|
| 1 | print | `print(args...)` |
| 2 | len | `len(container) → i64` |
| 3 | clock_ms | `clock_ms() → i64` |
| 4 | getenv | `getenv(name) → str \| none` |
| 5 | str | `str(val) → str` |
| 6 | type | `type(val) → str` |
| 7 | abs | `abs(n) → number` |
| 8 | floor | `floor(n) → i64` |
| 9 | ceil | `ceil(n) → i64` |
| 10 | sqrt | `sqrt(n) → f64` |
| 11 | min | `min(a, b) → number` |
| 12 | max | `max(a, b) → number` |
| 13 | print_n | variadic print (PRINTN) |
| 20 | range | `range(start, stop) → list[i64]` |

### Build system — `native/standalone/CMakeLists.txt`

- Added `target_link_libraries(mellowrt_core PUBLIC m)` to link `libm` for math functions

### Header — `native/standalone/include/mellowrt.h`

- Extended `MOpcode` enum with `MOP_MOD` through `MOP_STOP` (values 20–29)

---

## Test coverage (15/15 passing)

```
hello, arith, bool, func, list_idx, list_len, for_loop,
mod_pow, string_cat, nested_if, while_loop, map_get,
nested_func, fibonacci, string_ops
```

---

## Known limitations (deferred to v2.3.5+)

- `WAIT`, `ASK`, `SEED`, `TRY/ENDTRY`, `SAVE/LOAD_F`, `RANDFLOAT` emit `HALT 0xFF` (unsupported sentinel) in standalone images
- Closures / upvalues not supported in standalone
- Import / module loader (`get("math")`, `get("ai")`) not available in standalone
- GC / arena: memory is freed on `mvm_free` at program exit; long-running programs with heavy allocation may grow unboundedly
- New IR compiler has known variable-access bugs with `BUILD_LIST`/`BUILD_MAP` in the standalone path (standalone always uses legacy compiler for now)

---

## Upgrade guide

```bash
# Build the native binary (one-time)
cmake -S native/standalone -B native/standalone/build -DCMAKE_BUILD_TYPE=Release
cmake --build native/standalone/build

# Compile a .mellow file to a standalone image
mellow standalone compile my_script.mellow -o my_script.mvi

# Run without Python
./native/standalone/build/mellowrt my_script.mvi
```
