"""One statement node in, one run of IR instructions out."""

from __future__ import annotations

from ...ast import (
    AssignStmt,
    BreakStmt,
    ContinueStmt,
    DoBlock,
    ExprStmt,
    GetModuleStmt,
    IfGroup,
    ImportStmt,
    KeepMultiStmt,
    KeepStmt,
    LoadStmt,
    LoopCount,
    LoopForEach,
    LoopForRange,
    LoopWhile,
    OnDef,
    PrecisionStmt,
    PutStmt,
    ReturnStmt,
    SaveStmt,
    ShowStmt,
    SkillDef,
    SkillDefV2,
    Stmt,
    StopStmt,
    WaitStmt,
)
from ...ir import IRFunction

from .driver import _LoopCtx
from .errors import UnsupportedLoweringError
from .syscalls import _module_syscall


class StatementMixin:
    def _stmt(self, stmt: Stmt):
        line, col = self.pos(stmt)
        self._current_position = (line, col)
        if isinstance(stmt, KeepStmt):
            self._expr(stmt.expr)
            self.emit("STORE_KEEP", stmt.name, line=line, col=col)
        elif isinstance(stmt, KeepMultiStmt):
            for expr in stmt.exprs:
                self._expr(expr)
            for name in reversed(stmt.names):
                self.emit("STORE_KEEP", name, line=line, col=col)
        elif isinstance(stmt, AssignStmt):
            for expr in stmt.exprs:
                self._expr(expr)
            for name in reversed(stmt.names):
                self.emit("STORE_AUTO", name, line=line, col=col)
        elif isinstance(stmt, ExprStmt):
            self._expr(stmt.expr)
            self.emit("POP", line=line, col=col)
        elif isinstance(stmt, ShowStmt):
            for expr in stmt.exprs:
                self._expr(expr)
            self.emit("PRINTN" if len(stmt.exprs) > 1 else "PRINT", len(stmt.exprs), line=line, col=col)
        elif isinstance(stmt, PrecisionStmt):
            self._expr(stmt.expr)
            self.emit("SHOW_PREC", line=line, col=col)
        elif isinstance(stmt, StopStmt):
            self.emit("STOP", line=line, col=col)
        elif isinstance(stmt, WaitStmt):
            self._expr(stmt.expr)
            self.emit("WAIT", line=line, col=col)
        elif isinstance(stmt, SaveStmt):
            self._expr(stmt.filename_expr)
            self._expr(stmt.value_expr)
            self.emit("SAVE_VAL", line=line, col=col)
        elif isinstance(stmt, LoadStmt):
            self._expr(stmt.filename_expr)
            self.emit("LOAD_F", stmt.var_name, line=line, col=col)
        elif isinstance(stmt, PutStmt):
            self._expr(stmt.item_expr)
            self.emit("LOAD", stmt.list_name, line=line, col=col)
            self.emit("LIST_PUT", line=line, col=col)
        elif isinstance(stmt, ReturnStmt):
            if stmt.expr is None:
                self.emit("PUSH", None, line=line, col=col)
            else:
                self._expr(stmt.expr)
            self.emit("RETURN", line=line, col=col)
        elif isinstance(stmt, IfGroup):
            end_label = self.new_label("if_end")
            for idx, (cond, body) in enumerate(stmt.branches):
                next_label = self.new_label(f"if_next_{idx}")
                self._expr(cond)
                self.emit("JUMP_IF_FALSE", next_label, line=line, col=col)
                for s in body:
                    self._stmt(s)
                self.emit("JUMP", end_label, line=line, col=col)
                self.emit("LABEL", next_label, line=line, col=col)
            if stmt.else_block:
                for s in stmt.else_block:
                    self._stmt(s)
            self.emit("LABEL", end_label, line=line, col=col)
        elif isinstance(stmt, LoopWhile):
            start = self.new_label("while_start")
            end = self.new_label("while_end")
            self.emit("LABEL", start, line=line, col=col)
            self._expr(stmt.cond)
            self.emit("JUMP_IF_FALSE", end, line=line, col=col)
            self._loop_stack.append(_LoopCtx(break_label=end, continue_label=start))
            for s in stmt.body:
                self._stmt(s)
            self._loop_stack.pop()
            self.emit("JUMP", start, line=line, col=col)
            self.emit("LABEL", end, line=line, col=col)
        elif isinstance(stmt, LoopCount):
            counter = self.new_temp("count")
            start = self.new_label("count_start")
            end = self.new_label("count_end")
            self.emit("PUSH", 0, line=line, col=col)
            self.emit("STORE", counter, line=line, col=col)
            self.emit("LABEL", start, line=line, col=col)
            self.emit("LOAD", counter, line=line, col=col)
            self._expr(stmt.limit)
            self.emit("COMPARE", "<", line=line, col=col)
            self.emit("JUMP_IF_FALSE", end, line=line, col=col)
            self._loop_stack.append(_LoopCtx(break_label=end, continue_label=start))
            for s in stmt.body:
                self._stmt(s)
            self._loop_stack.pop()
            self.emit("LOAD", counter, line=line, col=col)
            self.emit("PUSH", 1, line=line, col=col)
            self.emit("ADD", line=line, col=col)
            self.emit("STORE", counter, line=line, col=col)
            self.emit("JUMP", start, line=line, col=col)
            self.emit("LABEL", end, line=line, col=col)
        elif isinstance(stmt, LoopForRange):
            start_tmp = self.new_temp("range_start")
            end_tmp = self.new_temp("range_end")
            step_tmp = self.new_temp("range_step")
            loop = self.new_label("for_range")
            end = self.new_label("for_range_end")
            self._expr(stmt.start)
            self.emit("STORE", start_tmp, line=line, col=col)
            self._expr(stmt.end)
            self.emit("STORE", end_tmp, line=line, col=col)
            if stmt.step is None:
                self.emit("PUSH", 1, line=line, col=col)
            else:
                self._expr(stmt.step)
            self.emit("STORE", step_tmp, line=line, col=col)
            self.emit("LOAD", start_tmp, line=line, col=col)
            self.emit("STORE", stmt.var_name, line=line, col=col)
            self.emit("LABEL", loop, line=line, col=col)
            self.emit("LOAD", stmt.var_name, line=line, col=col)
            self.emit("LOAD", end_tmp, line=line, col=col)
            self.emit("COMPARE", "<", line=line, col=col)
            self.emit("JUMP_IF_FALSE", end, line=line, col=col)
            self._loop_stack.append(_LoopCtx(break_label=end, continue_label=loop))
            for s in stmt.body:
                self._stmt(s)
            self._loop_stack.pop()
            self.emit("LOAD", stmt.var_name, line=line, col=col)
            self.emit("LOAD", step_tmp, line=line, col=col)
            self.emit("ADD", line=line, col=col)
            self.emit("STORE", stmt.var_name, line=line, col=col)
            self.emit("JUMP", loop, line=line, col=col)
            self.emit("LABEL", end, line=line, col=col)
        elif isinstance(stmt, LoopForEach):
            items_tmp = self.new_temp("foreach_items")
            len_tmp = self.new_temp("foreach_len")
            idx_tmp = self.new_temp("foreach_idx")
            loop = self.new_label("foreach")
            end = self.new_label("foreach_end")
            self._expr(stmt.iterable)
            self.emit("STORE", items_tmp, line=line, col=col)
            self.emit("LOAD", items_tmp, line=line, col=col)
            self.emit("LEN", line=line, col=col)
            self.emit("STORE", len_tmp, line=line, col=col)
            self.emit("PUSH", 0, line=line, col=col)
            self.emit("STORE", idx_tmp, line=line, col=col)
            self.emit("LABEL", loop, line=line, col=col)
            self.emit("LOAD", idx_tmp, line=line, col=col)
            self.emit("LOAD", len_tmp, line=line, col=col)
            self.emit("COMPARE", "<", line=line, col=col)
            self.emit("JUMP_IF_FALSE", end, line=line, col=col)
            self.emit("LOAD", items_tmp, line=line, col=col)
            self.emit("LOAD", idx_tmp, line=line, col=col)
            self.emit("GETITEM", line=line, col=col)
            if len(stmt.var_names) == 1:
                self.emit("STORE", stmt.var_names[0], line=line, col=col)
            else:
                raise UnsupportedLoweringError("foreach unpacking is not yet supported in IR pipeline")
            self._loop_stack.append(_LoopCtx(break_label=end, continue_label=loop))
            for s in stmt.body:
                self._stmt(s)
            self._loop_stack.pop()
            self.emit("LOAD", idx_tmp, line=line, col=col)
            self.emit("PUSH", 1, line=line, col=col)
            self.emit("ADD", line=line, col=col)
            self.emit("STORE", idx_tmp, line=line, col=col)
            self.emit("JUMP", loop, line=line, col=col)
            self.emit("LABEL", end, line=line, col=col)
        elif isinstance(stmt, DoBlock):
            for s in stmt.body:
                self._stmt(s)
        elif isinstance(stmt, BreakStmt):
            if not self._loop_stack:
                raise UnsupportedLoweringError("break used outside loop")
            self.emit("JUMP", self._loop_stack[-1].break_label, line=line, col=col)
        elif isinstance(stmt, ContinueStmt):
            if not self._loop_stack:
                raise UnsupportedLoweringError("continue used outside loop")
            self.emit("JUMP", self._loop_stack[-1].continue_label, line=line, col=col)
        elif isinstance(stmt, SkillDef):
            skip = self.new_label(f"after_skill_{stmt.name}")
            entry = self.new_label(f"skill_{stmt.name}")
            self.emit("JUMP", skip, line=line, col=col)
            self.emit("LABEL", entry, line=line, col=col)
            for param in stmt.params:
                self.emit("ARG", param, line=line, col=col)
            for s in stmt.body:
                self._stmt(s)
            self.emit("PUSH", None, line=line, col=col)
            self.emit("RETURN", line=line, col=col)
            self.emit("LABEL", skip, line=line, col=col)
            self.functions[stmt.name] = IRFunction(name=stmt.name, entry_label=entry, params=list(stmt.params), kind="skill")
        elif isinstance(stmt, SkillDefV2):
            raise UnsupportedLoweringError("SkillDefV2/default args are not yet lowered in IR pipeline")
        elif isinstance(stmt, OnDef):
            skip = self.new_label(f"after_on_{stmt.event}")
            entry = self.new_label(f"on_{stmt.event}")
            self.emit("JUMP", skip, line=line, col=col)
            self.emit("LABEL", entry, line=line, col=col)
            for param in stmt.params:
                self.emit("ARG", param, line=line, col=col)
            for s in stmt.body:
                self._stmt(s)
            self.emit("PUSH", None, line=line, col=col)
            self.emit("RETURN", line=line, col=col)
            self.emit("LABEL", skip, line=line, col=col)
            self.events[stmt.event] = IRFunction(name=stmt.event, entry_label=entry, params=list(stmt.params), kind="event")
        elif isinstance(stmt, GetModuleStmt):
            self.emit("PUSH", _module_syscall(stmt.module, stmt.function), line=line, col=col)
            for arg in stmt.args:
                self._expr(arg)
            self.emit("SYSCALL", len(stmt.args), line=line, col=col)
            if stmt.var_name:
                self.emit("STORE_AUTO", stmt.var_name, line=line, col=col)
            else:
                self.emit("POP", line=line, col=col)
        elif isinstance(stmt, ImportStmt):
            self.emit("IMPORT", stmt.path, stmt.alias, line=line, col=col)
        else:
            raise UnsupportedLoweringError(f"AST node not supported by IR pipeline: {type(stmt).__name__}")
