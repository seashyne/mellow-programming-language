# Mellow v1.9.4 — Full SSA Construction + SCCP Pack

This pack extends the AST -> IR -> optimizer -> bytecode pipeline with conservative but real SSA metadata and new optimization passes.

## Added

- Full SSA metadata builder
  - phi placement via dominance frontier
  - dominator-tree-guided renaming
  - per-instruction SSA def/use mapping
- SCCP-oriented optimizer pass
  - executable-edge tracking
  - constant propagation across CFG
  - stronger constant branch pruning
- Loop invariant motion (conservative)
  - hoists simple invariant expressions from natural loops when a safe preheader exists
- New compiler metadata
  - `ssa_program`
  - `optimized_ssa_program`
- New optimization summary counters
  - `phi_nodes`
  - `sccp_constants`
  - `sccp_branches_pruned`
  - `loop_invariants_hoisted`
- New CLI dump flags
  - `--dump-ssa`
  - `--dump-ssa-optimized`

## Notes

- SSA is emitted as metadata for inspection and future optimization passes; the runtime still executes optimized bytecode.
- Phi placement and renaming are designed to be conservative and tooling-friendly.
- LICM currently focuses on simple loop-invariant expressions where the optimizer can identify a safe preheader.
- Unsupported lowering/features still fall back to the legacy compiler path.
