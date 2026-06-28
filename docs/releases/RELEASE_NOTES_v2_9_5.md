# Release Notes v2.9.5

This development patch focuses on making basic terminal I/O work as real Full
Native C built-ins.

## Native C I/O built-ins

- `print(...)` and `println(...)` print values separated by spaces and append a newline.
- `write(...)` prints values separated by spaces without appending a newline.
- `input(prompt="")` writes an optional prompt, reads one line from stdin, strips the trailing newline, and returns a string.
- `readline()`, `read_line()`, and `ask(...)` are native aliases for `input(...)`.

The standalone native runtime now implements these built-ins in C and the native
CLI tests exercise them by sending stdin to the compiled executable.

## Native system built-ins

- `args()` / `argv()` returns command-line arguments after the script path.
- `cwd()` returns the process current working directory.
- `sleep_ms(ms)` sleeps for an integer number of milliseconds.
- `exit(code=0)` terminates the native process with the requested exit code.

## Native builtin module aliases

- `import "math" as m`, `use sys as system`, and `need io as out` are now accepted by the Full Native C source compiler.
- Imported builtin aliases compile directly to the same native syscall IDs as direct calls such as `math.sqrt(...)` or `sys.cwd()`.
- This is an allowlisted builtin-module foundation only; local file/package module loading remains deferred until the native loader has cache and cycle handling.

## Native source layout

The standalone runtime now separates the default built-in syscall table from the
CLI entry point:

- `native/standalone/src/mellowrt_main.c` owns CLI parsing, source/image loading, and runtime wiring.
- `native/standalone/src/mellowrt_syscalls.c` owns the native built-in syscall table.
- `native/standalone/include/mellowrt_syscalls.h` exposes the syscall bridge and runtime context.
