# frinds/error_core.py

class MellowLangRuntimeError(Exception):
    def __init__(self, error_type: str, message: str, line_num: int | None = None, *, filename: str | None = None, col: int | None = None, trace: list | None = None):
        self.error_type = error_type
        self.message = message
        self.line_num = line_num
        self.filename = filename
        self.col = col
        self.trace = trace or []
        super().__init__(self.__str__())

    def __str__(self):
        loc = None
        if self.filename and self.line_num is not None:
            if self.col is not None:
                loc = f"{self.filename}:{self.line_num}:{self.col}"
            else:
                loc = f"{self.filename}:{self.line_num}"
        elif self.line_num is not None:
            loc = f"line {self.line_num}"
        if loc:
            return f"{self.error_type} at {loc}: {self.message}"
        return f"{self.error_type}: {self.message}"


class MellowLangError:
    """Friendly error reporter (Python interpreter)."""
    def __init__(self, engine):
        self.engine = engine

    def raise_error(self, error_type, message):
        line_num = getattr(self.engine, "current_line", 0) + 1
        self.engine.is_stopped = True
        raise MellowLangRuntimeError(error_type, message, line_num)

    def report(self, error_type, message):
        line_num = getattr(self.engine, "current_line", 0) + 1
        print(f"\n--- ⚠️ Hey friend! Something went wrong at line {line_num} ---")
        if error_type == "VARIABLE":
            print(f"🧐 I can't find '{message}'. Did you forget to 'keep' it?")
        elif error_type == "MATH":
            print(f"🧮 Calculation Error: {message}")
        elif error_type == "SYNTAX":
            print(f"✍️ Command format looks a bit weird: {message}")
        elif error_type == "TIME":
            print(f"⏳ Internal clock error: {message}")
        elif error_type == "LIST":
            print(f"📦 Pocket error (List): {message}")
        else:
            print(f"❓ {error_type}: {message}")
        print("-------------------------------------------\n")
        self.engine.is_stopped = True