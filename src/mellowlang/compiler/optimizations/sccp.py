"""Sparse conditional constant propagation and branch pruning."""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple

from ...ir import IRInstruction


class SccpMixin:
    """Sparse conditional constant propagation and branch pruning."""

    def _sccp_optimize(self, instructions: List[IRInstruction]) -> tuple[List[IRInstruction], int, int]:
        cfg = self.build_cfg(instructions)
        if not cfg.blocks:
            return instructions, 0, 0
        block_map = {b.label: b for b in cfg.blocks}
        executable_edges: Set[Tuple[str, str]] = set()
        reachable: Set[str] = {cfg.entry_label}
        in_env: Dict[str, Dict[str, Any]] = {b.label: {} for b in cfg.blocks}
        out_env: Dict[str, Dict[str, Any]] = {b.label: {} for b in cfg.blocks}

        changed = True
        while changed:
            changed = False
            for block in cfg.blocks:
                preds = [p for p in block.predecessors if (p, block.label) in executable_edges or block.label == cfg.entry_label]
                if block.label != cfg.entry_label and not preds and block.label not in reachable:
                    continue
                pred_envs = [out_env[p] for p in preds if p in out_env]
                env_in = {} if block.label == cfg.entry_label else self._merge_envs(pred_envs)
                if env_in != in_env[block.label]:
                    in_env[block.label] = env_in
                    changed = True
                env_out, branch_value = self._transfer_env(block.instructions, dict(env_in))
                if env_out != out_env[block.label]:
                    out_env[block.label] = env_out
                    changed = True
                succs = self._reachable_successors(block, branch_value) - {block.label}
                for succ in succs:
                    edge = (block.label, succ)
                    if edge not in executable_edges:
                        executable_edges.add(edge)
                        changed = True
                    if succ not in reachable:
                        reachable.add(succ)
                        changed = True

        rewritten: List[IRInstruction] = []
        cp_count = 0
        branch_count = 0
        for block in cfg.blocks:
            if block.label not in reachable:
                continue
            block_out, cp, _lvn, bp, _js = self._rewrite_block(block.instructions, dict(in_env[block.label]))
            rewritten.extend(block_out)
            cp_count += cp
            branch_count += bp
        return rewritten, cp_count, branch_count

    def _prune_dead_branches_fixed_point(self, instructions: List[IRInstruction]) -> tuple[List[IRInstruction], int]:
        total_removed = 0
        current = list(instructions)
        while True:
            before = len(current)
            current, _ = self._simplify_jumps(current)
            current, removed = self._eliminate_dead_code(current)
            total_removed += removed
            current, _ = self._remove_unused_labels(current)
            if len(current) == before:
                break
        return current, total_removed
