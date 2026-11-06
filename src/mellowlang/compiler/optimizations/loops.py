"""Hoisting loop-invariant work out of loop bodies."""

from __future__ import annotations

from typing import List, Set

from ...ir import IRInstruction


class LoopInvariantMotionMixin:
    """Hoisting loop-invariant work out of loop bodies."""

    def _loop_invariant_motion(self, instructions: List[IRInstruction]) -> tuple[List[IRInstruction], int]:
        cfg = self.build_cfg(instructions)
        if not cfg.blocks:
            return instructions, 0
        dom = self.build_dominator_tree(cfg)
        hoisted = 0
        rewritten = list(instructions)
        labels = {str(ins.args[0]): idx for idx, ins in enumerate(rewritten) if ins.op == "LABEL"}
        for head, nodes in dom.natural_loops.items():
            loop_nodes = set(nodes)
            head_block = next((b for b in cfg.blocks if b.label == head), None)
            if head_block is None:
                continue
            outside_preds = [p for p in head_block.predecessors if p not in loop_nodes]
            if len(outside_preds) != 1:
                continue
            preheader = outside_preds[0]
            preheader_block = next((b for b in cfg.blocks if b.label == preheader), None)
            if preheader_block is None or not preheader_block.instructions:
                continue
            written_vars: Set[str] = set()
            for block in cfg.blocks:
                if block.label in loop_nodes:
                    for ins in block.instructions:
                        if ins.op in self.STORE_OPS or ins.op == "LOAD_F":
                            written_vars.add(str(ins.args[0]))
            # only hoist from loop head for now, keeping transform conservative
            block_ins = list(head_block.instructions)
            if len(block_ins) < 5:
                continue
            for i in range(1, len(block_ins) - 3):
                a, b, c, d = block_ins[i:i+4]
                if d.op not in self.STORE_OPS or c.op not in self.BINARY_OPS | self.UNARY_OPS:
                    continue
                expr_vars: Set[str] = set()
                pattern_ok = False
                if c.op in self.BINARY_OPS and a.op in {"LOAD", "PUSH"} and b.op in {"LOAD", "PUSH"}:
                    pattern_ok = True
                    if a.op == "LOAD": expr_vars.add(str(a.args[0]))
                    if b.op == "LOAD": expr_vars.add(str(b.args[0]))
                elif c.op in self.UNARY_OPS and a.op in {"LOAD", "PUSH"} and b.op == "POP":
                    pattern_ok = True
                    if a.op == "LOAD": expr_vars.add(str(a.args[0]))
                if not pattern_ok or any(v in written_vars for v in expr_vars):
                    continue
                # insert before terminating jump in preheader
                insert_at = preheader_block.end + 1
                if preheader_block.instructions[-1].op in self.TERMINATORS:
                    insert_at = preheader_block.end
                seq = [a, b, c, d]
                rewritten[insert_at:insert_at] = seq
                # remove original sequence (shift if needed)
                start_idx = head_block.start + i + (4 if insert_at <= head_block.start + i else 0)
                del rewritten[start_idx:start_idx+4]
                hoisted += 1
                break
            if hoisted:
                break
        return rewritten, hoisted
