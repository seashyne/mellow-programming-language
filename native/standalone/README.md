# Mellow 2.9.0 Full Native C

The native package now contains the source frontend and execution runtime in C.
The `mellow` executable reads, compiles, and runs `.mellow` source without
loading Python or CPython.

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
- debugger snapshots now include stack, frames, and locals

Native source syntax in v2.9.0:
- `let` / `keep` declarations and assignment
- numbers, strings, booleans, `none`
- arithmetic, comparisons, `and` / `or` / `not`
- `if` / `else`, `while`, and `for ... in range(...)`
- functions and return values
- lists, maps, and indexing
- `print`, `len`, `str`, `type`, `abs`, `floor`, `ceil`, `sqrt`, `min`, `max`

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

Run source directly:

```bash
./native/standalone/build/mellow examples/hello.mellow
./native/standalone/build/mellow check examples/hello.mellow
```
