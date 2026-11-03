"""CFG, dominator tree, def-use chains, and SSA construction."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from ...ir import IRInstruction

from .ir_data import (
    BasicBlock,
    ControlFlowGraph,
    DefUseInfo,
    DominatorTree,
    PhiNode,
    SSAProgram,
)


class ControlFlowMixin:
    """CFG, dominator tree, def-use chains, and SSA construction."""

    def build_cfg(self, instructions: List[IRInstruction]) -> ControlFlowGraph:
        if not instructions:
            return ControlFlowGraph(entry_label="entry", blocks=[])

        labels = {str(ins.args[0]): idx for idx, ins in enumerate(instructions) if ins.op == "LABEL"}
        leaders: Set[int] = {0}
        for idx, ins in enumerate(instructions):
            if ins.op == "LABEL":
                leaders.add(idx)
            if ins.op in {"JUMP", "JUMP_IF_FALSE"}:
                target = labels.get(str(ins.args[0]))
                if target is not None:
                    leaders.add(target)
                if idx + 1 < len(instructions):
                    leaders.add(idx + 1)
            elif ins.op in {"RETURN", "STOP", "HALT"} and idx + 1 < len(instructions):
                leaders.add(idx + 1)
        ordered = sorted(leaders)
        blocks: List[BasicBlock] = []
        for i, start in enumerate(ordered):
            end = (ordered[i + 1] - 1) if i + 1 < len(ordered) else (len(instructions) - 1)
            block_ins = instructions[start : end + 1]
            if block_ins and block_ins[0].op == "LABEL":
                label = str(block_ins[0].args[0])
            else:
                label = f"block_{i}"
            blocks.append(BasicBlock(id=i, label=label, start=start, end=end, instructions=list(block_ins)))

        succs: Dict[str, List[str]] = {b.label: [] for b in blocks}
        preds: Dict[str, List[str]] = {b.label: [] for b in blocks}

        for i, block in enumerate(blocks):
            last = block.instructions[-1] if block.instructions else None
            local_succs: List[str] = []
            if last is None:
                pass
            elif last.op == "JUMP":
                target = str(last.args[0])
                if target in succs:
                    local_succs.append(target)
            elif last.op == "JUMP_IF_FALSE":
                target = str(last.args[0])
                if target in succs:
                    local_succs.append(target)
                if i + 1 < len(blocks):
                    local_succs.append(blocks[i + 1].label)
            elif last.op not in {"RETURN", "STOP", "HALT"}:
                if i + 1 < len(blocks):
                    local_succs.append(blocks[i + 1].label)
            succs[block.label] = local_succs
            for s in local_succs:
                preds[s].append(block.label)

        final_blocks = [
            BasicBlock(
                id=b.id,
                label=b.label,
                start=b.start,
                end=b.end,
                instructions=b.instructions,
                predecessors=preds[b.label],
                successors=succs[b.label],
            )
            for b in blocks
        ]
        entry = final_blocks[0].label if final_blocks else "entry"
        return ControlFlowGraph(entry_label=entry, blocks=final_blocks)

    def build_dominator_tree(self, cfg: ControlFlowGraph) -> DominatorTree:
        if not cfg.blocks:
            return DominatorTree(entry_label=cfg.entry_label, dominators={}, immediate_dominators={}, tree_children={}, back_edges=[], natural_loops={})
        labels = [b.label for b in cfg.blocks]
        block_map = {b.label: b for b in cfg.blocks}
        dom: Dict[str, Set[str]] = {label: set(labels) for label in labels}
        dom[cfg.entry_label] = {cfg.entry_label}
        changed = True
        while changed:
            changed = False
            for block in cfg.blocks:
                if block.label == cfg.entry_label:
                    continue
                pred_sets = [dom[p] for p in block.predecessors if p in dom]
                new_set = ({block.label} | set.intersection(*pred_sets)) if pred_sets else {block.label}
                if new_set != dom[block.label]:
                    dom[block.label] = new_set
                    changed = True
        idom: Dict[str, Optional[str]] = {cfg.entry_label: None}
        for block in cfg.blocks:
            if block.label == cfg.entry_label:
                continue
            strict = dom[block.label] - {block.label}
            candidate: Optional[str] = None
            for d in strict:
                if all(d == other or d not in dom[other] for other in strict):
                    candidate = d
                    break
            idom[block.label] = candidate
        tree_children: Dict[str, List[str]] = {label: [] for label in labels}
        for label, parent in idom.items():
            if parent is not None:
                tree_children.setdefault(parent, []).append(label)
        back_edges: List[Tuple[str, str]] = []
        natural_loops: Dict[str, List[str]] = {}
        for block in cfg.blocks:
            for succ in block.successors:
                if succ in dom.get(block.label, set()):
                    back_edges.append((block.label, succ))
                    loop_nodes = self._collect_natural_loop(cfg, block.label, succ)
                    natural_loops[succ] = sorted(set(natural_loops.get(succ, [])) | loop_nodes)
        return DominatorTree(
            entry_label=cfg.entry_label,
            dominators={k: sorted(v) for k, v in dom.items()},
            immediate_dominators=idom,
            tree_children={k: sorted(v) for k, v in tree_children.items()},
            back_edges=back_edges,
            natural_loops=natural_loops,
        )

    def build_def_use(self, instructions: List[IRInstruction]) -> DefUseInfo:
        defs_by_var: Dict[str, List[int]] = defaultdict(list)
        uses_by_var: Dict[str, List[int]] = defaultdict(list)
        ssa_names_by_var: Dict[str, List[str]] = defaultdict(list)
        def_to_uses: Dict[str, List[int]] = defaultdict(list)
        version_by_var: Dict[str, int] = defaultdict(int)
        current_def: Dict[str, str] = {}
        for idx, ins in enumerate(instructions):
            if ins.op == "LOAD":
                var = str(ins.args[0])
                uses_by_var[var].append(idx)
                def_key = current_def.get(var)
                if def_key is not None:
                    def_to_uses[def_key].append(idx)
            elif ins.op in self.STORE_OPS or ins.op == "LOAD_F":
                var = str(ins.args[0])
                defs_by_var[var].append(idx)
                version_by_var[var] += 1
                name = f"{var}#{version_by_var[var]}"
                ssa_names_by_var[var].append(name)
                current_def[var] = name
        return DefUseInfo(
            defs_by_var={k: list(v) for k, v in defs_by_var.items()},
            uses_by_var={k: list(v) for k, v in uses_by_var.items()},
            ssa_names_by_var={k: list(v) for k, v in ssa_names_by_var.items()},
            def_to_uses={k: list(v) for k, v in def_to_uses.items()},
        )

    def _collect_natural_loop(self, cfg: ControlFlowGraph, tail: str, head: str) -> Set[str]:
        block_map = {b.label: b for b in cfg.blocks}
        loop_nodes: Set[str] = {head, tail}
        worklist = [tail]
        while worklist:
            cur = worklist.pop()
            for pred in block_map[cur].predecessors:
                if pred not in loop_nodes:
                    loop_nodes.add(pred)
                    worklist.append(pred)
        return loop_nodes

    def build_ssa(self, cfg: ControlFlowGraph, dom: DominatorTree, instructions: List[IRInstruction]) -> SSAProgram:
        if not cfg.blocks:
            return SSAProgram(entry_label=cfg.entry_label, phi_nodes={}, instruction_defs={}, instruction_uses={}, versions_by_var={}, rename_order=[])
        block_map = {b.label: b for b in cfg.blocks}
        block_index = {b.label: idx for idx, b in enumerate(cfg.blocks)}
        defs_by_block: Dict[str, Set[str]] = {b.label: set() for b in cfg.blocks}
        all_vars: Set[str] = set()
        for block in cfg.blocks:
            for ins in block.instructions:
                if ins.op in self.STORE_OPS or ins.op == "LOAD_F":
                    var = str(ins.args[0])
                    defs_by_block[block.label].add(var)
                    all_vars.add(var)
                elif ins.op == "LOAD":
                    all_vars.add(str(ins.args[0]))

        dom_frontier = self._compute_dominance_frontier(cfg, dom)
        phi_blocks: Dict[str, Set[str]] = defaultdict(set)
        for var in sorted(all_vars):
            work = [label for label, defs in defs_by_block.items() if var in defs]
            seen = set(work)
            while work:
                label = work.pop()
                for frontier in dom_frontier.get(label, set()):
                    if var not in phi_blocks[frontier]:
                        phi_blocks[frontier].add(var)
                        if frontier not in seen:
                            seen.add(frontier)
                            work.append(frontier)

        versions: Dict[str, int] = defaultdict(int)
        stacks: Dict[str, List[str]] = defaultdict(list)
        phi_nodes: Dict[str, List[PhiNode]] = defaultdict(list)
        instruction_defs: Dict[int, List[str]] = defaultdict(list)
        instruction_uses: Dict[int, List[str]] = defaultdict(list)
        versions_by_var: Dict[str, List[str]] = defaultdict(list)
        rename_order: List[str] = []
        ins_index = {id(ins): idx for idx, ins in enumerate(instructions)}

        def fresh(var: str) -> str:
            versions[var] += 1
            name = f"{var}#{versions[var]}"
            stacks[var].append(name)
            versions_by_var[var].append(name)
            rename_order.append(name)
            return name

        def walk(label: str) -> None:
            pushed: List[str] = []
            for var in sorted(phi_blocks.get(label, set())):
                ver = fresh(var)
                phi_nodes[label].append(PhiNode(block_label=label, variable=var, version=ver, sources={pred: None for pred in block_map[label].predecessors}))
                pushed.append(var)
            for ins in block_map[label].instructions:
                idx = ins_index.get(id(ins))
                if idx is None:
                    continue
                if ins.op == "LOAD":
                    var = str(ins.args[0])
                    if stacks[var]:
                        instruction_uses[idx].append(stacks[var][-1])
                elif ins.op in self.STORE_OPS or ins.op == "LOAD_F":
                    var = str(ins.args[0])
                    ver = fresh(var)
                    instruction_defs[idx].append(ver)
                    pushed.append(var)
            for succ in block_map[label].successors:
                for i, phi in enumerate(phi_nodes.get(succ, [])):
                    var = phi.variable
                    src = stacks[var][-1] if stacks[var] else None
                    updated = dict(phi.sources)
                    updated[label] = src
                    phi_nodes[succ][i] = PhiNode(block_label=phi.block_label, variable=phi.variable, version=phi.version, sources=updated)
            for child in dom.tree_children.get(label, []):
                walk(child)
            for var in reversed(pushed):
                if stacks[var]:
                    stacks[var].pop()

        walk(cfg.entry_label)
        return SSAProgram(
            entry_label=cfg.entry_label,
            phi_nodes={k: list(v) for k, v in phi_nodes.items()},
            instruction_defs={k: list(v) for k, v in instruction_defs.items()},
            instruction_uses={k: list(v) for k, v in instruction_uses.items()},
            versions_by_var={k: list(v) for k, v in versions_by_var.items()},
            rename_order=rename_order,
        )

    def _compute_dominance_frontier(self, cfg: ControlFlowGraph, dom: DominatorTree) -> Dict[str, Set[str]]:
        frontier: Dict[str, Set[str]] = {b.label: set() for b in cfg.blocks}
        if not cfg.blocks:
            return frontier
        for block in cfg.blocks:
            if len(block.predecessors) < 2:
                continue
            for pred in block.predecessors:
                runner = pred
                while runner is not None and runner != dom.immediate_dominators.get(block.label):
                    frontier.setdefault(runner, set()).add(block.label)
                    runner = dom.immediate_dominators.get(runner)
        return frontier
