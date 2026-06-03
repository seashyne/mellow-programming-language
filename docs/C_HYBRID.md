# C Hybrid VM (v1.3.0-hybrid)

This fork adds an **optional C-accelerated VM loop** while keeping the compiler, CLI, formatter, linter,
and host modules in Python.

## What you get

- Faster instruction dispatch for simple scripts (hot loop in C)
- Full compatibility with existing Python host skills (via `SYSCALL`)
- Safe fallback to the legacy Python VM when:
  - the C extension is not built
  - the script uses unsupported opcodes (functions/events in this minimal release)

## v1.3.0 hybrid notes

- **TRY/CATCH parity**: errors raised inside a TRY block are caught and jump to the stored catch address.
- **PC error markers**: structured C errors carry `pc`, enabling Python to map to **line:col + code frame**.

## Build / Install

From the repo root:

```bash
python -m pip install -U pip
python -m pip install -e .
```

This will build the optional extension `mellowlang._mellowvm`.

> On Windows, you need *Build Tools for Visual Studio* (MSVC) installed.

## Run with the C engine

```bash
mellow run examples/hello.mellow --engine=c
```

Engine modes:

- `--engine=auto` (default): try C if available, otherwise Python
- `--engine=py`: force legacy Python VM
- `--engine=c`: force C VM (errors if missing/unsupported)

## Notes / Limitations (current)

The C VM supports most v1.2.x core opcodes, but parity is still growing. When an opcode is unsupported,
`--engine=auto` will fall back to the Python VM.

Scripts using **functions**, **events**, or advanced runtime features will fall back to the Python VM in `auto`
mode, or raise in `c` mode.

## Extending opcode coverage

See: `native/mellowvm/src/mellowvm_module.c`

Add cases in the big `switch(op)` and keep opcodes synced with `src/mellowlang/constants.py`.
