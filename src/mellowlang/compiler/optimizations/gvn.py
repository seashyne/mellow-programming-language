"""Global value numbering across dominator regions."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Set

from ...ir import IRInstruction

from .ir_data import ControlFlowGraph, DominatorTree, _CONST_TOP, _StackValue


class GlobalValueNumberingMixin:
    """Global value numbering across dominator regions."""

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
                if op == "SYSCALL":
                    argc = int(ins.args[0]) if ins.args else 0
                    for _ in range(argc + 1):
                        if stack:
                            stack.pop()
                    stack.append(_StackValue(const=_CONST_TOP, expr=("syscall",)+tuple(ins.args), start=len(out)-1))
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
