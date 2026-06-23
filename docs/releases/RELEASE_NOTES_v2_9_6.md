# Release Notes v2.9.6

v2.9.6 expands the Full Native C runtime with practical built-ins and the first
native GC/concurrency foundation.

The runtime direction is C-first. New core runtime features should be
implemented and validated in `native/standalone` in native-only mode.

## Native built-ins

- Added terminal I/O built-ins: `println`, `write`, `input`, `readline`, `read_line`, and `ask`.
- Added system built-ins: `args`, `argv`, `cwd`, `sleep_ms`, and `exit`.
- Split the native syscall table into `mellowrt_syscalls.c/.h` so the CLI entry
  point stays small and runtime built-ins have a clear home.

## Builtin modules

- Added compile-time alias support for allowlisted builtin modules:
  `io`, `sys`, `math`, `time`, `gc`, `thread`, and `chan`.
- Supported forms include `io.println(...)`, `get sys.args()`,
  `import "math" as m`, `use chan as c`, and `need io as out`.

## GC/concurrency foundation

- Added `gc_collect()` / `gc.stats()` with native mark/sweep collection for
  runtime-owned channel handles and `mark-sweep-native-handles` mode reporting.
- Added `spawn(fn)` and `yield()` as cooperative native scheduling foundation
  APIs.
- Added native FIFO channels through `channel()`, `send(ch, value)`, and
  `recv(ch)`.

This release deliberately does not claim full tracing GC or full M:N
stack-switching scheduling yet. The API shape is now native and testable; the
deeper runtime engine work can build on it safely.
