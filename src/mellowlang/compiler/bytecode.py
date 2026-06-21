
# frinds/compiler.py (v2.2)
from __future__ import annotations
from typing import List, Dict, Any, Tuple
from ..constants import Op
from ..error_core import MellowLangRuntimeError
from ..ast import *
from ..parser import parse_program, ParseError

class Compiler:
    """
    v2.2: Parser/AST based compiler.
    - Parses full program into AST (no regex parsing of expressions)
    - Compiles AST -> bytecode for MellowLangVM
    """
    def __init__(self):
        self.bytecode: List[tuple] = []
        self.line_map: List[int] = []  # pc -> source line
        self.col_map: List[int] = []  # pc -> source column (1-indexed)
        self._cur_line = 0
        self._cur_col = 1
        # name -> {address:int, param_count:int}
        self.functions: Dict[str, Dict[str, Any]] = {}
        # event_name -> {address:int, param_count:int}
        self.events: Dict[str, Dict[str, Any]] = {}
        self._tmp_id = 0
        self._loop_stack: List[dict] = []

    def emit(self, instr: tuple):
        self.bytecode.append(instr)
        self.line_map.append(int(self._cur_line or 0))
        self.col_map.append(int(self._cur_col or 1))

    def compile(self, lines: List[str], *, filename: str | None = None) -> List[tuple]:
        prog = parse_program(lines, filename=filename)
        self.bytecode = []
        self.line_map = []
        self.col_map = []
        self.functions = {}
        self.events = {}
        self._cur_line = 0
        self._cur_col = 1
        self._loop_stack = []
        self._compile_program(prog)
        self.emit((Op.HALT,))
        return self.bytecode

    # ---------- Program/Statement compilation ----------

    def _compile_program(self, prog: Program):
        # 1) Emit placeholders to jump over skill bodies declared at top-level.
        # We compile in-order: statements. For each SkillDef, we jump over its body.
        for stmt in prog.body:
            self._compile_stmt(stmt)

    def _compile_stmt(self, s: Stmt):
        self._cur_line = int(getattr(s, "_line", self._cur_line) or 0)
        self._cur_col  = int(getattr(s, "_col", self._cur_col) or 1)
        if isinstance(s, KeepStmt):
            self._compile_expr(s.expr)
            self.emit((Op.STORE_KEEP, s.name))
        elif isinstance(s, KeepMultiStmt):
            # Parallel multi-assign: evaluate all RHS first, then assign.
            # This enables safe swaps: keep a,b = b,a
            if len(s.names) != len(s.exprs):
                raise RuntimeError("KeepMultiStmt: names/exprs length mismatch")
            for ex in s.exprs:
                self._compile_expr(ex)
            for name in reversed(s.names):
                self.emit((Op.STORE_KEEP, name))
        elif isinstance(s, AssignStmt):
            # Parallel multi-assign for normal variables.
            if len(s.names) != len(s.exprs):
                raise RuntimeError("AssignStmt: names/exprs length mismatch")
            for ex in s.exprs:
                self._compile_expr(ex)
            for name in reversed(s.names):
                self.emit((Op.STORE_AUTO, name))
        elif isinstance(s, ExprStmt):
            self._compile_expr(s.expr)
            self.emit((Op.POP,))
        elif isinstance(s, ShowStmt):
            # v1.2.5: multi-value print/show
            for ex in s.exprs:
                self._compile_expr(ex)
            if len(s.exprs) <= 1:
                self.emit((Op.PRINT,))
            else:
                self.emit((Op.PRINTN, len(s.exprs)))
        elif isinstance(s, PrecisionStmt):
            self._compile_expr(s.expr)
            self.emit((Op.SHOW_PREC,))
        elif isinstance(s, StopStmt):
            self.emit((Op.STOP,))
        elif isinstance(s, WaitStmt):
            self._compile_expr(s.expr)
            self.emit((Op.WAIT,))
        elif isinstance(s, PutStmt):
            # push item then load list then append
            self._compile_expr(s.item_expr)
            self.emit((Op.LOAD, s.list_name))
            self.emit((Op.LIST_PUT,))
        elif isinstance(s, SaveStmt):
            # save <value_expr> into <filename_expr>
            self._compile_expr(s.filename_expr)
            self._compile_expr(s.value_expr)
            self.emit((Op.SAVE_VAL,))  # store top value into file name below
        elif isinstance(s, LoadStmt):
            self._compile_expr(s.filename_expr)
            self.emit((Op.LOAD_F, s.var_name))
        elif isinstance(s, ReturnStmt):
            if s.expr is None:
                self.emit((Op.PUSH, None))
            else:
                self._compile_expr(s.expr)
            self.emit((Op.RETURN,))
        elif isinstance(s, BreakStmt):
            if not self._loop_stack:
                ln = getattr(s, "_line", None)
                col = getattr(s, "_col", None)
                raise MellowLangRuntimeError("SYNTAX", "break can only be used inside a loop", ln, col=col)
            ctx = self._loop_stack[-1]
            ctx["break_jumps"].append(len(self.bytecode))
            self.emit((Op.JUMP, None))
        elif isinstance(s, ContinueStmt):
            if not self._loop_stack:
                ln = getattr(s, "_line", None)
                col = getattr(s, "_col", None)
                raise MellowLangRuntimeError("SYNTAX", "continue can only be used inside a loop", ln, col=col)
            ctx = self._loop_stack[-1]
            ctx["continue_jumps"].append(len(self.bytecode))
            self.emit((Op.JUMP, None))
        elif isinstance(s, TryStmt):
            self._compile_try(s)
        elif isinstance(s, GetModuleStmt):
            self._compile_get_module(s)
        elif isinstance(s, SkillDef):
            # Jump over function body in main execution
            jmp_idx = len(self.bytecode)
            self.emit((Op.JUMP, None))

            start_addr = len(self.bytecode)
            self.functions[s.name] = {
                "address": start_addr,
                "param_count": len(s.params),
                "params": s.params,
                "defaults": {k: None for k in getattr(s, 'defaults', {})},  # placeholder
            }

            # Move arguments from stack to locals (reverse)
            for p in reversed(s.params):
                self.emit((Op.ARG, p))

            # v1.4.9: apply default values for missing (None) args
            defaults = getattr(s, 'defaults', {})
            for p in s.params:
                if p in defaults:
                    # if p is None, assign default: LOAD p; PUSH None; COMPARE ==; JIF skip; PUSH default; STORE p
                    self.emit((Op.LOAD, p))
                    self.emit((Op.PUSH, None))
                    self.emit((Op.COMPARE, "=="))
                    jif_default = len(self.bytecode)
                    self.emit((Op.JIF, None))  # if NOT None, skip
                    self._compile_expr(defaults[p])
                    self.emit((Op.STORE, p))
                    self.bytecode[jif_default] = (Op.JIF, len(self.bytecode))

            for st in s.body:
                self._compile_stmt(st)

            # implicit return none
            self.emit((Op.PUSH, None))
            self.emit((Op.RETURN,))

            # patch jump
            self.bytecode[jmp_idx] = (Op.JUMP, len(self.bytecode))

        elif isinstance(s, ImportStmt):
            # v1.4.9: import "path.mellow" as alias → IMPORT opcode
            self.emit((Op.IMPORT, s.path, s.alias))

        elif isinstance(s, OnDef):
            # Jump over event handler body in main execution
            jmp_idx = len(self.bytecode)
            self.emit((Op.JUMP, None))

            start_addr = len(self.bytecode)
            self.events[s.event] = {"address": start_addr, "param_count": len(s.params), "params": s.params}

            for p in reversed(s.params):
                self.emit((Op.ARG, p))

            for st in s.body:
                self._compile_stmt(st)

            # implicit return none
            self.emit((Op.PUSH, None))
            self.emit((Op.RETURN,))

            self.bytecode[jmp_idx] = (Op.JUMP, len(self.bytecode))
        elif isinstance(s, IfGroup):
            self._compile_ifgroup(s)
        elif isinstance(s, LoopWhile):
            self._compile_loop_while(s)
        elif isinstance(s, LoopForEach):
            self._compile_loop_foreach(s)
        elif isinstance(s, LoopForMap):
            self._compile_loop_formap(s)
        elif isinstance(s, DoBlock):
            for st in s.body:
                self._compile_stmt(st)
        elif isinstance(s, LoopForRange):
            self._compile_loop_forrange(s)
        elif isinstance(s, RepeatUntil):
            self._compile_repeat_until(s)
        elif isinstance(s, LoopCount):
            self._compile_loop_count(s)
        else:
            raise RuntimeError(f"Unknown stmt: {s}")

    def _compile_ifgroup(self, ig: IfGroup):
        """Compile check/also/else (and if/elif alias)."""
        end_jumps: List[int] = []
        next_patch: List[int] = []  # list of JIF indices to patch to next branch

        for (cond, block) in ig.branches:
            # patch previous branch-false jumps to here
            cur_addr = len(self.bytecode)
            for jif_idx in next_patch:
                self.bytecode[jif_idx] = (Op.JIF, cur_addr)
            next_patch = []

            self._compile_expr(cond)
            jif_idx = len(self.bytecode)
            self.emit((Op.JIF, None))  # jump to next branch (patched later)
            next_patch.append(jif_idx)

            for st in block:
                self._compile_stmt(st)

            end_jumps.append(len(self.bytecode))
            self.emit((Op.JUMP, None))

        # else block entry
        else_addr = len(self.bytecode)
        for jif_idx in next_patch:
            self.bytecode[jif_idx] = (Op.JIF, else_addr)

        if ig.else_block is not None:
            for st in ig.else_block:
                self._compile_stmt(st)

        end_addr = len(self.bytecode)
        for j in end_jumps:
            self.bytecode[j] = (Op.JUMP, end_addr)

    def _compile_loop_while(self, lp: LoopWhile):
        loop_start = len(self.bytecode)
        ctx = {"break_jumps": [], "continue_jumps": []}
        self._loop_stack.append(ctx)
        self._compile_expr(lp.cond)
        jif_idx = len(self.bytecode)
        self.emit((Op.JIF, None))
        for st in lp.body:
            self._compile_stmt(st)
        self.emit((Op.JUMP, loop_start))
        end_addr = len(self.bytecode)
        self.bytecode[jif_idx] = (Op.JIF, end_addr)

        # patch break/continue
        for j in ctx["continue_jumps"]:
            self.bytecode[j] = (Op.JUMP, loop_start)
        for j in ctx["break_jumps"]:
            self.bytecode[j] = (Op.JUMP, end_addr)
        self._loop_stack.pop()


    
    def _compile_repeat_until(self, rp: RepeatUntil):
        loop_start = len(self.bytecode)
        ctx = {"break_jumps": [], "continue_jumps": []}
        self._loop_stack.append(ctx)

        for st in rp.body:
            self._compile_stmt(st)

        # until condition (stop when cond is true)
        self._compile_expr(rp.cond)
        jif_idx = len(self.bytecode)
        # if condition is false -> jump back to start
        self.emit((Op.JIF, loop_start))

        end_addr = len(self.bytecode)
        # patch break/continue
        for j in ctx["continue_jumps"]:
            self.bytecode[j] = (Op.JUMP, loop_start)
        for j in ctx["break_jumps"]:
            self.bytecode[j] = (Op.JUMP, end_addr)
        self._loop_stack.pop()

    def _compile_loop_count(self, lp: LoopCount):
        # loop count < limit:
        idx_var = self._new_tmp("__count")
        limit_var = self._new_tmp("__limit")

        # idx=0
        self.emit((Op.PUSH, 0))
        self.emit((Op.STORE, idx_var))
        # limit = expr
        self._compile_expr(lp.limit)
        self.emit((Op.STORE, limit_var))

        ctx = {"break_jumps": [], "continue_jumps": []}
        self._loop_stack.append(ctx)

        loop_start = len(self.bytecode)

        # condition: idx < limit
        self.emit((Op.LOAD, idx_var))
        self.emit((Op.LOAD, limit_var))
        self.emit((Op.COMPARE, "<"))
        jif_idx = len(self.bytecode)
        self.emit((Op.JIF, None))

        # expose 'count' to user each iteration
        self.emit((Op.LOAD, idx_var))
        self.emit((Op.STORE, "count"))

        for st in lp.body:
            self._compile_stmt(st)

        incr_addr = len(self.bytecode)
        self.emit((Op.LOAD, idx_var))
        self.emit((Op.PUSH, 1))
        self.emit((Op.ADD,))
        self.emit((Op.STORE, idx_var))

        self.emit((Op.JUMP, loop_start))
        end_addr = len(self.bytecode)
        self.bytecode[jif_idx] = (Op.JIF, end_addr)

        for j in ctx["continue_jumps"]:
            self.bytecode[j] = (Op.JUMP, incr_addr)
        for j in ctx["break_jumps"]:
            self.bytecode[j] = (Op.JUMP, end_addr)
        self._loop_stack.pop()


    def _compile_loop_forrange(self, lp: LoopForRange):
        # numeric for: for i = start, end, step (inclusive end, Lua-like)
        i_var = lp.var_name
        start_tmp = self._new_tmp("__for_start")
        end_tmp = self._new_tmp("__for_end")
        step_tmp = self._new_tmp("__for_step")

        # evaluate start/end once
        self._compile_expr(lp.start)
        self.emit((Op.STORE, start_tmp))
        self._compile_expr(lp.end)
        self.emit((Op.STORE, end_tmp))

        # step default: if omitted -> +1 when start<=end else -1
        if lp.step is None:
            cond_tmp = self._new_tmp("__for_cond")
            self.emit((Op.LOAD, start_tmp))
            self.emit((Op.LOAD, end_tmp))
            self.emit((Op.COMPARE, "<="))
            self.emit((Op.STORE, cond_tmp))

            # if not cond -> step = -1 else step = 1
            self.emit((Op.LOAD, cond_tmp))
            jif_idx = len(self.bytecode)
            self.emit((Op.JIF, None))  # false => jump to set -1
            self.emit((Op.PUSH, 1))
            self.emit((Op.STORE, step_tmp))
            jmp_end = len(self.bytecode)
            self.emit((Op.JUMP, None))
            neg_addr = len(self.bytecode)
            self.bytecode[jif_idx] = (Op.JIF, neg_addr)
            self.emit((Op.PUSH, -1))
            self.emit((Op.STORE, step_tmp))
            end_addr = len(self.bytecode)
            self.bytecode[jmp_end] = (Op.JUMP, end_addr)
        else:
            self._compile_expr(lp.step)
            self.emit((Op.STORE, step_tmp))

        # i = start
        self.emit((Op.LOAD, start_tmp))
        self.emit((Op.STORE, i_var))

        ctx = {"break_jumps": [], "continue_jumps": []}
        self._loop_stack.append(ctx)

        loop_start = len(self.bytecode)

        # if step > 0: i <= end else: i >= end
        self.emit((Op.LOAD, step_tmp))
        self.emit((Op.PUSH, 0))
        self.emit((Op.COMPARE, ">"))
        sign_jif = len(self.bytecode)
        self.emit((Op.JIF, None))  # false => negative branch

        # positive branch
        self.emit((Op.LOAD, i_var))
        self.emit((Op.LOAD, end_tmp))
        self.emit((Op.COMPARE, "<="))
        cond_jif_pos = len(self.bytecode)
        self.emit((Op.JIF, None))
        jmp_to_body = len(self.bytecode)
        self.emit((Op.JUMP, None))

        # negative branch
        neg_branch = len(self.bytecode)
        self.bytecode[sign_jif] = (Op.JIF, neg_branch)

        self.emit((Op.LOAD, i_var))
        self.emit((Op.LOAD, end_tmp))
        self.emit((Op.COMPARE, ">="))
        cond_jif_neg = len(self.bytecode)
        self.emit((Op.JIF, None))
        jmp_to_body2 = len(self.bytecode)
        self.emit((Op.JUMP, None))

        # body entry
        body_addr = len(self.bytecode)
        self.bytecode[jmp_to_body] = (Op.JUMP, body_addr)
        self.bytecode[jmp_to_body2] = (Op.JUMP, body_addr)

        for st in lp.body:
            self._compile_stmt(st)

        incr_addr = len(self.bytecode)

        # i = i + step
        self.emit((Op.LOAD, i_var))
        self.emit((Op.LOAD, step_tmp))
        self.emit((Op.ADD,))
        self.emit((Op.STORE, i_var))

        self.emit((Op.JUMP, loop_start))

        end_loop = len(self.bytecode)
        self.bytecode[cond_jif_pos] = (Op.JIF, end_loop)
        self.bytecode[cond_jif_neg] = (Op.JIF, end_loop)

        for j in ctx["continue_jumps"]:
            self.bytecode[j] = (Op.JUMP, incr_addr)
        for j in ctx["break_jumps"]:
            self.bytecode[j] = (Op.JUMP, end_loop)
        self._loop_stack.pop()

    def _new_tmp(self, prefix="__tmp") -> str:
        self._tmp_id += 1
        return f"{prefix}{self._tmp_id}"

    def _compile_loop_foreach(self, lp: LoopForEach):
        # foreach var in iterable (v1.4.9: supports tuple unpacking for multi-var)
        iter_var = self._new_tmp("__iter")
        idx_var = self._new_tmp("__idx")
        item_var = self._new_tmp("__item")

        # iter = iterable
        self._compile_expr(lp.iterable)
        self.emit((Op.STORE, iter_var))
        # idx = 0
        self.emit((Op.PUSH, 0))
        self.emit((Op.STORE, idx_var))

        ctx = {"break_jumps": [], "continue_jumps": []}
        self._loop_stack.append(ctx)

        loop_start = len(self.bytecode)

        # condition: idx < len(iter)
        self.emit((Op.LOAD, idx_var))
        self.emit((Op.LOAD, iter_var))
        self.emit((Op.LEN,))
        self.emit((Op.COMPARE, "<"))
        jif_idx = len(self.bytecode)
        self.emit((Op.JIF, None))

        # bind loop var(s) = iter[idx]
        self.emit((Op.LOAD, iter_var))
        self.emit((Op.LOAD, idx_var))
        self.emit((Op.GETITEM,))

        var_names = getattr(lp, 'var_names', [lp.var_name])
        if len(var_names) > 1:
            # Tuple unpacking: item = iter[idx]; var0 = item[0]; var1 = item[1]; ...
            self.emit((Op.STORE, item_var))
            for vi, vname in enumerate(var_names):
                self.emit((Op.LOAD, item_var))
                self.emit((Op.PUSH, vi))
                self.emit((Op.GETITEM,))
                self.emit((Op.STORE, vname))
        else:
            self.emit((Op.STORE, var_names[0]))

        for st in lp.body:
            self._compile_stmt(st)

        incr_addr = len(self.bytecode)

        # idx = idx + 1
        self.emit((Op.LOAD, idx_var))
        self.emit((Op.PUSH, 1))
        self.emit((Op.ADD,))
        self.emit((Op.STORE, idx_var))

        self.emit((Op.JUMP, loop_start))
        end_addr = len(self.bytecode)
        self.bytecode[jif_idx] = (Op.JIF, end_addr)

        for j in ctx["continue_jumps"]:
            self.bytecode[j] = (Op.JUMP, incr_addr)
        for j in ctx["break_jumps"]:
            self.bytecode[j] = (Op.JUMP, end_addr)
        self._loop_stack.pop()


    def _compile_loop_formap(self, lp: LoopForMap):
        """loop k, v in map_expr: ... end

        Compiles by materializing keys list via std.map.keys (no copy of values),
        then v is fetched via std.map.get per key.
        """
        map_var = self._new_tmp("__map")
        keys_var = self._new_tmp("__keys")
        idx_var = self._new_tmp("__idx")

        # map = iterable
        self._compile_expr(lp.iterable)
        self.emit((Op.STORE, map_var))

        # keys = std.map.keys(map)
        self.emit((Op.PUSH, "std.map.keys"))
        self.emit((Op.LOAD, map_var))
        self.emit((Op.SYSCALL, 1))
        self.emit((Op.STORE, keys_var))

        # idx = 0
        self.emit((Op.PUSH, 0))
        self.emit((Op.STORE, idx_var))

        ctx = {"break_jumps": [], "continue_jumps": []}
        self._loop_stack.append(ctx)

        loop_start = len(self.bytecode)

        # condition: idx < len(keys)
        self.emit((Op.LOAD, idx_var))
        self.emit((Op.LOAD, keys_var))
        self.emit((Op.LEN,))
        self.emit((Op.COMPARE, "<"))
        jif_idx = len(self.bytecode)
        self.emit((Op.JIF, None))

        # key = keys[idx]
        self.emit((Op.LOAD, keys_var))
        self.emit((Op.LOAD, idx_var))
        self.emit((Op.GETITEM,))
        self.emit((Op.STORE, lp.key_name))

        # value = std.map.get(map, key)
        self.emit((Op.PUSH, "std.map.get"))
        self.emit((Op.LOAD, map_var))
        self.emit((Op.LOAD, lp.key_name))
        self.emit((Op.SYSCALL, 2))
        self.emit((Op.STORE, lp.value_name))

        for st in lp.body:
            self._compile_stmt(st)

        incr_addr = len(self.bytecode)
        self.emit((Op.LOAD, idx_var))
        self.emit((Op.PUSH, 1))
        self.emit((Op.ADD,))
        self.emit((Op.STORE, idx_var))
        self.emit((Op.JUMP, loop_start))

        end_addr = len(self.bytecode)
        self.bytecode[jif_idx] = (Op.JIF, end_addr)

        for j in ctx["continue_jumps"]:
            self.bytecode[j] = (Op.JUMP, incr_addr)
        for j in ctx["break_jumps"]:
            self.bytecode[j] = (Op.JUMP, end_addr)
        self._loop_stack.pop()

    def _compile_get_module(self, s):
        """v1.4.8: compile get/call module.func(args...) statement.

        Resolves to a SYSCALL using the MODULE_ALLOWLIST:
          get math.sqrt(25)  ->  SYSCALL "std.math.sqrt" with arg 25
          call ai.chat("hi") ->  SYSCALL "std.ai.chat" with arg "hi"

        If s.var_name is non-empty, stores result; otherwise POPs it.
        """
        from ..host.runtime import MODULE_ALLOWLIST
        mod = s.module.lower()
        func = s.function.lower()
        # Lookup syscall name
        syscall_name = None
        if mod in MODULE_ALLOWLIST and func in MODULE_ALLOWLIST[mod]:
            syscall_name = MODULE_ALLOWLIST[mod][func]
        else:
            # Try dot notation: e.g. "ai.steering.seek"
            syscall_name = f"std.{mod}.{func}"

        # Push syscall name + args onto stack, then SYSCALL
        self.emit((Op.PUSH, syscall_name))
        for arg in s.args:
            self._compile_expr(arg)
        self.emit((Op.SYSCALL, len(s.args)))

        if s.var_name:
            self.emit((Op.STORE_AUTO, s.var_name))
        else:
            self.emit((Op.POP,))

    def _compile_try(self, ts: TryStmt):
        """Compile try/catch/finally using Op.TRY/Op.ENDTRY."""
        has_catch = ts.catch_body is not None and ts.catch_name is not None
        has_finally = ts.finally_body is not None

        if not (has_catch or has_finally):
            for st in ts.try_body:
                self._compile_stmt(st)
            return

        try_idx = len(self.bytecode)
        # placeholders: catch_pc, finally_pc, err_name
        self.emit((Op.TRY, None, None, ts.catch_name if has_catch else None))

        for st in ts.try_body:
            self._compile_stmt(st)

        # normal exit from try
        self.emit((Op.ENDTRY,))
        jmp_to_finally_from_try = len(self.bytecode)
        self.emit((Op.JUMP, None))

        catch_pc = len(self.bytecode)
        if has_catch:
            for st in ts.catch_body or []:
                self._compile_stmt(st)
        jmp_to_finally_from_catch = None
        if has_catch:
            jmp_to_finally_from_catch = len(self.bytecode)
            self.emit((Op.JUMP, None))

        finally_pc = len(self.bytecode)
        if has_finally:
            for st in ts.finally_body or []:
                self._compile_stmt(st)

        end_pc = len(self.bytecode)

        # patch TRY placeholders
        if not has_catch:
            catch_pc = finally_pc
        if not has_finally:
            finally_pc = end_pc
        self.bytecode[try_idx] = (Op.TRY, catch_pc, finally_pc, ts.catch_name if has_catch else None)

        # patch jumps to finally
        self.bytecode[jmp_to_finally_from_try] = (Op.JUMP, finally_pc)
        if jmp_to_finally_from_catch is not None:
            self.bytecode[jmp_to_finally_from_catch] = (Op.JUMP, finally_pc)

    # ---------- Expression compilation ----------

    def _compile_expr(self, e: Expr):
        if isinstance(e, GetModuleExpr):
            from ..host.runtime import MODULE_ALLOWLIST
            mod = e.module.lower()
            func = e.function.lower()
            # v1.4.9: No-arg dot access (utils.PI, obj.prop) → LOAD "mod.prop"
            if not e.args:
                # If it's a known stdlib module, still syscall; otherwise LOAD
                if mod not in MODULE_ALLOWLIST:
                    self.emit((Op.LOAD, f"{e.module}.{e.function}"))
                    return
            # Known stdlib syscall
            if mod in MODULE_ALLOWLIST and func in MODULE_ALLOWLIST[mod]:
                syscall_name = MODULE_ALLOWLIST[mod][func]
            else:
                # Could be a user-imported module method with no args → treat as CALL
                syscall_name = f"std.{mod}.{func}"
            self.emit((Op.PUSH, syscall_name))
            for arg in e.args:
                self._compile_expr(arg)
            self.emit((Op.SYSCALL, len(e.args)))
            return
        if isinstance(e, Literal):
            self.emit((Op.PUSH, e.value))
        elif isinstance(e, Var):
            self.emit((Op.LOAD, e.name))
        elif isinstance(e, UnaryOp):
            self._compile_expr(e.expr)
            if e.op == "not":
                self.emit((Op.BOOL_NOT,))
            elif e.op == "-":
                self.emit((Op.PUSH, -1))
                self.emit((Op.MUL,))
            else:
                raise RuntimeError(f"Unknown unary op {e.op}")
        elif isinstance(e, BinaryOp):
            # boolean short-circuit could be added later; v2.2 evaluates both sides
            self._compile_expr(e.left)
            self._compile_expr(e.right)
            op = e.op
            if op == "+": self.emit((Op.ADD,))
            elif op == "-": self.emit((Op.SUB,))
            elif op == "*": self.emit((Op.MUL,))
            elif op == "/": self.emit((Op.DIV,))
            elif op == "%": self.emit((Op.MOD,))
            elif op == "**": self.emit((Op.POW_OP,))
            elif op in ("==","!=",">","<",">=","<="):
                self.emit((Op.COMPARE, op))
            elif op == "and":
                self.emit((Op.BOOL_AND,))
            elif op == "or":
                self.emit((Op.BOOL_OR,))
            else:
                raise RuntimeError(f"Unknown binary op {op}")
        elif isinstance(e, Call):
            # v1.2.3+: support named args in call syntax.
            # IMPORTANT: kwargs are NOT encoded as a plain dict, because that
            # would be ambiguous with a user passing a dict as a normal argument
            # (e.g. save_data("profile", {"hp": 10})).
            #
            # Instead, we append a *tagged* kwargs object as the last argument:
            #   {"$kwargs": {"mode": "w", ...}}
            # The VM recognizes this shape and extracts kwargs safely.
            call_args = list(e.args)
            if getattr(e, "kwargs", None):
                kw_pairs = [(Literal(k), v) for (k, v) in e.kwargs]
                call_args.append(
                    MapLiteral([
                        (Literal("$kwargs"), MapLiteral(kw_pairs)),
                    ])
                )

            # builtins handled by VM: random, ask (if enabled), call(syscall)
            if e.name == "global_seed":
                # global_seed(n)
                if getattr(e, "kwargs", None):
                    raise RuntimeError("global_seed() does not support named args")
                if len(e.args) != 1:
                    raise RuntimeError("global_seed() expects 1 arg")
                self._compile_expr(e.args[0])
                self.emit((Op.GLOBAL_SEED,))
                return
            if e.name == "seed":
                # seed(n)
                if getattr(e, "kwargs", None):
                    raise RuntimeError("seed() does not support named args")
                if len(e.args) != 1:
                    raise RuntimeError("seed() expects 1 arg")
                self._compile_expr(e.args[0])
                self.emit((Op.SEED,))
                return
            if e.name == "rand":
                # rand() -> float [0,1)
                if getattr(e, "kwargs", None):
                    raise RuntimeError("rand() does not support named args")
                if len(e.args) != 0:
                    raise RuntimeError("rand() expects 0 args")
                self.emit((Op.RANDFLOAT,))
                return
            if e.name == "randi":
                # randi(lo, hi) -> int inclusive
                if getattr(e, "kwargs", None):
                    raise RuntimeError("randi() does not support named args")
                if len(e.args) != 2:
                    raise RuntimeError("randi() expects 2 args")
                for a in e.args:
                    self._compile_expr(a)
                self.emit((Op.RANDOM,))
                return
            if e.name == "random":
                # expect 2 args
                for a in call_args:
                    self._compile_expr(a)
                # If user passed kwargs, RANDOM will see a trailing map and ignore it
                # (kept for compatibility). Prefer positional args for random().
                self.emit((Op.RANDOM,))
                return
            if e.name in ("rand_int","random_int"):
                for a in e.args:
                    self._compile_expr(a)
                self.emit((Op.RANDOM,))
                return
            if e.name in ("rand_float","random_float"):
                # no args
                self.emit((Op.RANDFLOAT,))
                return
            if e.name in ("ask","input"):
                if getattr(e, "kwargs", None):
                    raise RuntimeError("ask()/input() does not support named args")
                for a in e.args:
                    self._compile_expr(a)
                self.emit((Op.ASK,))
                return
            if e.name == "call":
                # call("x.y", arg1, arg2, ...)
                if not e.args:
                    self.emit((Op.PUSH, None))
                    return
                # first arg is name
                self._compile_expr(e.args[0])
                # remaining args as list
                for a in call_args[1:]:
                    self._compile_expr(a)
                self.emit((Op.SYSCALL, len(call_args)-1))
                return

            # get("math") / lib("math") -> returns a cached module map (allowlisted)
            if e.name in ("get", "lib"):
                # get(name)
                self.emit((Op.PUSH, "sys.get"))
                for a in e.args:
                    self._compile_expr(a)
                self.emit((Op.SYSCALL, len(e.args)))
                return

            # stdlib helper calls (compile to SYSCALL)
            STDLIB_SYSCALLS = {
                # len — universal length (list, string, map)
                "len": "std.len",
                # list
                "list_push": "std.list.push",
                "list_pop": "std.list.pop",
                "list_len": "std.list.len",
                "list_insert": "std.list.insert",
                "list_remove": "std.list.remove",
                "list_has": "std.list.has",
                "list_sort": "std.list.sort",
                # map
                "map_get": "std.map.get",
                "map_set": "std.map.set",
                "map_keys": "std.map.keys",
                "map_values": "std.map.values",
                "map_has": "std.map.has",
                # string helpers (aliases: str_* and string_*)
                "str_len": "std.string.len",
                "str_lower": "std.string.lower",
                "str_upper": "std.string.upper",
                "str_trim": "std.string.trim",
                "str_replace": "std.string.replace",
                "str_find": "std.string.find",
                "str_split": "std.string.split",
                "str_join": "std.string.join",
                "string_len": "std.string.len",
                "string_lower": "std.string.lower",
                "string_upper": "std.string.upper",
                # json
                "json_encode": "std.json.encode",
                "json_decode": "std.json.decode",
                # money / fixed-point decimal helpers
                "money": "std.money.of",
                "money.of": "std.money.of",
                "money_of": "std.money.of",
                "money.add": "std.money.add",
                "money_add": "std.money.add",
                "money.sub": "std.money.sub",
                "money_sub": "std.money.sub",
                "money.mul": "std.money.mul",
                "money_mul": "std.money.mul",
                "money.div": "std.money.div",
                "money_div": "std.money.div",
                "money.quantize": "std.money.quantize",
                "money_quantize": "std.money.quantize",
                "money.format": "std.money.format",
                "money_format": "std.money.format",
                "money.amount": "std.money.amount",
                "money_amount": "std.money.amount",
                "money.currency": "std.money.currency",
                "money_currency": "std.money.currency",
                "money.eq": "std.money.eq",
                "money_eq": "std.money.eq",
                "money.lt": "std.money.lt",
                "money_lt": "std.money.lt",
                "money.gt": "std.money.gt",
                "money_gt": "std.money.gt",
                # streaming data and parameterized SQLite
                "data.open_jsonl": "std.data.open_jsonl",
                "data_open_jsonl": "std.data.open_jsonl",
                "data.open_csv": "std.data.open_csv",
                "data_open_csv": "std.data.open_csv",
                "data.next": "std.data.next",
                "data_next": "std.data.next",
                "data.close": "std.data.close",
                "data_close": "std.data.close",
                "data.cancel": "std.data.cancel",
                "data_cancel": "std.data.cancel",
                "data.info": "std.data.info",
                "data_info": "std.data.info",
                "data.project": "std.data.project",
                "data_project": "std.data.project",
                "data.where": "std.data.where",
                "data_where": "std.data.where",
                "data.sum": "std.data.sum",
                "data_sum": "std.data.sum",
                "data.sqlite_open": "std.data.sqlite_open",
                "data_sqlite_open": "std.data.sqlite_open",
                "data.sqlite_close": "std.data.sqlite_close",
                "data_sqlite_close": "std.data.sqlite_close",
                "data.sqlite_query": "std.data.sqlite_query",
                "data_sqlite_query": "std.data.sqlite_query",
                "data.sqlite_execute": "std.data.sqlite_execute",
                "data_sqlite_execute": "std.data.sqlite_execute",
                # immutable double-entry ledger helpers
                "ledger.create": "std.ledger.create",
                "ledger_create": "std.ledger.create",
                "ledger.post": "std.ledger.post",
                "ledger_post": "std.ledger.post",
                "ledger.verify": "std.ledger.verify",
                "ledger_verify": "std.ledger.verify",
                "ledger.balance": "std.ledger.balance",
                "ledger_balance": "std.ledger.balance",
                "ledger.entries": "std.ledger.entries",
                "ledger_entries": "std.ledger.entries",
                # range
                "range": "std.range",

                # math
                "abs": "std.math.abs",
                "min": "std.math.min",
                "max": "std.math.max",
                "floor": "std.math.floor",
                "ceil": "std.math.ceil",
                "round": "std.math.round",
                "sqrt": "std.math.sqrt",
                "pow": "std.math.pow",
                "sin": "std.math.sin",
                "cos": "std.math.cos",
                "tan": "std.math.tan",
                "atan2": "std.math.atan2",
                "clamp": "std.math.clamp",
                "lerp": "std.math.lerp",
                # vectors (fast game helpers)
                "vec2": "std.math.vec2",
                "vec3": "std.math.vec3",
                # generic vectors (multi-dim)
                "vec": "std.math.vector",
                "vector": "std.math.vector",
                "vec_add": "std.math.vec_add",
                "vec_sub": "std.math.vec_sub",
                "vec_mul": "std.math.vec_mul",
                "vec_dot": "std.math.vec_dot",
                "vec_len": "std.math.vec_len",
                "vec_norm": "std.math.vec_norm",
                "vec_dist": "std.math.vec_dist",
                "vec_lerp": "std.math.vec_lerp",
                "vec_limit": "std.math.vec_limit",
                "vec_dim": "std.math.vec_dim",
                "vec_axis": "std.math.vec_axis",
                "vec_with": "std.math.vec_with",
                # time
                "time_now": "std.time.now",
                "time_unix": "std.time.unix",
                "time_ms": "std.time.ms",

                # v1.4.6: game top-level (ไม่ต้องใช้ call(g["astar"], ...) อีกต่อไป)
                "astar": "std.game.path.astar",
                "neighbors4": "std.game.grid.neighbors4",
                "neighbors8": "std.game.grid.neighbors8",
                "tween": "std.game.tween.step",
                "ease_linear": "std.game.easing.linear",
                "ease_in_quad": "std.game.easing.in_quad",
                "ease_out_quad": "std.game.easing.out_quad",
                "ease_in_out_quad": "std.game.easing.in_out_quad",
                "ease_in_cubic": "std.game.easing.in_cubic",
                "ease_out_cubic": "std.game.easing.out_cubic",
                "ease_in_out_cubic": "std.game.easing.in_out_cubic",
                "ease_in_back": "std.game.easing.in_back",
                "ease_out_back": "std.game.easing.out_back",
                "ease_out_bounce": "std.game.easing.out_bounce",
                "ease_out_elastic": "std.game.easing.out_elastic",

                # v1.4.6: AI top-level functions
                "ai_decide": "std.ai.decide",
                "ai_utility": "std.ai.utility_choose",
                "ai_bt": "std.ai.bt_tick",
                "ai_fsm": "std.ai.fsm_tick",
                # steering
                "ai_seek": "std.ai.steering.seek",
                "ai_flee": "std.ai.steering.flee",
                "ai_arrive": "std.ai.steering.arrive",
                "ai_wander": "std.ai.steering.wander",
                "ai_patrol": "std.ai.steering.patrol",
                # perception
                "ai_in_range": "std.ai.perception.in_range",
                "ai_in_sight": "std.ai.perception.in_sight",
                "ai_nearest": "std.ai.perception.nearest",
                "ai_filter_range": "std.ai.perception.filter_range",

                # v1.4.7: string helpers
                "str_starts_with": "std.string.starts_with",
                "str_ends_with": "std.string.ends_with",
                "str_contains": "std.string.contains",
                "str_repeat": "std.string.repeat",
                "str_pad_left": "std.string.pad_left",
                "str_pad_right": "std.string.pad_right",
                "str_format": "std.string.format",

                # v1.4.7: math game helpers
                "sign": "std.math.sign",
                "fmod": "std.math.fmod",
                "deg_to_rad": "std.math.deg_to_rad",
                "rad_to_deg": "std.math.rad_to_deg",
                "distance": "std.math.distance",
                "angle_between": "std.math.angle_between",

                # v1.4.7: list functional
                "list_map": "std.list.map",
                "list_filter": "std.list.filter",
                "list_find": "std.list.find",
                "list_slice": "std.list.slice",
                "list_reverse": "std.list.reverse",
                "list_reduce": "std.list.reduce",
                "list_count": "std.list.count",

                # v1.4.7: type checking
                "is_number": "std.type.is_number",
                "is_string": "std.type.is_string",
                "is_bool": "std.type.is_bool",
                "is_list": "std.type.is_list",
                "is_map": "std.type.is_map",
                "is_none": "std.type.is_none",
                "type_of": "std.type.of",

                # v1.4.9: new general functions
                "enumerate": "std.list.enumerate",
                "zip": "std.list.zip",
                "map": "std.list.map_fn",
                "filter": "std.list.filter_fn",
                "reduce": "std.list.reduce",
                "sorted": "std.list.sorted",
                "reversed": "std.list.reversed",
                "sum": "std.math.sum",
                "any": "std.list.any",
                "all": "std.list.all",
                # type conversions
                "int": "std.type.to_int",
                "float": "std.type.to_float",
                "str": "std.type.to_str",
                "bool": "std.type.to_bool",
                "list": "std.type.to_list",
                # string
                "chr": "std.string.chr",
                "ord": "std.string.ord",

                # v1.4.7: assert
                "assert": "std.assert.check",
                "assert_eq": "std.assert.eq",
                "assert_ne": "std.assert.ne",

                # v1.4.7: event
                "emit": "std.event.emit",
            }
            if e.name in STDLIB_SYSCALLS:
                self.emit((Op.PUSH, STDLIB_SYSCALLS[e.name]))
                for a in call_args:
                    self._compile_expr(a)
                self.emit((Op.SYSCALL, len(call_args)))
                return

            # user defined skill call OR first-class function call
            for a in call_args:
                self._compile_expr(a)
            # Check if this is a variable holding a func reference (first-class fn)
            # We emit CALL which the VM will resolve at runtime
            self.emit((Op.CALL, e.name, len(call_args)))
        elif isinstance(e, Index):
            self._compile_expr(e.target)
            self._compile_expr(e.index)
            self.emit((Op.GETITEM,))
        elif isinstance(e, SliceExpr):
            # v1.4.9: stack: target, start_or_None, stop_or_None → SLICE
            self._compile_expr(e.target)
            if e.start is not None:
                self._compile_expr(e.start)
            else:
                self.emit((Op.PUSH, None))
            if e.stop is not None:
                self._compile_expr(e.stop)
            else:
                self.emit((Op.PUSH, None))
            self.emit((Op.SLICE,))
        elif isinstance(e, ListLiteral):
            has_spread = any(isinstance(item, SpreadExpr) for item in e.items)
            if has_spread:
                # Build incrementally using a temp var to avoid stack confusion
                tmp = self._new_tmp("__spread")
                self.emit((Op.BUILD_LIST, 0))
                self.emit((Op.STORE, tmp))
                for item in e.items:
                    if isinstance(item, SpreadExpr):
                        # extend(base, iterable) → returns extended list
                        self.emit((Op.PUSH, "std.list._extend"))
                        self.emit((Op.LOAD, tmp))
                        self._compile_expr(item.expr)
                        self.emit((Op.SYSCALL, 2))
                        self.emit((Op.STORE, tmp))
                    else:
                        # append_to_top(base, item) → returns new list
                        self.emit((Op.PUSH, "std.list._append_to_top"))
                        self.emit((Op.LOAD, tmp))
                        self._compile_expr(item)
                        self.emit((Op.SYSCALL, 2))
                        self.emit((Op.STORE, tmp))
                self.emit((Op.LOAD, tmp))
            else:
                for item in e.items:
                    self._compile_expr(item)
                self.emit((Op.BUILD_LIST, len(e.items)))
        elif isinstance(e, ListCompExpr):
            # v1.4.9: [expr for var in iterable if cond]
            # Compile to: tmp=[], for var in iterable: if cond: tmp.push(expr)
            tmp_var = self._new_tmp("__lc")
            iter_var = self._new_tmp("__lci")
            idx_var = self._new_tmp("__lcidx")
            # tmp = []
            self.emit((Op.BUILD_LIST, 0))
            self.emit((Op.STORE, tmp_var))
            # iter = iterable
            self._compile_expr(e.iterable)
            self.emit((Op.STORE, iter_var))
            # idx = 0
            self.emit((Op.PUSH, 0))
            self.emit((Op.STORE, idx_var))
            # loop: idx < len(iter)
            loop_start = len(self.bytecode)
            self.emit((Op.LOAD, idx_var))
            self.emit((Op.LOAD, iter_var))
            self.emit((Op.LEN,))
            self.emit((Op.COMPARE, "<"))
            jif_end = len(self.bytecode)
            self.emit((Op.JIF, None))
            # var = iter[idx]
            self.emit((Op.LOAD, iter_var))
            self.emit((Op.LOAD, idx_var))
            self.emit((Op.GETITEM,))
            self.emit((Op.STORE, e.var_name))
            # if condition (optional)
            if e.condition is not None:
                self._compile_expr(e.condition)
                jif_skip = len(self.bytecode)
                self.emit((Op.JIF, None))
                # compile expr + push to tmp
                self.emit((Op.PUSH, "std.list.push"))
                self.emit((Op.LOAD, tmp_var))
                self._compile_expr(e.expr)
                self.emit((Op.SYSCALL, 2))
                self.emit((Op.POP,))
                self.bytecode[jif_skip] = (Op.JIF, len(self.bytecode))
            else:
                self.emit((Op.PUSH, "std.list.push"))
                self.emit((Op.LOAD, tmp_var))
                self._compile_expr(e.expr)
                self.emit((Op.SYSCALL, 2))
                self.emit((Op.POP,))
            # idx += 1
            self.emit((Op.LOAD, idx_var))
            self.emit((Op.PUSH, 1))
            self.emit((Op.ADD,))
            self.emit((Op.STORE, idx_var))
            self.emit((Op.JUMP, loop_start))
            self.bytecode[jif_end] = (Op.JIF, len(self.bytecode))
            # result = tmp
            self.emit((Op.LOAD, tmp_var))
        elif isinstance(e, CallValExpr):
            # v1.4.9: fns[0](5) -> eval callee, push args, CALL_VAL
            self._compile_expr(e.callee)
            for a in e.args:
                self._compile_expr(a)
            self.emit((Op.CALL_VAL, len(e.args)))
        elif isinstance(e, LambdaExpr):
            # v1.4.9: compile lambda as anonymous SkillDef, push function reference
            lam_name = self._new_tmp("__lambda")
            # Compile as a SkillDef
            skill = SkillDef(lam_name, e.params, e.body, defaults=getattr(e, 'defaults', {}))
            self._compile_stmt(skill)
            # Push a function reference
            self.emit((Op.PUSH_FUNC, lam_name))
        elif isinstance(e, MapLiteral):
            # keys and values
            for k, v in e.pairs:
                self._compile_expr(k)
                self._compile_expr(v)
            self.emit((Op.BUILD_MAP, len(e.pairs)))
        elif isinstance(e, FStringExpr):
            # v1.4.5: f-string compiled as series of ADD operations
            # Each part pushes a string value onto the stack, then we ADD them together
            if not e.parts:
                self.emit((Op.PUSH, ""))
                return
            first = True
            for kind, val in e.parts:
                if kind == 'literal':
                    self.emit((Op.PUSH, str(val)))
                else:
                    # expr: evaluate and convert to string via std.string.tostr syscall
                    self.emit((Op.PUSH, "std.string.tostr"))
                    self._compile_expr(val)
                    self.emit((Op.SYSCALL, 1))
                if not first:
                    self.emit((Op.ADD,))
                first = False
        else:
            raise RuntimeError(f"Unknown expr: {e}")
