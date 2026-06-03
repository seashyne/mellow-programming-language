\
# mellowlang/evaluator.py
from __future__ import annotations

import re
from typing import Any


class Evaluator:
    def __init__(self, engine: Any):
        self.engine = engine

    def _parse_string_literal(self, expr: str) -> str | None:
        """Parse a quoted string literal supporting common escapes.

        Supports both double and single quotes:
          "hello\n"  'tab\t'  "quote: \""
        """
        s = (expr or "").strip()
        if len(s) < 2:
            return None
        q = s[0]
        if q not in ("'", '"') or s[-1] != q:
            return None

        body = s[1:-1]
        out: list[str] = []
        i = 0
        while i < len(body):
            ch = body[i]
            if ch != "\\":
                out.append(ch)
                i += 1
                continue

            # escape sequence
            i += 1
            if i >= len(body):
                out.append("\\")
                break

            esc = body[i]
            i += 1

            if esc == "n":
                out.append("\n")
                continue
            if esc == "r":
                out.append("\r")
                continue
            if esc == "t":
                out.append("\t")
                continue
            if esc == "\\":
                out.append("\\")
                continue
            if esc == '"':
                out.append('"')
                continue
            if esc == "'":
                out.append("'")
                continue
            if esc == "u" and i + 3 < len(body):
                hex4 = body[i : i + 4]
                if re.fullmatch(r"[0-9a-fA-F]{4}", hex4):
                    out.append(chr(int(hex4, 16)))
                    i += 4
                    continue

            # Unknown escape: keep it as-is
            out.append(esc)

        return "".join(out)

    def evaluate(self, expr: str):
        expr = (expr or "").strip()
        if not expr:
            return None

        # Boolean literals
        if expr.lower() == "true":
            return True
        if expr.lower() == "false":
            return False
        if expr.lower() in ("none", "null"):
            return None

        # --- List Index Access (player_stats[1]) must come BEFORE variable-not-found error ---
        if "[" in expr and expr.endswith("]") and expr.count("[") == 1:
            var_name = expr[: expr.find("[")].strip()
            index_expr = expr[expr.find("[") + 1 : -1].strip()
            if hasattr(self.engine, "variables") and var_name in self.engine.variables:
                target = self.engine.variables[var_name]
                try:
                    idx = int(self.evaluate(index_expr))
                except Exception:
                    idx = 0
                if isinstance(target, list) and 0 <= idx < len(target):
                    return target[idx]

        # String literal (supports escapes + single quotes)
        parsed = self._parse_string_literal(expr)
        if parsed is not None:
            return parsed

        # v1.4.5: f-string literal: f"..." or f'...'
        if len(expr) >= 3 and expr[0].lower() == 'f' and expr[1] in ('"', "'"):
            return self._eval_fstring_expr(expr)

        # Number literal (int/float) — keep it simple and avoid parsing math expressions here
        is_num = expr.replace(".", "", 1).replace("-", "", 1).isdigit()
        if is_num and not any(op in expr for op in "+-*/"):
            return float(expr) if "." in expr else int(expr)

        # Function call / skill call: name(...)
        if "(" in expr and expr.endswith(")"):
            name = expr[: expr.find("(")].strip()
            content = expr[expr.find("(") + 1 : expr.rfind(")")].strip()

            # split args while respecting quotes
            args_raw = (
                re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', content) if content else []
            )
            args = [self.evaluate(a.strip()) for a in args_raw if a.strip()]

            # Math core
            if hasattr(self.engine, "math_core") and name in getattr(
                self.engine.math_core, "commands", []
            ):
                return self.engine.math_core.execute(name, args)

            # Storage core
            if hasattr(self.engine, "storage_core") and name in getattr(
                self.engine.storage_core, "commands", []
            ):
                if not bool(getattr(self.engine, "config", {}).get("allow_storage", True)):
                    if hasattr(self.engine, "error_handler"):
                        self.engine.error_handler.report(
                            "SANDBOX",
                            "Storage API is disabled by config (allow_storage=false)",
                        )
                    return None
                return self.engine.storage_core.execute(name, args)

            # Built-ins (sandbox guarded by engine.config)
            if name == "ask":
                if getattr(self.engine, "config", {}).get("allow_ask", False):
                    return input(args[0] if args else "")
                if hasattr(self.engine, "error_handler"):
                    self.engine.error_handler.report("SANDBOX", "ask() is disabled")
                return None

            if name == "random":
                import random

                if len(args) >= 2:
                    return random.randint(int(args[0]), int(args[1]))
                return random.random()

            # User-defined skills
            if hasattr(self.engine, "functions") and name in self.engine.functions:
                return self.engine.call_skill(name, args)

        # Variable
        if hasattr(self.engine, "variables") and expr in self.engine.variables:
            return self.engine.variables[expr]

        # List literal (if list core exists)
        if expr.startswith("[") and expr.endswith("]") and hasattr(self.engine, "list_core"):
            return self.engine.list_core.create_list(expr)

        # Math / string concatenation
        if any(op in expr for op in ["+", "-", "*", "/"]):
            # string concatenation using +
            if '"' in expr or "'" in expr:
                parts = re.split(r"\s*\+\s*(?=(?:[^\"']*[\"'][^\"']*[\"'])*[^\"']*$)", expr)
                res = ""
                for p in parts:
                    val = self.evaluate(p.strip())
                    if hasattr(self.engine, "format_value"):
                        res += str(self.engine.format_value(val))
                    else:
                        res += str(val)
                return res

            if hasattr(self.engine, "math_core"):
                return self.engine.math_core.calculate(expr)

        # Variable-not-found error (only after trying special syntaxes)
        if not (is_num or expr.startswith('"') or expr.startswith("'")):
            if hasattr(self.engine, "error_handler") and not any(op == expr for op in "+-*/"):
                self.engine.error_handler.report("VARIABLE", expr)

        return None

    def _eval_fstring_expr(self, expr: str) -> str:
        """v1.4.5: Evaluate a raw f-string expression like f"Hello {name}!" in interpreter mode."""
        # Strip the f prefix and quote
        quote = expr[1]
        inner = expr[2:-1]  # remove f"..." wrapper

        parts_out = []
        buf = []
        i = 0
        n = len(inner)
        while i < n:
            ch = inner[i]
            if ch == '{':
                if buf:
                    parts_out.append(''.join(buf))
                    buf = []
                depth = 1
                i += 1
                expr_buf = []
                while i < n and depth > 0:
                    c = inner[i]
                    if c == '{': depth += 1
                    elif c == '}': depth -= 1
                    if depth > 0:
                        expr_buf.append(c)
                    i += 1
                expr_src = ''.join(expr_buf).strip()
                if expr_src:
                    val = self.evaluate(expr_src)
                    if val is None:
                        parts_out.append("none")
                    elif isinstance(val, bool):
                        parts_out.append("true" if val else "false")
                    elif isinstance(val, float) and val == int(val):
                        parts_out.append(str(int(val)))
                    else:
                        fv = self.engine.format_value(val) if hasattr(self.engine, 'format_value') else val
                        parts_out.append(str(fv))
            elif ch == '\\' and i + 1 < n:
                esc = inner[i + 1]
                i += 2
                if esc == 'n': buf.append('\n')
                elif esc == 't': buf.append('\t')
                elif esc == 'r': buf.append('\r')
                elif esc == '\\': buf.append('\\')
                elif esc in ('"', "'"): buf.append(esc)
                else: buf.append(esc)
            else:
                buf.append(ch)
                i += 1
        if buf:
            parts_out.append(''.join(buf))
        return ''.join(parts_out)
