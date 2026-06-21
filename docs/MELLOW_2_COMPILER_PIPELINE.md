# Mellow 2.0 Compiler Pipeline Foundation

This pack adds a real compiler pipeline:

`Source -> Parser(AST) -> IR -> Bytecode -> VM`

## What was added

- `src/mellowlang/ir.py`
  - IR dataclasses (`IRInstruction`, `IRFunction`, `IRProgram`)
- `src/mellowlang/compiler/ir_lowering.py`
  - Lowers parsed AST into a structured IR
- `src/mellowlang/compiler/bytecode_backend.py`
  - Converts IR labels/instructions into VM bytecode + debug maps
- `src/mellowlang/vm/ir_vm.py`
  - Executes IR by lowering into the stable VM backend
- `src/mellowlang/compiler/compiler.py`
  - Stable compiler facade now prefers the AST -> IR -> bytecode pipeline
  - Falls back to the complete bytecode compiler for unsupported IR features

## Supported by the new IR path

- literals, variables
- arithmetic / comparison / boolean expressions
- keep / let / assignment
- print/show
- calls
- if / while / count loop / foreach / range loop
- def / return
- event handlers (`on ...`)
- lists / maps / indexing
- save/load/put/wait/stop

## Current fallback behavior

Some advanced nodes compile through the complete bytecode backend, including:

- try/catch/finally
- default/variadic skill defs (`SkillDefV2`)
- some advanced expression forms (spread, kwargs, unpacking, etc.)

That means existing projects keep working while the new compiler pipeline grows.

## Tooling value

`CompiledProgram` now carries:

- `ast`
- `ir`
- `pipeline` (`"ast-ir-bytecode"` or `"bytecode"`)

So later you can add:

- optimizer passes
- IR dumps / graph views
- static analysis
- alt backends (JIT / C / WASM)
- workflow-aware scheduling optimizations

## Smoke check

Examples verified during packaging:

- `examples/hello.mellow` -> `ast-ir-bytecode`
- `examples/modern_quickstart.mellow` -> `ast-ir-bytecode`
- `examples/try_catch.mellow` -> `bytecode`

## Next recommended steps

1. Add SSA-ish temporary normalization pass on IR.
2. Add constant folding / dead jump elimination.
3. Add dedicated workflow IR ops (`EMIT_EVENT`, `ENQUEUE_JOB`, `CHECKPOINT`, `RETRY`).
4. Add `mellow compile --dump-ast --dump-ir` CLI output.
5. Add a direct IR interpreter for debugging mode.


## v1.9.1 additions

- `IROptimizer` runs after lowering and before bytecode emission.
- `mellow compile` can now dump AST, IR, optimized IR, and optimization summaries.
- `CompiledProgram` records `optimized_ir` and `optimization` metadata for tooling.


## v1.9.2 additions

- CFG builder over lowered IR
- basic-block aware optimization passes
- forward constant propagation across blocks
- local value numbering inside each block
- branch pruning + dead block removal
- compiler metadata now includes `cfg` and `optimized_cfg`


## v1.9.3 Analysis Layer

The compiler now keeps additional metadata around the optimized IR pipeline:

- CFG
- Dominator tree
- SSA-like def/use chains
- optimization summary including GVN and loop rewrite counts

This keeps the current bytecode VM stable while preparing the compiler for future SSA conversion, dominator-based simplification, and stronger loop optimizations.


## v1.9.4 additions

- SSA metadata generation with phi placement and dominator-driven renaming
- SCCP pass for executable-edge-aware constant propagation
- Conservative loop-invariant motion
- CLI inspection for SSA via `--dump-ssa` and `--dump-ssa-optimized`
