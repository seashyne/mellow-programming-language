# Standalone Mellow Runtime Opcode Migration Pack

This pack extends the standalone runtime from a scaffold into a more realistic execution core.

What moved into native standalone now:
- arithmetic: add/sub/mul/div
- locals: load/store with per-frame local windows
- call/return: simple function refs and stack frames
- compare: eq/ne/lt/le/gt/ge
- jump/jump_if_false
- list/map builders
- syscall bridge: host callback contract in pure C
- debugger snapshots now include stack, frames, and locals

What still is not complete yet:
- heap-managed strings/bytes ownership
- import/module loader parity
- closures/upvalues
- GC / arena / refcount policy
- native workflow/event runtime parity
- bytecode serializer from the Python compiler pipeline

Build:

```bash
cmake -S native/standalone -B native/standalone/build
cmake --build native/standalone/build
./native/standalone/build/mellowrt
```
