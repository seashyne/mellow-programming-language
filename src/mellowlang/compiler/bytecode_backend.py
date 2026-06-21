from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from ..constants import Op
from ..ir import IRInstruction, IRProgram


@dataclass(frozen=True)
class BytecodeBundle:
    bytecode: List[tuple]
    line_map: List[int]
    col_map: List[int]
    end_line_map: List[int]
    end_col_map: List[int]
    span_map: List[dict]
    func_table: Dict[str, Dict[str, Any]]
    event_table: Dict[str, Dict[str, Any]]


class BytecodeBackend:
    OP_MAP = {
        "HALT": lambda ins: (Op.HALT,),
        "PUSH": lambda ins: (Op.PUSH, ins.args[0]),
        "STORE": lambda ins: (Op.STORE, ins.args[0]),
        "STORE_KEEP": lambda ins: (Op.STORE_KEEP, ins.args[0]),
        "STORE_AUTO": lambda ins: (Op.STORE_AUTO, ins.args[0]),
        "LOAD": lambda ins: (Op.LOAD, ins.args[0]),
        "ADD": lambda ins: (Op.ADD,),
        "SUB": lambda ins: (Op.SUB,),
        "MUL": lambda ins: (Op.MUL,),
        "DIV": lambda ins: (Op.DIV,),
        "COMPARE": lambda ins: (Op.COMPARE, ins.args[0]),
        "PRINT": lambda ins: (Op.PRINT,),
        "PRINTN": lambda ins: (Op.PRINTN, ins.args[0]),
        "CALL": lambda ins: (Op.CALL, ins.args[0], ins.args[1]),
        "RETURN": lambda ins: (Op.RETURN,),
        "ARG": lambda ins: (Op.ARG, ins.args[0]),
        "SHOW_PREC": lambda ins: (Op.SHOW_PREC,),
        "STOP": lambda ins: (Op.STOP,),
        "WAIT": lambda ins: (Op.WAIT,),
        "SAVE_VAL": lambda ins: (Op.SAVE_VAL,),
        "LOAD_F": lambda ins: (Op.LOAD_F, ins.args[0]),
        "LIST_PUT": lambda ins: (Op.LIST_PUT,),
        "BOOL_AND": lambda ins: (Op.BOOL_AND,),
        "BOOL_OR": lambda ins: (Op.BOOL_OR,),
        "BOOL_NOT": lambda ins: (Op.BOOL_NOT,),
        "SYSCALL": lambda ins: (Op.SYSCALL, ins.args[0]),
        "POP": lambda ins: (Op.POP,),
        "GETITEM": lambda ins: (Op.GETITEM,),
        "LEN": lambda ins: (Op.LEN,),
        "BUILD_LIST": lambda ins: (Op.BUILD_LIST, ins.args[0]),
        "BUILD_MAP": lambda ins: (Op.BUILD_MAP, ins.args[0]),
        "RANDOM": lambda ins: (Op.RANDOM,),
        "SEED": lambda ins: (Op.SEED,),
        "GLOBAL_SEED": lambda ins: (Op.GLOBAL_SEED,),
        "MOD": lambda ins: (Op.MOD,),
        "POW_OP": lambda ins: (Op.POW_OP,),
        "IMPORT": lambda ins: (Op.IMPORT, ins.args[0], ins.args[1]),
    }

    def lower(self, ir: IRProgram) -> BytecodeBundle:
        labels: Dict[str, int] = {}
        pc = 0
        for ins in ir.instructions:
            if ins.op == "LABEL":
                labels[str(ins.args[0])] = pc
            else:
                pc += 1

        bytecode: List[tuple] = []
        line_map: List[int] = []
        col_map: List[int] = []
        end_line_map: List[int] = []
        end_col_map: List[int] = []
        span_map: List[dict] = []
        emitted_pc_to_ir_index: Dict[int, int] = {}
        pc = 0
        for idx, ins in enumerate(ir.instructions):
            if ins.op == "LABEL":
                continue
            emitted_pc_to_ir_index[pc] = idx
            bytecode.append(self._emit_instruction(ins, labels))
            start_line = int(ins.line or 0)
            start_col = int(ins.col or 1)
            rendered = self._render_instruction_hint(ins)
            end_line = start_line
            end_col = start_col + max(1, len(rendered) - 1)
            line_map.append(start_line)
            col_map.append(start_col)
            end_line_map.append(end_line)
            end_col_map.append(end_col)
            span_map.append({
                "start_line": start_line,
                "start_col": start_col,
                "end_line": end_line,
                "end_col": end_col,
                "hint": rendered,
                "ir_index": idx,
            })
            pc += 1

        func_table = {
            name: {
                "address": labels[meta.entry_label],
                "param_count": len(meta.params),
                "params": list(meta.params),
                "kind": meta.kind,
            }
            for name, meta in ir.functions.items()
        }
        event_table = {
            name: {
                "address": labels[meta.entry_label],
                "param_count": len(meta.params),
                "params": list(meta.params),
                "kind": meta.kind,
            }
            for name, meta in ir.events.items()
        }
        return BytecodeBundle(
            bytecode=bytecode,
            line_map=line_map,
            col_map=col_map,
            func_table=func_table,
            event_table=event_table,
            end_line_map=end_line_map,
            end_col_map=end_col_map,
            span_map=span_map,
        )

    def _emit_instruction(self, ins: IRInstruction, labels: Dict[str, int]) -> tuple:
        if ins.op == "JUMP":
            return (Op.JUMP, labels[str(ins.args[0])])
        if ins.op == "JUMP_IF_FALSE":
            return (Op.JIF, labels[str(ins.args[0])])
        emitter = self.OP_MAP.get(ins.op)
        if emitter is None:
            raise ValueError(f"Unsupported IR opcode for bytecode lowering: {ins.op}")
        return emitter(ins)


    def _render_instruction_hint(self, ins: IRInstruction) -> str:
        parts = [ins.op]
        if ins.args:
            parts.extend(repr(a) for a in ins.args)
        return " ".join(parts)
