"""Per-block dataflow environment and its transfer functions."""

from __future__ import annotations

from typing import Any, Dict, List, Set

from ...ir import IRInstruction

from .ir_data import BasicBlock, _CONST_TOP


class DataflowMixin:
    """Per-block dataflow environment and its transfer functions."""

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
