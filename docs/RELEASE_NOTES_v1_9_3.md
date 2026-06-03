# Mellow v1.9.3 — SSA Prep + Global Value Numbering Pack

## Added

- Dominator tree construction for IR CFGs
- SSA-like variable versioning / def-use chain metadata
- Global value numbering across dominator regions
- Loop-aware redundant expression elimination
- CLI dump flags:
  - `--dump-dom`
  - `--dump-dom-optimized`
  - `--dump-def-use`
  - `--dump-def-use-optimized`

## Optimizer Notes

This release is intentionally conservative. It adds the analysis foundation needed for a future full SSA pipeline without breaking the existing bytecode VM path.

The new optimizer focuses on:

- reusing previously computed expressions when they are dominated by an earlier definition
- avoiding reuse when a variable that appears inside the expression is written again
- counting loop-local rewrites separately so loop-heavy workloads can be measured

## Example

```bash
mellow compile examples/hello.mellow --dump-dom --dump-def-use
mellow compile examples/hello.mellow --dump-ir-optimized --dump-dom-optimized --dump-def-use-optimized
```
