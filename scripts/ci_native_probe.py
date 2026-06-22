from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import traceback


SOURCE = """\
let score = 1
score = score + 4
print(score)
"""


def _annotation(message: str) -> None:
    escaped = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::error title=Native arithmetic probe::{escaped}")


def main() -> int:
    output = io.StringIO()
    try:
        import mellowlang
        from mellowlang.compiler import Compiler
        from mellowlang.vm import MellowVM, RunConfig

        vm = MellowVM()
        program = Compiler().compile(SOURCE, filename="<ci-native-probe>")
        with contextlib.redirect_stdout(output):
            vm.run(
                program,
                config=RunConfig(
                    engine="c",
                    native_allow_fallback=False,
                    native_require=True,
                ),
            )
        payload = {
            "python": sys.executable,
            "cwd": os.getcwd(),
            "package": mellowlang.__file__,
            "output": output.getvalue(),
            "engine": vm.last_engine,
            "engine_detail": vm.last_engine_detail,
            "native": vm.last_native_result,
            "bytecode": [tuple(map(str, item)) for item in program.bytecode],
        }
        print(json.dumps(payload, ensure_ascii=True, indent=2))
        if output.getvalue().strip() != "5" or vm.last_engine != "c":
            _annotation(json.dumps(payload, ensure_ascii=True))
            return 1
        return 0
    except Exception:
        details = json.dumps(
            {
                "python": sys.executable,
                "cwd": os.getcwd(),
                "sys_path": sys.path,
                "traceback": traceback.format_exc(),
            },
            ensure_ascii=True,
        )
        print(details)
        _annotation(details)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
