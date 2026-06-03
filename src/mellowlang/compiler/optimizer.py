from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from ..ir import IRInstruction, IRProgram


_CONST_TOP = object()


@dataclass(frozen=True)
class BasicBlock:
    id: int
    label: str
    start: int
    end: int
    instructions: List[IRInstruction]
    predecessors: List[str] = field(default_factory=list)
    successors: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ControlFlowGraph:
    entry_label: str
    blocks: List[BasicBlock]


@dataclass(frozen=True)
class DominatorTree:
    entry_label: str
    dominators: Dict[str, List[str]]
    immediate_dominators: Dict[str, Optional[str]]
    tree_children: Dict[str, List[str]]
    back_edges: List[Tuple[str, str]] = field(default_factory=list)
    natural_loops: Dict[str, List[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class DefUseInfo:
    defs_by_var: Dict[str, List[int]]
    uses_by_var: Dict[str, List[int]]
    ssa_names_by_var: Dict[str, List[str]]
    def_to_uses: Dict[str, List[int]]


@dataclass(frozen=True)
class PhiNode:
    block_label: str
    variable: str
    version: str
    sources: Dict[str, Optional[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class SSAProgram:
    entry_label: str
    phi_nodes: Dict[str, List[PhiNode]]
    instruction_defs: Dict[int, List[str]]
    instruction_uses: Dict[int, List[str]]
    versions_by_var: Dict[str, List[str]]
    rename_order: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class OptimizationSummary:
    passes: List[str]
    instructions_before: int
    instructions_after: int
    labels_removed: int = 0
    constants_folded: int = 0
    constants_propagated: int = 0
    jumps_simplified: int = 0
    branches_pruned: int = 0
    dead_instructions_removed: int = 0
    lvn_rewrites: int = 0
    gvn_rewrites: int = 0
    loop_rewrites: int = 0
    blocks_before: int = 0
    blocks_after: int = 0
    ssa_versions: int = 0
    phi_nodes: int = 0
    sccp_constants: int = 0
    sccp_branches_pruned: int = 0
    loop_invariants_hoisted: int = 0


@dataclass
class _StackValue:
    const: Any = _CONST_TOP
    expr: Any = None
    start: int = -1


class IROptimizer:
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

    # ---------------- CFG / dominators / def-use ----------------

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

    # ---------------- front-end constant folding ----------------

    def _constant_fold(self, instructions: List[IRInstruction]) -> tuple[List[IRInstruction], int]:
        out: List[IRInstruction] = []
        count = 0
        i = 0
        while i < len(instructions):
            if i + 2 < len(instructions):
                a, b, c = instructions[i], instructions[i + 1], instructions[i + 2]
                if a.op == "PUSH" and b.op == "PUSH" and c.op in self.BINARY_OPS:
                    ok, value = self._eval_binary(a.args[0], b.args[0], c)
                    if ok:
                        out.append(IRInstruction("PUSH", (value,), line=c.line, col=c.col))
                        count += 1
                        i += 3
                        continue
                if a.op == "PUSH" and b.op in self.UNARY_OPS:
                    ok, value = self._eval_unary(a.args[0], b)
                    if ok:
                        out.append(IRInstruction("PUSH", (value,), line=b.line, col=b.col))
                        count += 1
                        i += 2
                        continue
            out.append(instructions[i])
            i += 1
        return out, count

    # ---------------- dataflow / block rewrite ----------------

    def _cfg_dataflow_optimize(self, instructions: List[IRInstruction]) -> tuple[List[IRInstruction], int, int, int, int]:
        cfg = self.build_cfg(instructions)
        if not cfg.blocks:
            return instructions, 0, 0, 0, 0

        block_map = {b.label: b for b in cfg.blocks}
        in_env: Dict[str, Dict[str, Any]] = {b.label: {} for b in cfg.blocks}
        out_env: Dict[str, Dict[str, Any]] = {b.label: {} for b in cfg.blocks}
        reachable: Set[str] = {cfg.entry_label}

        changed = True
        while changed:
            changed = False
            for block in cfg.blocks:
                if block.label != cfg.entry_label and not any(pred in reachable for pred in block.predecessors):
                    continue
                pred_envs = [out_env[p] for p in block.predecessors if p in reachable]
                env_in = {} if block.label == cfg.entry_label else self._merge_envs(pred_envs)
                if env_in != in_env[block.label]:
                    in_env[block.label] = env_in
                    changed = True
                env_out, branch_value = self._transfer_env(block.instructions, dict(env_in))
                if env_out != out_env[block.label]:
                    out_env[block.label] = env_out
                    changed = True
                new_reachable = self._reachable_successors(block, branch_value)
                before = len(reachable)
                reachable.update(new_reachable)
                if len(reachable) != before:
                    changed = True

        rewritten: List[IRInstruction] = []
        cp_count = 0
        lvn_count = 0
        branch_count = 0
        jump_count = 0
        for block in cfg.blocks:
            if block.label not in reachable:
                continue
            block_out, cp, lvn, bp, js = self._rewrite_block(block.instructions, dict(in_env[block.label]))
            rewritten.extend(block_out)
            cp_count += cp
            lvn_count += lvn
            branch_count += bp
            jump_count += js
        return rewritten, cp_count, lvn_count, branch_count, jump_count

    def _reachable_successors(self, block: BasicBlock, branch_value: Any) -> Set[str]:
        if not block.successors:
            return {block.label}
        last = block.instructions[-1] if block.instructions else None
        reachable = {block.label}
        if last and last.op == "JUMP_IF_FALSE" and branch_value is not _CONST_TOP:
            target = str(last.args[0])
            if bool(branch_value):
                if len(block.successors) > 1:
                    reachable.add(block.successors[1])
            else:
                reachable.add(target)
            return reachable
        reachable.update(block.successors)
        return reachable

    def _merge_envs(self, envs: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not envs:
            return {}
        keys = set().union(*[set(e.keys()) for e in envs])
        merged: Dict[str, Any] = {}
        for key in keys:
            values = [e.get(key, _CONST_TOP) for e in envs]
            first = values[0]
            if all(v == first for v in values):
                merged[key] = first
            else:
                merged[key] = _CONST_TOP
        return merged

    def _transfer_env(self, instructions: List[IRInstruction], env: Dict[str, Any]) -> tuple[Dict[str, Any], Any]:
        stack: List[Any] = []
        branch_value: Any = _CONST_TOP
        for ins in instructions:
            op = ins.op
            if op == "PUSH":
                stack.append(ins.args[0])
            elif op == "LOAD":
                stack.append(env.get(str(ins.args[0]), _CONST_TOP))
            elif op in self.STORE_OPS:
                value = stack.pop() if stack else _CONST_TOP
                env[str(ins.args[0])] = value
            elif op in self.BINARY_OPS:
                right = stack.pop() if stack else _CONST_TOP
                left = stack.pop() if stack else _CONST_TOP
                if left is not _CONST_TOP and right is not _CONST_TOP:
                    ok, value = self._eval_binary(left, right, ins)
                    stack.append(value if ok else _CONST_TOP)
                else:
                    stack.append(_CONST_TOP)
            elif op in self.UNARY_OPS:
                value = stack.pop() if stack else _CONST_TOP
                if value is not _CONST_TOP:
                    ok, res = self._eval_unary(value, ins)
                    stack.append(res if ok else _CONST_TOP)
                else:
                    stack.append(_CONST_TOP)
            elif op == "POP":
                if stack:
                    stack.pop()
            elif op == "JUMP_IF_FALSE":
                branch_value = stack.pop() if stack else _CONST_TOP
            elif op == "CALL":
                argc = int(ins.args[1]) if len(ins.args) > 1 else 0
                for _ in range(argc):
                    if stack:
                        stack.pop()
                stack.append(_CONST_TOP)
            elif op == "LEN":
                value = stack.pop() if stack else _CONST_TOP
                if value is not _CONST_TOP:
                    try:
                        stack.append(len(value))
                    except Exception:
                        stack.append(_CONST_TOP)
                else:
                    stack.append(_CONST_TOP)
            elif op == "GETITEM":
                idx = stack.pop() if stack else _CONST_TOP
                obj = stack.pop() if stack else _CONST_TOP
                if obj is not _CONST_TOP and idx is not _CONST_TOP:
                    try:
                        stack.append(obj[idx])
                    except Exception:
                        stack.append(_CONST_TOP)
                else:
                    stack.append(_CONST_TOP)
            elif op in {"PRINT", "PRINTN", "SAVE_VAL", "LIST_PUT", "WAIT", "SHOW_PREC", "LOAD_F"}:
                if op == "LOAD_F":
                    env[str(ins.args[0])] = _CONST_TOP
                else:
                    stack.clear()
            elif op in {"LABEL", "JUMP", "RETURN", "STOP", "HALT"}:
                pass
            else:
                stack.clear()
        return env, branch_value

    def _rewrite_block(self, instructions: List[IRInstruction], env: Dict[str, Any]) -> tuple[List[IRInstruction], int, int, int, int]:
        out: List[IRInstruction] = []
        stack: List[_StackValue] = []
        cp_count = 0
        lvn_count = 0
        branch_count = 0
        jump_count = 0
        value_of_var: Dict[str, Any] = {k: self._const_expr(v) if v is not _CONST_TOP else None for k, v in env.items()}
        expr_to_var: Dict[Any, str] = {}
        for name, expr in value_of_var.items():
            if expr is not None:
                expr_to_var[expr] = name

        for ins in instructions:
            op = ins.op
            if op == "LABEL":
                out.append(ins)
                continue

            if op == "PUSH":
                out.append(ins)
                stack.append(_StackValue(const=ins.args[0], expr=self._const_expr(ins.args[0]), start=len(out) - 1))
                continue

            if op == "LOAD":
                var_name = str(ins.args[0])
                known = env.get(var_name, _CONST_TOP)
                if known is not _CONST_TOP:
                    out.append(IRInstruction("PUSH", (known,), line=ins.line, col=ins.col))
                    stack.append(_StackValue(const=known, expr=self._const_expr(known), start=len(out) - 1))
                    cp_count += 1
                else:
                    out.append(ins)
                    expr = value_of_var.get(var_name) or ("var", var_name)
                    stack.append(_StackValue(const=_CONST_TOP, expr=expr, start=len(out) - 1))
                continue

            if op in self.BINARY_OPS:
                right = stack.pop() if stack else _StackValue()
                left = stack.pop() if stack else _StackValue()
                out.append(ins)
                start = min(v.start for v in (left, right) if v.start >= 0) if (left.start >= 0 or right.start >= 0) else len(out) - 1
                if left.const is not _CONST_TOP and right.const is not _CONST_TOP:
                    ok, value = self._eval_binary(left.const, right.const, ins)
                    if ok:
                        out[start:] = [IRInstruction("PUSH", (value,), line=ins.line, col=ins.col)]
                        stack.append(_StackValue(const=value, expr=self._const_expr(value), start=start))
                        cp_count += 1
                        continue
                expr = self._expr_for_binary(op, left.expr, right.expr, ins)
                existing_var = expr_to_var.get(expr)
                if existing_var and value_of_var.get(existing_var) == expr:
                    out[start:] = [IRInstruction("LOAD", (existing_var,), line=ins.line, col=ins.col)]
                    stack.append(_StackValue(const=_CONST_TOP, expr=expr, start=start))
                    lvn_count += 1
                    continue
                stack.append(_StackValue(const=_CONST_TOP, expr=expr, start=start))
                continue

            if op in self.UNARY_OPS:
                value = stack.pop() if stack else _StackValue()
                out.append(ins)
                start = value.start if value.start >= 0 else len(out) - 1
                if value.const is not _CONST_TOP:
                    ok, result = self._eval_unary(value.const, ins)
                    if ok:
                        out[start:] = [IRInstruction("PUSH", (result,), line=ins.line, col=ins.col)]
                        stack.append(_StackValue(const=result, expr=self._const_expr(result), start=start))
                        cp_count += 1
                        continue
                stack.append(_StackValue(const=_CONST_TOP, expr=(op, value.expr), start=start))
                continue

            if op in self.STORE_OPS:
                value = stack.pop() if stack else _StackValue()
                out.append(ins)
                var_name = str(ins.args[0])
                env[var_name] = value.const
                value_of_var[var_name] = value.expr
                if value.expr is not None:
                    expr_to_var[value.expr] = var_name
                self._invalidate_var_aliases(expr_to_var, value_of_var, var_name)
                continue

            if op == "POP":
                if stack:
                    stack.pop()
                out.append(ins)
                continue

            if op == "JUMP_IF_FALSE":
                cond = stack.pop() if stack else _StackValue()
                if cond.const is not _CONST_TOP:
                    out[cond.start:] = []
                    if bool(cond.const):
                        branch_count += 1
                        continue
                    out.append(IRInstruction("JUMP", ins.args, line=ins.line, col=ins.col))
                    branch_count += 1
                    jump_count += 1
                    continue
                out.append(ins)
                continue

            if op == "JUMP":
                out.append(ins)
                continue

            if op == "CALL":
                argc = int(ins.args[1]) if len(ins.args) > 1 else 0
                for _ in range(argc):
                    if stack:
                        stack.pop()
                out.append(ins)
                stack.append(_StackValue(const=_CONST_TOP, expr=("call",) + tuple(ins.args), start=len(out) - 1))
                continue

            if op == "LEN":
                value = stack.pop() if stack else _StackValue()
                out.append(ins)
                start = value.start if value.start >= 0 else len(out) - 1
                if value.const is not _CONST_TOP:
                    try:
                        result = len(value.const)
                        out[start:] = [IRInstruction("PUSH", (result,), line=ins.line, col=ins.col)]
                        stack.append(_StackValue(const=result, expr=self._const_expr(result), start=start))
                        cp_count += 1
                        continue
                    except Exception:
                        pass
                stack.append(_StackValue(const=_CONST_TOP, expr=("len", value.expr), start=start))
                continue

            if op == "GETITEM":
                idx = stack.pop() if stack else _StackValue()
                obj = stack.pop() if stack else _StackValue()
                out.append(ins)
                starts = [v.start for v in (obj, idx) if v.start >= 0]
                start = min(starts) if starts else len(out) - 1
                if obj.const is not _CONST_TOP and idx.const is not _CONST_TOP:
                    try:
                        result = obj.const[idx.const]
                        out[start:] = [IRInstruction("PUSH", (result,), line=ins.line, col=ins.col)]
                        stack.append(_StackValue(const=result, expr=self._const_expr(result), start=start))
                        cp_count += 1
                        continue
                    except Exception:
                        pass
                stack.append(_StackValue(const=_CONST_TOP, expr=("getitem", obj.expr, idx.expr), start=start))
                continue

            if op == "LOAD_F":
                out.append(ins)
                var_name = str(ins.args[0])
                env[var_name] = _CONST_TOP
                value_of_var[var_name] = None
                self._invalidate_var_aliases(expr_to_var, value_of_var, var_name)
                continue

            out.append(ins)
            if op in {"PRINT", "PRINTN", "SAVE_VAL", "LIST_PUT", "WAIT", "SHOW_PREC"}:
                stack.clear()
            elif op in {"RETURN", "STOP", "HALT"}:
                stack.clear()
        return out, cp_count, lvn_count, branch_count, jump_count

    # ---------------- global value numbering / loops ----------------

    def _global_value_numbering(self, instructions: List[IRInstruction], cfg: ControlFlowGraph, dom: DominatorTree) -> tuple[List[IRInstruction], int, int]:
        if not cfg.blocks:
            return instructions, 0, 0
        block_map = {b.label: b for b in cfg.blocks}
        def_use = self.build_def_use(instructions)
        write_blocks_by_var: Dict[str, Set[str]] = defaultdict(set)
        for block in cfg.blocks:
            for ins in block.instructions:
                if ins.op in self.STORE_OPS or ins.op == "LOAD_F":
                    write_blocks_by_var[str(ins.args[0])].add(block.label)
        loop_nodes = {node for nodes in dom.natural_loops.values() for node in nodes}

        gvn_rewrites = 0
        loop_rewrites = 0

        def walk(label: str, available_exprs: Dict[Any, str], available_values: Dict[str, Any]) -> List[IRInstruction]:
            nonlocal gvn_rewrites, loop_rewrites
            block = block_map[label]
            exprs = dict(available_exprs)
            values = dict(available_values)
            stack: List[_StackValue] = []
            out: List[IRInstruction] = []
            for ins in block.instructions:
                op = ins.op
                if op == "LABEL":
                    out.append(ins)
                    continue
                if op == "PUSH":
                    out.append(ins)
                    stack.append(_StackValue(const=ins.args[0], expr=self._const_expr(ins.args[0]), start=len(out)-1))
                    continue
                if op == "LOAD":
                    var = str(ins.args[0])
                    out.append(ins)
                    stack.append(_StackValue(const=_CONST_TOP, expr=values.get(var, ("var", var)), start=len(out)-1))
                    continue
                if op in self.BINARY_OPS:
                    right = stack.pop() if stack else _StackValue()
                    left = stack.pop() if stack else _StackValue()
                    out.append(ins)
                    starts = [v.start for v in (left, right) if v.start >= 0]
                    start = min(starts) if starts else len(out)-1
                    expr = self._expr_for_binary(op, left.expr, right.expr, ins)
                    existing_var = exprs.get(expr)
                    if existing_var and self._expr_safe_to_reuse(expr, write_blocks_by_var, dom, label):
                        out[start:] = [IRInstruction("LOAD", (existing_var,), line=ins.line, col=ins.col)]
                        stack.append(_StackValue(const=_CONST_TOP, expr=expr, start=start))
                        gvn_rewrites += 1
                        if label in loop_nodes:
                            loop_rewrites += 1
                        continue
                    stack.append(_StackValue(const=_CONST_TOP, expr=expr, start=start))
                    continue
                if op in self.UNARY_OPS:
                    value = stack.pop() if stack else _StackValue()
                    out.append(ins)
                    start = value.start if value.start >= 0 else len(out)-1
                    expr = (op, value.expr)
                    existing_var = exprs.get(expr)
                    if existing_var and self._expr_safe_to_reuse(expr, write_blocks_by_var, dom, label):
                        out[start:] = [IRInstruction("LOAD", (existing_var,), line=ins.line, col=ins.col)]
                        stack.append(_StackValue(const=_CONST_TOP, expr=expr, start=start))
                        gvn_rewrites += 1
                        if label in loop_nodes:
                            loop_rewrites += 1
                        continue
                    stack.append(_StackValue(const=_CONST_TOP, expr=expr, start=start))
                    continue
                if op in {"LEN", "GETITEM"}:
                    if op == "LEN":
                        value = stack.pop() if stack else _StackValue()
                        out.append(ins)
                        start = value.start if value.start >= 0 else len(out)-1
                        expr = ("len", value.expr)
                    else:
                        idxv = stack.pop() if stack else _StackValue()
                        objv = stack.pop() if stack else _StackValue()
                        out.append(ins)
                        starts = [v.start for v in (objv, idxv) if v.start >= 0]
                        start = min(starts) if starts else len(out)-1
                        expr = ("getitem", objv.expr, idxv.expr)
                    existing_var = exprs.get(expr)
                    if existing_var and self._expr_safe_to_reuse(expr, write_blocks_by_var, dom, label):
                        out[start:] = [IRInstruction("LOAD", (existing_var,), line=ins.line, col=ins.col)]
                        stack.append(_StackValue(const=_CONST_TOP, expr=expr, start=start))
                        gvn_rewrites += 1
                        if label in loop_nodes:
                            loop_rewrites += 1
                        continue
                    stack.append(_StackValue(const=_CONST_TOP, expr=expr, start=start))
                    continue
                if op in self.STORE_OPS:
                    value = stack.pop() if stack else _StackValue()
                    out.append(ins)
                    var = str(ins.args[0])
                    self._kill_exprs_touching_var(exprs, var)
                    values[var] = value.expr
                    if value.expr is not None:
                        exprs[value.expr] = var
                    continue
                if op == "LOAD_F":
                    out.append(ins)
                    var = str(ins.args[0])
                    self._kill_exprs_touching_var(exprs, var)
                    values.pop(var, None)
                    continue
                out.append(ins)
                if op == "CALL":
                    argc = int(ins.args[1]) if len(ins.args) > 1 else 0
                    for _ in range(argc):
                        if stack:
                            stack.pop()
                    stack.append(_StackValue(const=_CONST_TOP, expr=("call",)+tuple(ins.args), start=len(out)-1))
                    exprs.clear()
                    continue
                if op == "POP":
                    if stack:
                        stack.pop()
                    continue
                if op == "JUMP_IF_FALSE":
                    if stack:
                        stack.pop()
                    continue
                if op in {"PRINT", "PRINTN", "SAVE_VAL", "LIST_PUT", "WAIT", "SHOW_PREC", "RETURN", "STOP", "HALT"}:
                    stack.clear()
                    if op in self.SIDE_EFFECT_BARRIERS:
                        exprs.clear()
                    continue
            child_outputs: List[IRInstruction] = []
            for child in dom.tree_children.get(label, []):
                child_outputs.extend(walk(child, exprs, values))
            return out + child_outputs

        rewritten = walk(cfg.entry_label, {}, {})
        return rewritten, gvn_rewrites, loop_rewrites

    def _expr_safe_to_reuse(self, expr: Any, write_blocks_by_var: Dict[str, Set[str]], dom: DominatorTree, current_label: str) -> bool:
        touched = self._vars_in_expr(expr)
        for var in touched:
            if current_label in write_blocks_by_var.get(var, set()):
                return False
            for block in write_blocks_by_var.get(var, set()):
                if block != current_label and current_label in dom.natural_loops and block in dom.natural_loops.get(current_label, []):
                    return False
        return True

    def _vars_in_expr(self, expr: Any) -> Set[str]:
        out: Set[str] = set()
        if isinstance(expr, tuple):
            if len(expr) >= 2 and expr[0] == "var":
                out.add(str(expr[1]))
            for item in expr[1:]:
                out.update(self._vars_in_expr(item))
        return out

    def _kill_exprs_touching_var(self, exprs: Dict[Any, str], var_name: str) -> None:
        stale = [expr for expr in exprs if var_name in self._vars_in_expr(expr) or expr == ("var", var_name)]
        for expr in stale:
            exprs.pop(expr, None)

    def _invalidate_var_aliases(self, expr_to_var: Dict[Any, str], value_of_var: Dict[str, Any], var_name: str) -> None:
        stale = [expr for expr, name in expr_to_var.items() if name == var_name and value_of_var.get(var_name) != expr]
        for expr in stale:
            expr_to_var.pop(expr, None)
        expr = value_of_var.get(var_name)
        if expr is not None:
            expr_to_var[expr] = var_name

    # ---------------- SCCP / LICM ----------------

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

    # ---------------- cleanup ----------------

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

    # ---------------- helpers ----------------

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

    def _const_expr(self, value: Any) -> tuple[str, Any]:
        return ("const", value)

    def _expr_for_binary(self, op: str, left: Any, right: Any, ins: IRInstruction) -> Any:
        if op == "COMPARE":
            return (op, str(ins.args[0]), left, right)
        if op in {"ADD", "MUL", "BOOL_AND", "BOOL_OR"}:
            a, b = (left, right) if repr(left) <= repr(right) else (right, left)
            return (op, a, b)
        return (op, left, right)

    def _eval_binary(self, left: Any, right: Any, ins: IRInstruction) -> tuple[bool, Any]:
        try:
            if ins.op == "ADD":
                return True, left + right
            if ins.op == "SUB":
                return True, left - right
            if ins.op == "MUL":
                return True, left * right
            if ins.op == "DIV":
                return (False, None) if right == 0 else (True, left / right)
            if ins.op == "MOD":
                return (False, None) if right == 0 else (True, left % right)
            if ins.op == "POW_OP":
                return True, left ** right
            if ins.op == "BOOL_AND":
                return True, bool(left) and bool(right)
            if ins.op == "BOOL_OR":
                return True, bool(left) or bool(right)
            if ins.op == "COMPARE":
                op = str(ins.args[0])
                table = {
                    "==": left == right,
                    "!=": left != right,
                    "<": left < right,
                    "<=": left <= right,
                    ">": left > right,
                    ">=": left >= right,
                }
                if op in table:
                    return True, table[op]
        except Exception:
            return False, None
        return False, None

    def _eval_unary(self, value: Any, ins: IRInstruction) -> tuple[bool, Any]:
        try:
            if ins.op == "BOOL_NOT":
                return True, not bool(value)
        except Exception:
            return False, None
        return False, None
