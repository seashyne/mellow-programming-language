# Mellow Full Native C

<p align="center">
  <img src="../../docs/assets/mellow-logo.png" alt="Mellow logo" width="72">
</p>

The native package now contains the source frontend and execution runtime in C.
The `mellow` executable reads, compiles, and runs `.mellow` source without
loading Python or CPython.

This tree is the forward path for Mellow runtime work. The standalone C runtime
is still the main supported path. The embeddable Mellow Runtime ABI is
experimental for now and should be updated gradually until it is ready to be
treated as stable.

What moved into native standalone now:
- lexer and expression parser
- source-to-bytecode compiler
- native `mellow` CLI with `run`, `check`, and `--version`
- arithmetic: add/sub/mul/div
- locals: load/store with per-frame local windows
- call/return: simple function refs and stack frames
- compare: eq/ne/lt/le/gt/ge
- jump/jump_if_false
- list/map builders
- syscall bridge: host callback contract in pure C
- native terminal I/O built-ins: `print`, `println`, `write`, `input`, `readline`, `read_line`, `ask`
- native system built-ins: `args`, `argv`, `cwd`, `sleep_ms`, `exit`
- native GC/concurrency foundation built-ins: `gc_collect`, `gc_stats`, `spawn`, `yield`, `channel`, `send`, `recv`
- debugger snapshots now include stack, frames, and locals

Native source layout:

- `include/mellow_runtime.h` — experimental embeddable runtime ABI for host applications
- `src/mellowc.c` — source lexer/compiler for `.mellow`
- `src/mellow_runtime.c` — runtime ABI wrapper over compiler, VM, syscalls, and GC
- `src/mellowrt_core.c` — bytecode VM and value ownership
- `src/mellowrt_syscalls.c` — built-in syscall table for I/O, math, env, args, cwd, sleep, exit, GC/concurrency foundation, and channels
- `src/mellowrt_main.c` — CLI entry point, source/image loading, and runtime wiring
- `src/mellowrt_platform.c` — target architecture/runtime-info probing
- `src/mellowrt_debug.c` — debug snapshot helpers

Native source syntax in v2.9.0:
- `let` / `keep` declarations and assignment
- numbers, strings, booleans, `none`
- arithmetic, comparisons, `and` / `or` / `not`
- `if` / `else`, `while`, and `for ... in range(...)`
- functions and return values
- lists, maps, and indexing
- `print`, `println`, `write`, `input`, `readline`, `read_line`, `ask`
- `args`, `argv`, `cwd`, `sleep_ms`, `exit`
- `gc_collect`, `gc_stats`, `spawn`, `yield`, `channel`, `send`, `recv`
- `len`, `str`, `type`, `abs`, `floor`, `ceil`, `sqrt`, `min`, `max`
- builtin module aliases: `import "math" as m`, `use sys as sys`, `need io as io`, `use chan as c`

Extended systems that remain outside the native runtime:
- import/module loader parity
- closures/upvalues
- native workflow/event runtime parity
- package manager, registry, LSP, playground, and deployment tooling

Build:

```bash
cmake -S native/standalone -B native/standalone/build
cmake --build native/standalone/build
./native/standalone/build/mellowrt
```

Try the experimental embedding wrapper from C:

```c
#include "mellow_runtime.h"

MellowRuntime *rt = mellow_runtime_new();
MellowCompiledProgram program;
MRunResult result;
char error[512] = {0};

if (mellow_runtime_compile_source(rt, "print(\"hi\")\n", "<embed>", &program, error, sizeof(error))) {
    mellow_runtime_run_program(rt, &program, &result);
    mellow_runtime_program_free(&program);
}
mellow_runtime_free(rt);
```

This wrapper is intentionally provisional. Use the `mellow` standalone
executable as the stable native path while the runtime ABI is still being
hardened.

Memory safety and fuzzing on Linux with Clang:

```bash
CC=clang cmake -S native/standalone -B build/standalone-safety \
  -DCMAKE_BUILD_TYPE=Debug \
  -DMELLOW_ENABLE_SANITIZERS=ON \
  -DMELLOW_BUILD_FUZZER=ON
cmake --build build/standalone-safety --parallel 2
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
  ctest --test-dir build/standalone-safety --output-on-failure
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
  build/standalone-safety/mellow_fuzz native/standalone/fuzz/corpus -runs=5000
```

This gate runs AddressSanitizer, UndefinedBehaviorSanitizer, LeakSanitizer, and
libFuzzer over both source compilation and runtime value ownership paths.

Run source directly:

```bash
./native/standalone/build/mellow examples/hello.mellow
./native/standalone/build/mellow check examples/hello.mellow
```

Native terminal I/O example:

```mellow
let name = input("Name: ")
write("Hello, ")
println(name)
```

When run by the native executable, the prompt is written to stdout, one line is
read from stdin, the trailing newline is stripped, and the result is returned as
a string.

Native system example:

```mellow
let argv = args()
print("argc:", len(argv))
print("cwd:", cwd())
sleep_ms(10)
exit(0)
```

Native builtin module alias example:

```mellow
import "math" as m
use sys as system
need io as out

out.println(m.sqrt(25))
out.println(system.cwd())
```

These imports are compile-time aliases for allowlisted native built-ins. They do
not load local files or packages yet.

Native GC/concurrency foundation example:

```mellow
gc_collect()
let stats = gc_stats()
print(stats["mode"])

def worker():
    return 1

let task = spawn(worker)
yield()

use chan as c
let mailbox = c.channel()
c.send(mailbox, "hello")
print(c.recv(mailbox))
```

In v2.9.6 these APIs are native C built-ins. Channels are FIFO native handles,
`spawn` returns cooperative task ids, and `yield` records explicit scheduling
points. `gc_stats()["mode"]` reports `mark-sweep-native-handles`; the collector
marks native handles from VM stack/locals and sweeps unreachable channel handles.
Full stack-switching M:N scheduling is still future runtime-engine work.

Inspect the binary's actual target and backend:

```bash
./native/standalone/build/mellow --runtime-info
```

ARM64 is release-gated through an `aarch64-linux-gnu-gcc` cross-build and QEMU
execution in CI. The current ARM64 backend is portable `generic-c`; NEON is
reported as a CPU capability but no optimized NEON kernel is claimed yet.
