# frinds/list_core.py

class ListCore:
    def __init__(self, engine, max_list_len=10_000):
        self.engine = engine
        self.max_list_len = max_list_len

    def create_list(self, elements_str):
        """v1.4.5: Parse list literal respecting quoted strings and nested brackets.

        Previously used a naive str.split(',') which broke on:
          ["hello, world", "test"]  ->  wrongly gave 3 items instead of 2
        """
        inner = elements_str.strip()
        # Strip outer brackets
        if inner.startswith("[") and inner.endswith("]"):
            inner = inner[1:-1]
        inner = inner.strip()
        if not inner:
            return []

        # Split by commas, but respect: quoted strings " ' and nested [] {}
        parts = []
        depth = 0
        in_quote = None
        buf = []
        i = 0
        while i < len(inner):
            ch = inner[i]
            if in_quote:
                buf.append(ch)
                if ch == '\\' and i + 1 < len(inner):
                    i += 1
                    buf.append(inner[i])
                elif ch == in_quote:
                    in_quote = None
            elif ch in ('"', "'"):
                in_quote = ch
                buf.append(ch)
            elif ch in ('[', '{', '('):
                depth += 1
                buf.append(ch)
            elif ch in (']', '}', ')'):
                depth -= 1
                buf.append(ch)
            elif ch == ',' and depth == 0:
                parts.append(''.join(buf).strip())
                buf = []
            else:
                buf.append(ch)
            i += 1
        if buf or parts:
            parts.append(''.join(buf).strip())

        out = [self.engine.evaluator.evaluate(e) for e in parts if e]
        if len(out) > self.max_list_len:
            if hasattr(self.engine, 'error_handler'):
                self.engine.error_handler.report("LIST", f"List too large (>{self.max_list_len})")
            return out[:self.max_list_len]
        return out

    def handle_command(self, line):
        # put "sword" into inventory
        if line.startswith("put ") and " into " in line:
            parts = line.split(" into ", 1)
            item = self.engine.evaluator.evaluate(parts[0][4:])
            list_name = parts[1].strip()
            if list_name in self.engine.variables and isinstance(self.engine.variables[list_name], list):
                if len(self.engine.variables[list_name]) >= self.max_list_len:
                    if hasattr(self.engine, 'error_handler'):
                        self.engine.error_handler.report("LIST", f"'{list_name}' is full")
                else:
                    self.engine.variables[list_name].append(item)
            else:
                if hasattr(self.engine, 'error_handler'):
                    self.engine.error_handler.report("VARIABLE", list_name)
