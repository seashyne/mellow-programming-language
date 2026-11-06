"""One expression node in, one Python expression string out."""

from __future__ import annotations

from ..ast import (
    BinaryOp,
    Call,
    CallValExpr,
    Expr,
    FStringExpr,
    GetModuleExpr,
    Index,
    LambdaExpr,
    ListCompExpr,
    ListLiteral,
    Literal,
    MapLiteral,
    ReturnStmt,
    SliceExpr,
    SpreadExpr,
    UnaryOp,
    Var,
)
from .names import _py_name


class ExpressionMixin:
    # ── Expression compilation ─────────────────────────────────────────

    def _expr(self, e: Expr) -> str:
        if isinstance(e, Literal):
            v = e.value
            if v is None: return "None"
            if v is True: return "True"
            if v is False: return "False"
            if isinstance(v, str): return repr(v)
            return str(v)

        elif isinstance(e, Var):
            name = e.name
            # Remap common builtins
            _remaps = {
                'true': 'True', 'false': 'False', 'none': 'None', 'null': 'None',
                'len': '_mellow_len', 'abs': 'abs_val', 'floor': 'floor_val',
                'ceil': 'ceil_val', 'round': 'round_val', 'sqrt': 'sqrt_val',
                'log': 'log_val', 'sin': 'sin_val', 'cos': 'cos_val', 'tan': 'tan_val',
                'min': 'min_val', 'max': 'max_val', 'clamp': 'clamp_val',
                'int': 'to_int', 'float': 'to_float', 'str': 'to_str', 'bool': 'to_bool',
                'random_int': 'random_int', 'random_float': 'random_float',
                'enumerate': 'enumerate_mellow', 'zip': 'zip_mellow',
                'range': 'range_mellow',
            }
            return _remaps.get(name, _py_name(name))

        elif isinstance(e, UnaryOp):
            operand = self._expr(e.expr)
            if e.op == '-': return f"(-{operand})"
            if e.op in ('not', '!'): return f"(not {operand})"
            return f"({e.op}{operand})"

        elif isinstance(e, BinaryOp):
            left = self._expr(e.left)
            right = self._expr(e.right)
            op_map = {
                '+': '+', '-': '-', '*': '*', '/': '/',
                '%': '%', '**': '**',
                '==': '==', '!=': '!=', '<': '<', '>': '>',
                '<=': '<=', '>=': '>=',
                'and': 'and', 'or': 'or',
            }
            py_op = op_map.get(e.op, e.op)
            if e.op == '/':
                # Mellow division: integer result if exact
                return f"(lambda _a, _b: int(_a/_b) if _b != 0 and int(_a/_b) == _a/_b else (_a/_b if _b != 0 else 0))({left}, {right})"
            return f"({left} {py_op} {right})"

        elif isinstance(e, Call):
            return self._call_expr(e)

        elif isinstance(e, Index):
            return f"({self._expr(e.target)})[{self._expr(e.index)}]"

        elif isinstance(e, SliceExpr):
            target = self._expr(e.target)
            start = self._expr(e.start) if e.start else ""
            stop = self._expr(e.stop) if e.stop else ""
            step = f":{self._expr(e.step)}" if e.step else ""
            return f"({target})[{start}:{stop}{step}]"

        elif isinstance(e, ListLiteral):
            items = []
            for item in e.items:
                if isinstance(item, SpreadExpr):
                    items.append(f"*({self._expr(item.expr)})")
                else:
                    items.append(self._expr(item))
            return f"[{', '.join(items)}]"

        elif isinstance(e, MapLiteral):
            pairs = ", ".join(f"{self._expr(k)}: {self._expr(v)}" for k, v in e.pairs)
            return "{" + pairs + "}"

        elif isinstance(e, FStringExpr):
            parts = []
            for kind, val in e.parts:
                if kind == 'literal':
                    parts.append(repr(str(val)))
                else:
                    parts.append(f"_fmt({self._expr(val)})")
            if not parts: return "''"
            return " + ".join(parts)

        elif isinstance(e, LambdaExpr):
            # Build params with defaults
            defaults = getattr(e, 'defaults', {}) or {}
            params_parts = []
            for p in e.params:
                if p.startswith("*"):
                    params_parts.append(f"*{_py_name(p[1:])}")
                elif p in defaults:
                    params_parts.append(f"{_py_name(p)}={self._expr(defaults[p])}")
                else:
                    params_parts.append(_py_name(p))
            params_str = ", ".join(params_parts)

            if len(e.body) == 1 and isinstance(e.body[0], ReturnStmt) and e.body[0].expr is not None:
                body_src = self._expr(e.body[0].expr)
                return f"(lambda {params_str}: {body_src})"
            else:
                # Multi-statement: emit as nested def and return reference
                fn_name = f"__lam_{self._tmp_counter}"
                self._tmp_counter += 1
                self._w(f"def {fn_name}({params_str}):")
                self._indent += 1
                for st in e.body: self._stmt(st)
                if not e.body: self._w("pass")
                self._indent -= 1
                return fn_name

        elif isinstance(e, CallValExpr):
            # v1.4.9: call expression value: fns[0](args)
            callee = self._expr(e.callee)
            args = [self._expr(a) for a in e.args]
            return f"({callee})({', '.join(args)})"
        elif isinstance(e, ListCompExpr):
            expr_src = self._expr(e.expr)
            var = _py_name(e.var_name)
            it = self._expr(e.iterable)
            if e.condition:
                cond = self._expr(e.condition)
                return f"[{expr_src} for {var} in ({it} or []) if {cond}]"
            return f"[{expr_src} for {var} in ({it} or [])]"

        elif isinstance(e, GetModuleExpr):
            args_src = ", ".join(self._expr(a) for a in e.args)
            return f"_mod_{e.module}_{e.function}({args_src})"

        else:
            return f"None  # unsupported expr: {type(e).__name__}"

    def _call_expr(self, e: Call) -> str:
        # Map Mellow standard library calls to Python equivalents
        _name_map = {
            'show': 'show',
            'len': '_mellow_len',
            'list_push': 'list_push',
            'list_pop': 'list_pop',
            'list_len': 'list_len',
            'list_has': 'list_has',
            'list_map': 'list_map',
            'list_filter': 'list_filter',
            'list_reduce': 'list_reduce',
            'list_sort': 'list_sort',
            'list_reverse': 'list_reverse',
            'list_slice': 'list_slice',
            'list_find': 'list_find',
            'list_count': 'list_count',
            'list_flat': 'list_flat',
            'map_keys': 'map_keys',
            'map_values': 'map_values',
            'map_has': 'map_has',
            'map_set': 'map_set',
            'map_get': 'map_get',
            'map_del': 'map_del',
            'str_split': 'str_split',
            'str_join': 'str_join',
            'str_upper': 'str_upper',
            'str_lower': 'str_lower',
            'str_trim': 'str_trim',
            'str_starts': 'str_starts',
            'str_ends': 'str_ends',
            'str_contains': 'str_contains',
            'str_replace': 'str_replace',
            'str_find': 'str_find',
            'to_int': 'to_int',
            'to_float': 'to_float',
            'to_str': 'to_str',
            'to_bool': 'to_bool',
            'abs': 'abs_val',
            'floor': 'floor_val',
            'ceil': 'ceil_val',
            'round': 'round_val',
            'sqrt': 'sqrt_val',
            'sin': 'sin_val',
            'cos': 'cos_val',
            'tan': 'tan_val',
            'log': 'log_val',
            'min': 'min_val',
            'max': 'max_val',
            'clamp': 'clamp_val',
            'sign': 'sign',
            'fmod': 'fmod',
            'random_int': 'random_int',
            'random_float': 'random_float',
            'random_choice': 'random_choice',
            'shuffle': 'shuffle_list',
            'assert': 'assert_mellow',
            'assert_eq': 'assert_eq',
            'assert_ne': 'assert_ne',
            'is_number': 'is_number',
            'is_string': 'is_string',
            'is_bool': 'is_bool',
            'is_list': 'is_list',
            'is_map': 'is_map',
            'is_none': 'is_none',
            'type_of': 'type_of',
            'enumerate': 'enumerate_mellow',
            'zip': 'zip_mellow',
            'range': 'range_mellow',
        }
        name_raw = e.name
        # Handle dotted module calls: mylib.func(args) → keep as mylib.func
        if '.' in name_raw:
            parts = name_raw.split('.', 1)
            py_mod = _py_name(parts[0])
            py_func = parts[1]
            args = [self._expr(a) for a in e.args]
            if e.kwargs:
                kw_str = ", ".join(f"{k}={self._expr(v)}" for k, v in e.kwargs)
                args.append(kw_str)
            return f"{py_mod}.{py_func}({', '.join(args)})"

        name = _name_map.get(name_raw, _py_name(name_raw))
        args = [self._expr(a) for a in e.args]
        if e.kwargs:
            kw_str = ", ".join(f"{k}={self._expr(v)}" for k, v in e.kwargs)
            args.append(kw_str)
        return f"{name}({', '.join(args)})"
