# MellowLang v1.9.2 — CFG + Dataflow Optimizer Pack

This release upgrades the new compiler pipeline with a real control-flow and
block-aware optimizer.

## Added

- Basic block construction for lowered IR
- Control-flow graph (CFG) builder
- Forward constant propagation across basic blocks
- Local value numbering (LVN) inside each basic block
- Serious branch pruning when a conditional becomes constant
- Compiler metadata:
  - `cfg`
  - `optimized_cfg`
  - richer `optimization` summary
- CLI dumps:
  - `--dump-cfg`
  - `--dump-cfg-optimized`

## Optimizer passes

### 1. Constant propagation
The optimizer tracks constant values stored in local variables and rewrites later
`LOAD` instructions into `PUSH` where safe.

### 2. Local value numbering
Inside a basic block, repeated pure expressions can be rewritten to reuse an
already-computed local value instead of rebuilding the same expression tree.

### 3. Branch pruning
When a conditional becomes constant after propagation/folding, the optimizer can:

- remove impossible conditional branches
- rewrite `JUMP_IF_FALSE` into `JUMP`
- remove fallthrough paths that can no longer execute

### 4. CFG-aware dead block removal
After branch pruning, unreachable blocks are removed before final bytecode
lowering.

## CLI

```bash
mellow compile examples/hello.mellow --dump-cfg
mellow compile examples/hello.mellow --dump-cfg-optimized
mellow compile examples/hello.mellow --dump-ir-optimized --dump-cfg-optimized
```

## Notes

- The AST → IR → optimized IR → bytecode pipeline remains conservative.
- Unsupported lowering features still fall back to the legacy compiler path.
- The new optimizer focuses on safety first so runtime compatibility stays high.
