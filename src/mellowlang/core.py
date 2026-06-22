# frinds/core.py
import re

from mellowlang.time_core import TimeCore
from mellowlang.evaluator import Evaluator
from mellowlang.math_core import MathCore
from mellowlang.error_core import MellowLangError
from mellowlang.list_core import ListCore
from mellowlang.storage_core import StorageCore

DEFAULT_CONFIG = {
    # Sandbox switches
    "allow_ask": False,
    "allow_wait": True,
    "allow_storage": True,

    # Safety limits
    "max_steps": 200_000,
    "max_loop_iterations": 50_000,
    "max_recursion": 50,
}

class MellowLangEngine:
    """Interpreter (direct execution) with sandbox limits.

    For stronger sandbox, prefer Compiler -> VM (bytecode) execution.
    """
    def __init__(self, parent=None, config=None):
        self.parent = parent
        self.variables = parent.variables if parent else {}
        self.functions = parent.functions if parent else {}
        self.precision = parent.precision if parent else None

        self.config = dict(DEFAULT_CONFIG)
        if parent and hasattr(parent, 'config'):
            self.config.update(parent.config)
        if config:
            self.config.update(config)

        self.current_line = 0
        self.is_stopped = False
        self._steps = 0
        self._rec_depth = (getattr(parent, '_rec_depth', 0) if parent else 0)

        self.evaluator = Evaluator(self)
        self.math_core = MathCore(self)
        self.time_core = parent.time_core if parent else TimeCore()

        self.error_handler = MellowLangError(self)
        self.list_core = ListCore(self)

        # Storage sandbox
        self.storage_core = parent.storage_core if parent else StorageCore(self)

    def _tick(self):
        self._steps += 1
        if self._steps > int(self.config.get('max_steps', 200_000)):
            self.error_handler.report("SANDBOX", "Step limit exceeded")
            self.is_stopped = True

    def call_skill(self, name, args):
        if self._rec_depth >= int(self.config.get('max_recursion', 50)):
            self.error_handler.report("SANDBOX", "Max recursion depth exceeded")
            return None
        func_data = self.functions[name]
        sub = MellowLangEngine(parent=self, config=self.config)
        sub._rec_depth = self._rec_depth + 1
        for i, p_name in enumerate(func_data["params"]):
            if i < len(args):
                sub.variables[p_name] = args[i]
        return sub.run(func_data["body"])

    def get_block(self, lines):
        block = []
        while self.current_line + 1 < len(lines):
            nxt = lines[self.current_line + 1]
            if not nxt.strip():
                self.current_line += 1
                continue
            if nxt.startswith("    ") or nxt.startswith("\t"):
                block.append(nxt)
                self.current_line += 1
            else:
                break
        return block

    def format_value(self, val):
        if isinstance(val, (float, int)):
            if self.precision is not None:
                return f"{float(val):.{int(self.precision)}f}"
            if isinstance(val, float) and val.is_integer():
                return int(val)
        return val

    def run_sub_block(self, lines):
        cleaned = [l[4:] if l.startswith("    ") else l[1:] if l.startswith("\t") else l for l in lines]
        sub = MellowLangEngine(parent=self, config=self.config)
        res = sub.run(cleaned)
        if res == "STOP_SIGNAL":
            return "STOP_SIGNAL"
        return res

    def evaluate_boolean(self, cond):
        """v1.4.5: Use AST ExprParser (Pratt parser) for correct boolean evaluation.

        Previously used fragile string-splitting which broke on compound conditions
        like `x >= 10 and y < 5` or `not is_dead and hp > 0`.
        Now delegates to the same parser used by the VM pipeline.
        """
        from .parser import ExprParser, ParseError
        from .ast import BinaryOp, UnaryOp, Literal, Var, Call, Index

        src = str(cond).strip()
        if not src:
            return False

        # Fast path for bare booleans
        low = src.lower()
        if low == "true":  return True
        if low == "false": return False
        if low == "none":  return False

        # Special: list has item (compatibility syntax)
        if " has " in src:
            parts = src.split(" has ", 1)
            var_val = self.evaluator.evaluate(parts[0].strip())
            item_val = self.evaluator.evaluate(parts[1].strip())
            return isinstance(var_val, list) and item_val in var_val

        # Parse and walk the AST
        try:
            parser = ExprParser(src)
            tree = parser.parse()
            return self._truthy(self._eval_ast(tree))
        except (ParseError, Exception):
            # Fallback: delegate to bytecode evaluator
            result = self.evaluator.evaluate(src)
            return self._truthy(result)

    def _truthy(self, val):
        """Python-style truthiness for MellowLang values."""
        if val is None:  return False
        if isinstance(val, bool): return val
        if isinstance(val, (int, float)): return val != 0
        if isinstance(val, str): return val != ""
        if isinstance(val, list): return len(val) > 0
        if isinstance(val, dict): return len(val) > 0
        return bool(val)

    def _eval_ast(self, node):
        """Walk an AST node and return its value, using engine variables."""
        from .ast import (BinaryOp, UnaryOp, Literal, Var, Call,
                          Index, ListLiteral, MapLiteral, FStringExpr)

        if isinstance(node, Literal):
            return node.value

        if isinstance(node, Var):
            name = node.name
            low = name.lower()
            if low == "true":  return True
            if low == "false": return False
            if low in ("none", "null"): return None
            return self.variables.get(name)

        if isinstance(node, UnaryOp):
            val = self._eval_ast(node.expr)
            if node.op == "not": return not self._truthy(val)
            if node.op == "-":
                try: return -float(val)
                except: return 0
            return val

        if isinstance(node, BinaryOp):
            op = node.op
            # Short-circuit boolean ops
            if op == "and":
                lv = self._eval_ast(node.left)
                return lv if not self._truthy(lv) else self._eval_ast(node.right)
            if op == "or":
                lv = self._eval_ast(node.left)
                return lv if self._truthy(lv) else self._eval_ast(node.right)

            lv = self._eval_ast(node.left)
            rv = self._eval_ast(node.right)

            # Arithmetic
            if op == "+":
                if isinstance(lv, str) or isinstance(rv, str):
                    return str(self.format_value(lv)) + str(self.format_value(rv))
                try: return lv + rv
                except: return 0
            if op == "-":
                try: return float(lv) - float(rv)
                except: return 0
            if op == "*":
                try: return float(lv) * float(rv)
                except: return 0
            if op == "/":
                try:
                    d = float(rv)
                    return float(lv) / d if d != 0 else 0
                except: return 0

            # Comparison
            if op == "==":
                try: return float(lv) == float(rv)
                except: return str(lv) == str(rv)
            if op == "!=":
                try: return float(lv) != float(rv)
                except: return str(lv) != str(rv)
            if op in (">", "<", ">=", "<="):
                try:
                    a, b = float(lv), float(rv)
                    if op == ">":  return a > b
                    if op == "<":  return a < b
                    if op == ">=": return a >= b
                    if op == "<=": return a <= b
                except: return False

            return None

        if isinstance(node, Index):
            obj = self._eval_ast(node.target)
            idx = self._eval_ast(node.index)
            try:
                if isinstance(obj, list):
                    return obj[int(idx)]
                if isinstance(obj, dict):
                    return obj.get(idx)
            except: pass
            return None

        if isinstance(node, Call):
            # Delegate function calls back to the evaluator
            args_str = ", ".join(self._repr_for_eval(self._eval_ast(a)) for a in node.args)
            return self.evaluator.evaluate(f"{node.name}({args_str})")

        if isinstance(node, ListLiteral):
            return [self._eval_ast(e) for e in node.items]

        if isinstance(node, MapLiteral):
            return {str(self._eval_ast(k)): self._eval_ast(v) for k, v in node.pairs}

        if isinstance(node, FStringExpr):
            return self._eval_fstring(node)

        return None

    def _repr_for_eval(self, val):
        """Convert a Python value back to a MellowLang expression string for evaluator."""
        if val is None: return "none"
        if isinstance(val, bool): return "true" if val else "false"
        if isinstance(val, str): return f'"{val}"'
        return str(val)

    def _eval_fstring(self, node) -> str:
        """v1.4.5: Evaluate FStringExpr by processing parts sequentially."""
        parts_out = []
        for kind, val in node.parts:
            if kind == 'literal':
                parts_out.append(str(val))
            else:
                # val is an Expr node
                result = self._eval_ast(val)
                if result is None:
                    parts_out.append("none")
                elif isinstance(result, bool):
                    parts_out.append("true" if result else "false")
                elif isinstance(result, float) and result == int(result):
                    parts_out.append(str(int(result)))
                else:
                    parts_out.append(str(self.format_value(result)))
        return "".join(parts_out)

    def run(self, lines):
        self.current_line = 0
        last_group_executed = False

        while self.current_line < len(lines):
            if self.is_stopped:
                break
            self._tick()

            line = lines[self.current_line].strip()
            if not line or line.startswith("//"):
                self.current_line += 1
                continue

            # keep x = expr
            if line.startswith("keep "):
                m = re.match(r"keep\s+(\w+)\s*=\s*(.*)", line)
                if not m:
                    self.error_handler.report("SYNTAX", line)
                    self.current_line += 1
                    continue
                var_name, expr = m.groups()
                expr = expr.strip()
                if expr.startswith("[") and expr.endswith("]"):
                    self.variables[var_name] = self.list_core.create_list(expr)
                else:
                    self.variables[var_name] = self.evaluator.evaluate(expr)
                last_group_executed = False

            elif line.startswith("put "):
                self.list_core.handle_command(line)
                last_group_executed = False

            elif line.startswith("precision("):
                m = re.search(r'precision\((.*)\)', line)
                if m:
                    self.precision = int(self.evaluator.evaluate(m.group(1)))
                last_group_executed = False

            elif line.startswith("show("):
                m = re.search(r'show\((.*)\)', line)
                if m:
                    print(self.format_value(self.evaluator.evaluate(m.group(1))))
                last_group_executed = False

            elif line == "stop":
                self.is_stopped = True
                return "STOP_SIGNAL"

            elif line.startswith("check "):
                m = re.search(r'\((.*)\)', line)
                cond = m.group(1) if m else "False"
                sub_lines = self.get_block(lines)
                if self.evaluate_boolean(cond):
                    if self.run_sub_block(sub_lines) == "STOP_SIGNAL":
                        return "STOP_SIGNAL"
                    last_group_executed = True
                else:
                    last_group_executed = False

            elif line.startswith("also"):
                m = re.search(r'\((.*)\)', line)
                cond = m.group(1) if m else "False"
                sub_lines = self.get_block(lines)
                if not last_group_executed and self.evaluate_boolean(cond):
                    if self.run_sub_block(sub_lines) == "STOP_SIGNAL":
                        return "STOP_SIGNAL"
                    last_group_executed = True

            elif line.startswith("else:"):
                sub_lines = self.get_block(lines)
                if not last_group_executed:
                    if self.run_sub_block(sub_lines) == "STOP_SIGNAL":
                        return "STOP_SIGNAL"
                last_group_executed = True

            elif line.startswith("loop"):
                m = re.search(r'\((.*)\)', line)
                cond_str = m.group(1) if m else "True"
                sub_lines = self.get_block(lines)
                it = 0
                while self.evaluate_boolean(cond_str):
                    self._tick()
                    it += 1
                    if it > int(self.config.get('max_loop_iterations', 50_000)):
                        self.error_handler.report("SANDBOX", "Loop iteration limit exceeded")
                        break
                    if self.run_sub_block(sub_lines) == "STOP_SIGNAL":
                        break
                last_group_executed = False

            elif line.startswith("skill "):
                m = re.match(r"skill\s+(\w+)\((.*)\):", line)
                if m:
                    name, p = m.groups()
                    params = [x.strip() for x in p.split(',') if x.strip()]
                    self.functions[name] = {"params": params, "body": self.get_block(lines)}
                last_group_executed = False

            elif line.startswith("wait("):
                if not self.config.get('allow_wait', True):
                    self.error_handler.report("SANDBOX", "wait() is disabled")
                else:
                    m = re.search(r'wait\((.*)\)', line)
                    if m:
                        seconds = self.evaluator.evaluate(m.group(1))
                        self.time_core.wait(seconds)
                last_group_executed = False

            elif line.startswith("save ") and " into " in line:
                if not self.config.get('allow_storage', True):
                    self.error_handler.report("SANDBOX", "save/load is disabled")
                else:
                    parts = line[5:].split(" into ", 1)
                    data = self.evaluator.evaluate(parts[0].strip())
                    filename = self.evaluator.evaluate(parts[1].strip())
                    self.storage_core.execute("save_data", [data, filename])
                last_group_executed = False

            elif line.startswith("load ") and " into " in line:
                if not self.config.get('allow_storage', True):
                    self.error_handler.report("SANDBOX", "save/load is disabled")
                else:
                    parts = line[5:].split(" into ", 1)
                    filename = self.evaluator.evaluate(parts[0].strip())
                    var_name = parts[1].strip()
                    data = self.storage_core.execute("load_data", [filename])
                    self.variables[var_name] = data
                last_group_executed = False

            else:
                self.error_handler.report("SYNTAX", line)

            self.current_line += 1

        return None
