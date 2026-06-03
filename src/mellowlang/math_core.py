# frinds/math_core.py
# v1.4.5: Added min, max, floor, ceil, clamp, log, sin, cos, tan
#         Replaced Newton's method sqrt with math.sqrt for correctness
import math
import re

class MathCore:
    def __init__(self, engine):
        self.engine = engine
        self.commands = [
            "sqrt", "abs", "round", "power",
            # v1.4.5 additions
            "min", "max", "floor", "ceil", "clamp",
            "log", "sin", "cos", "tan",
        ]

    def execute(self, name, args):
        if not args: return 0

        if name == "sqrt":  return self.get_sqrt(args[0])
        if name == "abs":   return self.get_abs(args[0])
        if name == "round": return self.get_round(args[0])
        if name == "power": return self.get_power(args[0], args[1]) if len(args) >= 2 else 0

        # v1.4.5
        if name == "min":
            if len(args) == 1 and isinstance(args[0], list):
                return min((float(x) for x in args[0]), default=0)
            nums = [float(a) for a in args]
            return min(nums)
        if name == "max":
            if len(args) == 1 and isinstance(args[0], list):
                return max((float(x) for x in args[0]), default=0)
            nums = [float(a) for a in args]
            return max(nums)
        if name == "floor":  return int(math.floor(float(args[0])))
        if name == "ceil":   return int(math.ceil(float(args[0])))
        if name == "clamp":
            if len(args) < 3:
                return float(args[0])
            val, lo, hi = float(args[0]), float(args[1]), float(args[2])
            return max(lo, min(hi, val))
        if name == "log":
            base = float(args[1]) if len(args) >= 2 else math.e
            val = float(args[0])
            if val <= 0: return 0
            return math.log(val, base)
        if name == "sin":  return math.sin(float(args[0]))
        if name == "cos":  return math.cos(float(args[0]))
        if name == "tan":  return math.tan(float(args[0]))

        return 0

    def get_sqrt(self, n):
        # v1.4.5: use math.sqrt instead of 12-iteration Newton's method
        n = float(n)
        if n < 0: return 0
        return math.sqrt(n)

    def get_abs(self, n): return abs(float(n))
    def get_round(self, n): return round(float(n))
    def get_power(self, b, e): return float(b) ** float(e)

    def calculate(self, expr):
        # Tokenize numbers, identifiers, operators, parentheses
        tokens = re.findall(r'\d+\.?\d*|[a-zA-Z_]\w*|[\+\-\*\/\(\)]', expr)
        processed = []
        for t in tokens:
            if t in self.engine.variables and isinstance(self.engine.variables[t], (int, float)):
                processed.append(str(self.engine.variables[t]))
            else:
                processed.append(t)

        prec = {'+': 1, '-': 1, '*': 2, '/': 2}
        output, stack = [], []
        for token in processed:
            if token.replace('.', '', 1).replace('-', '', 1).isdigit():
                output.append(float(token))
            elif token in prec:
                while stack and stack[-1] in prec and prec[stack[-1]] >= prec[token]:
                    output.append(stack.pop())
                stack.append(token)
            elif token == '(':
                stack.append(token)
            elif token == ')':
                while stack and stack[-1] != '(':
                    output.append(stack.pop())
                if stack and stack[-1] == '(':
                    stack.pop()
        while stack:
            output.append(stack.pop())

        res_stack = []
        for token in output:
            if isinstance(token, float):
                res_stack.append(token)
            else:
                if len(res_stack) < 2:
                    continue
                b, a = res_stack.pop(), res_stack.pop()
                if token == '+': res_stack.append(a + b)
                elif token == '-': res_stack.append(a - b)
                elif token == '*': res_stack.append(a * b)
                elif token == '/': res_stack.append(a / b if b != 0 else 0)
        return res_stack[0] if res_stack else 0
