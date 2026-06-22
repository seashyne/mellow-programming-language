# MellowLang v1.9.1 — Optimizer + IR Dump CLI Pack

## Highlights

- Added a safe IR optimizer for the new AST -> IR -> bytecode pipeline.
- Added CLI dump support for AST, raw IR, and optimized IR.
- Compiler metadata now records optimization summaries for tooling and profiling.

## New CLI examples

```bash
mellow compile examples/hello.mellow --dump-ast
mellow compile examples/hello.mellow --dump-ir
mellow compile examples/hello.mellow --dump-ir-optimized
mellow compile examples/hello.mellow --dump-ir --dump-ir-optimized --dump-format json
mellow compile examples/hello.mellow --no-optimize
```

## Optimizer passes

- constant folding for literal math/bool/compare instructions
- jump simplification
- dead code elimination after unconditional terminators
- unused label pruning

## Notes

The optimizer is intentionally conservative. Unsupported syntax still falls back to the legacy compiler path automatically.
