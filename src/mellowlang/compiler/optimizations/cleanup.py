"""Jump simplification, dead code removal, label pruning."""

from __future__ import annotations

from typing import Dict, List, Set

from ...ir import IRInstruction


class CleanupMixin:
    """Jump simplification, dead code removal, label pruning."""

    def _simplify_jumps(self, instructions: List[IRInstruction]) -> tuple[List[IRInstruction], int]:
        labels = {str(ins.args[0]): idx for idx, ins in enumerate(instructions) if ins.op == "LABEL"}
        out: List[IRInstruction] = []
        count = 0
        i = 0
        while i < len(instructions):
            ins = instructions[i]
            if ins.op == "JUMP" and i + 1 < len(instructions) and instructions[i + 1].op == "LABEL" and str(ins.args[0]) == str(instructions[i + 1].args[0]):
                count += 1
                i += 1
                continue
            if ins.op in {"JUMP", "JUMP_IF_FALSE"}:
                target = str(ins.args[0])
                resolved = self._follow_jump_chain(target, labels, instructions)
                if resolved != target:
                    out.append(IRInstruction(ins.op, (resolved,), line=ins.line, col=ins.col))
                    count += 1
                    i += 1
                    continue
            out.append(ins)
            i += 1
        return out, count

    def _eliminate_dead_code(self, instructions: List[IRInstruction]) -> tuple[List[IRInstruction], int]:
        cfg = self.build_cfg(instructions)
        if not cfg.blocks:
            return instructions, 0
        block_map = {b.label: b for b in cfg.blocks}
        reachable: Set[str] = set()
        queue: List[str] = [cfg.entry_label]
        while queue:
            label = queue.pop(0)
            if label in reachable:
                continue
            reachable.add(label)
            for succ in block_map[label].successors:
                if succ not in reachable:
                    queue.append(succ)
        kept: List[IRInstruction] = []
        removed = 0
        for block in cfg.blocks:
            if block.label in reachable:
                kept.extend(block.instructions)
            else:
                removed += len(block.instructions)
        return kept, removed

    def _remove_unused_labels(self, instructions: List[IRInstruction]) -> tuple[List[IRInstruction], int]:
        used: Set[str] = set()
        for ins in instructions:
            if ins.op in {"JUMP", "JUMP_IF_FALSE"}:
                used.add(str(ins.args[0]))
        entry = None
        for ins in instructions:
            if ins.op == "LABEL":
                entry = str(ins.args[0])
                break
            if ins.op != "LABEL":
                break
        pruned: List[IRInstruction] = []
        removed = 0
        for ins in instructions:
            if ins.op == "LABEL" and str(ins.args[0]) not in used and str(ins.args[0]) != entry:
                removed += 1
                continue
            pruned.append(ins)
        return pruned, removed

    def _follow_jump_chain(self, label: str, labels: Dict[str, int], instructions: List[IRInstruction]) -> str:
        seen: Set[str] = set()
        cur = label
        while cur not in seen:
            seen.add(cur)
            idx = labels.get(cur)
            if idx is None:
                return cur
            j = idx + 1
            while j < len(instructions) and instructions[j].op == "LABEL":
                j += 1
            if j < len(instructions) and instructions[j].op == "JUMP":
                cur = str(instructions[j].args[0])
                continue
            return cur
        return label
