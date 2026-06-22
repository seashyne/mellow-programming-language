# C Hybrid VM (v1.3.0-hybrid)

This fork adds an **optional C-accelerated VM loop** while keeping the compiler, CLI, formatter, linter,
and host modules in Python.

## What you get

- Faster instruction dispatch for simple scripts (hot loop in C)
- Full compatibility with existing Python host skills (via `SYSCALL`)
- Safe fallback to the Python VM when:
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

- `--engine=c` (default): use C first and fall back to Python for unsupported runtime features
- `--engine=auto`: compatibility alias for native-first execution
- `--engine=py`: force the Python VM
- `--native-required`: fail instead of falling back when `--engine=c` cannot run natively

Native release gates should use:

```powershell
mellow run path/to/test.mellow --engine=c --native-required
mellow test tests/language/fixtures --engine=c --native-required
```

## Notes / Limitations (current)

The C VM supports the stable core plus money, data, and ledger services. When an
opcode or runtime feature is unsupported, the default C mode falls back to the
Python VM.

Scripts using **events**, debugger hooks, record/replay, or advanced runtime
features without native parity fall back to the Python VM.

## Extending opcode coverage

See: `native/mellowvm/src/mellowvm_module.c`

Add cases in the big `switch(op)` and keep opcodes synced with `src/mellowlang/constants.py`.
