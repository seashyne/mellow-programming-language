"""Assembles the pass mixins into the IR optimizer the pipeline calls."""

from __future__ import annotations

from typing import Dict, List

from ...ir import IRProgram

from .graph import ControlFlowMixin
from .folding import ConstantFoldingMixin
from .dataflow import DataflowMixin
from .rewrite import BlockRewriteMixin
from .gvn import GlobalValueNumberingMixin
from .sccp import SccpMixin
from .loops import LoopInvariantMotionMixin
from .cleanup import CleanupMixin
from .exprs import ExpressionMixin
from .ir_data import OptimizationSummary


class IROptimizer(
    ControlFlowMixin,
    ConstantFoldingMixin,
    DataflowMixin,
    BlockRewriteMixin,
    GlobalValueNumberingMixin,
    SccpMixin,
    LoopInvariantMotionMixin,
    CleanupMixin,
    ExpressionMixin,
):
    """CFG + SSA-prep + dataflow optimizer for the AST -> IR -> bytecode pipeline.

    v1.9.3 adds:
    - dominator tree construction
    - SSA-like variable versioning / def-use chains for inspection
    - global value numbering across dominator regions
    - loop-aware redundant expression elimination

    The optimizer remains conservative: unsupported ops simply become unknown.
    """

    TERMINATORS = {"JUMP", "JUMP_IF_FALSE", "RETURN", "STOP", "HALT"}
    STORE_OPS = {"STORE", "STORE_AUTO", "STORE_KEEP"}
    BINARY_OPS = {"ADD", "SUB", "MUL", "DIV", "MOD", "POW_OP", "COMPARE", "BOOL_AND", "BOOL_OR"}
    UNARY_OPS = {"BOOL_NOT"}
    SIDE_EFFECT_BARRIERS = {"PRINT", "PRINTN", "SAVE_VAL", "LIST_PUT", "WAIT", "SHOW_PREC", "LOAD_F", "CALL"}

    def optimize(self, program: IRProgram) -> tuple[IRProgram, OptimizationSummary]:
        instructions = list(program.instructions)
        before = len(instructions)
        passes: List[str] = []
        counts: Dict[str, int] = {
            "constants_folded": 0,
            "constants_propagated": 0,
            "jumps_simplified": 0,
            "branches_pruned": 0,
            "dead_instructions_removed": 0,
            "labels_removed": 0,
            "lvn_rewrites": 0,
            "gvn_rewrites": 0,
            "loop_rewrites": 0,
            "ssa_versions": 0,
            "phi_nodes": 0,
            "sccp_constants": 0,
            "sccp_branches_pruned": 0,
            "loop_invariants_hoisted": 0,
        }

        cfg_before = self.build_cfg(instructions)
        blocks_before = len(cfg_before.blocks)

        instructions, c = self._constant_fold(instructions)
        counts["constants_folded"] += c
        if c:
            passes.append("constant-fold")

        instructions, cp_count, lvn_count, branch_count, jump_count = self._cfg_dataflow_optimize(instructions)
        counts["constants_propagated"] += cp_count
        counts["lvn_rewrites"] += lvn_count
        counts["branches_pruned"] += branch_count
        counts["jumps_simplified"] += jump_count
        if cp_count:
            passes.append("constant-propagation")
        if lvn_count:
            passes.append("local-value-numbering")
        if branch_count:
            passes.append("branch-prune")
        if jump_count:
            passes.append("cfg-jump-simplify")

        cfg_mid = self.build_cfg(instructions)
        dom_mid = self.build_dominator_tree(cfg_mid)
        def_use_mid = self.build_def_use(instructions)
        ssa_mid = self.build_ssa(cfg_mid, dom_mid, instructions)
        counts["ssa_versions"] = sum(len(v) for v in def_use_mid.ssa_names_by_var.values())
        counts["phi_nodes"] = sum(len(v) for v in ssa_mid.phi_nodes.values())

        instructions, gvn_count, loop_count = self._global_value_numbering(instructions, cfg_mid, dom_mid)
        counts["gvn_rewrites"] += gvn_count
        counts["loop_rewrites"] += loop_count
        if gvn_count:
            passes.append("global-value-numbering")
        if loop_count:
            passes.append("loop-rewrite")

        instructions, c_const, c_branch = self._sccp_optimize(instructions)
        counts["sccp_constants"] += c_const
        counts["sccp_branches_pruned"] += c_branch
        if c_const:
            passes.append("sccp")
        if c_branch:
            passes.append("sccp-branch-prune")

        instructions, c = self._loop_invariant_motion(instructions)
        counts["loop_invariants_hoisted"] += c
        if c:
            passes.append("licm")

        instructions, c = self._simplify_jumps(instructions)
        counts["jumps_simplified"] += c
        if c and "jump-simplify" not in passes:
            passes.append("jump-simplify")

        instructions, c = self._prune_dead_branches_fixed_point(instructions)
        counts["dead_instructions_removed"] += c
        if c and "dead-code" not in passes:
            passes.append("dead-code")

        instructions, c = self._eliminate_dead_code(instructions)
        counts["dead_instructions_removed"] += c
        if c:
            passes.append("dead-code")

        instructions, c = self._remove_unused_labels(instructions)
        counts["labels_removed"] += c
        if c:
            passes.append("label-prune")

        cfg_after = self.build_cfg(instructions)
        blocks_after = len(cfg_after.blocks)
        after = len(instructions)
        return IRProgram(
            instructions=instructions,
            functions=dict(program.functions),
            events=dict(program.events),
            filename=program.filename,
        ), OptimizationSummary(
            passes=passes,
            instructions_before=before,
            instructions_after=after,
            labels_removed=counts["labels_removed"],
            constants_folded=counts["constants_folded"],
            constants_propagated=counts["constants_propagated"],
            jumps_simplified=counts["jumps_simplified"],
            branches_pruned=counts["branches_pruned"],
            dead_instructions_removed=counts["dead_instructions_removed"],
            lvn_rewrites=counts["lvn_rewrites"],
            gvn_rewrites=counts["gvn_rewrites"],
            loop_rewrites=counts["loop_rewrites"],
            blocks_before=blocks_before,
            blocks_after=blocks_after,
            ssa_versions=counts["ssa_versions"],
            phi_nodes=counts["phi_nodes"],
            sccp_constants=counts["sccp_constants"],
            sccp_branches_pruned=counts["sccp_branches_pruned"],
            loop_invariants_hoisted=counts["loop_invariants_hoisted"],
        )
