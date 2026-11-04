"""`mellow test`: walk the files, run each one with the engine or engines
asked for, and compare against the golden output when there is one."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ....compiler import Compiler
from ....vm import MellowVM, RunConfig
from ...common import _json_print, _read_text


def _iter_test_files(root: Path, pattern: str) -> list[Path]:
    if root.is_file():
        return [root]
    out: list[Path] = []
    for p in sorted(root.rglob(pattern)):
        if p.is_file():
            out.append(p)
    return out


def _run_one_script(path: Path, *, engine: str, native_required: bool = False) -> dict[str, Any]:
    import io
    import contextlib

    src = _read_text(path)
    comp = Compiler()
    program = comp.compile(src, filename=str(path))
    vm = MellowVM()
    cfg = RunConfig(
        engine=engine,
        native_allow_fallback=False,
        native_require=(str(engine).lower().strip() == "c" or bool(native_required)),
    )

    buf_out = io.StringIO()
    buf_err = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            result = vm.run(program, config=cfg)
        return {"ok": True, "stdout": buf_out.getvalue(), "stderr": buf_err.getvalue(), "result": result}
    except Exception as e:
        return {"ok": False, "stdout": buf_out.getvalue(), "stderr": buf_err.getvalue(), "error": str(e), "type": e.__class__.__name__}


def _golden_output_for(path: Path) -> str | None:
    candidates = [
        path.with_suffix(path.suffix + ".out"),
        path.with_suffix(".out"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    return None


def _cmd_test(path: str, *, engine: str, pattern: str, json_out: bool, native_required: bool = False) -> int:
    root = Path(path)
    files = _iter_test_files(root, pattern)
    if not files:
        if json_out:
            _json_print({"ok": False, "error": f"no test files found in {root} (pattern={pattern})"})
        else:
            print(f"no test files found in {root} (pattern={pattern})")
        return 2

    results: list[dict[str, Any]] = []
    passed = 0
    failed = 0

    def compare(a: dict[str, Any], b: dict[str, Any]) -> tuple[bool, str]:
        keys = ("ok", "stdout", "stderr")
        for k in keys:
            if a.get(k) != b.get(k):
                return False, f"{k} mismatch"
        if a.get("ok"):
            if a.get("result") != b.get("result"):
                return False, "result mismatch"
        else:
            if a.get("error") != b.get("error"):
                return False, "error mismatch"
        return True, "ok"

    for f in files:
        golden = _golden_output_for(f)
        if engine == "dual":
            r_py = _run_one_script(f, engine="py")
            r_c = _run_one_script(f, engine="c", native_required=native_required)
            same, why = compare(r_py, r_c)
            ok = same
            if ok and golden is not None and r_py.get("stdout") != golden:
                ok = False
                why = "golden stdout mismatch"
            rec = {"file": str(f), "ok": ok, "why": why, "py": r_py, "c": r_c}
            if golden is not None:
                rec["golden"] = str(f.with_suffix(f.suffix + ".out") if f.with_suffix(f.suffix + ".out").exists() else f.with_suffix(".out"))
        else:
            r = _run_one_script(f, engine=engine, native_required=(native_required and engine == "c"))
            ok = bool(r.get("ok"))
            why = "ok"
            if ok and golden is not None and r.get("stdout") != golden:
                ok = False
                why = "golden stdout mismatch"
            rec = {"file": str(f), "ok": ok, "why": why, "run": r}
            if golden is not None:
                rec["golden"] = str(f.with_suffix(f.suffix + ".out") if f.with_suffix(f.suffix + ".out").exists() else f.with_suffix(".out"))
        results.append(rec)
        if ok:
            passed += 1
            if not json_out:
                print(f"[PASS] {f}")
        else:
            failed += 1
            if not json_out:
                print(f"[FAIL] {f}")
                if engine == "dual":
                    print(f"  reason: {rec.get('why')}")
                    print(f"  py: {rec['py'].get('error') or rec['py'].get('result')}")
                    print(f"  c : {rec['c'].get('error') or rec['c'].get('result')}")
                else:
                    print(f"  reason: {rec.get('why')}")
                    if rec['run'].get('error'):
                        print(f"  {rec['run'].get('error')}")
    out = {"ok": failed == 0, "passed": passed, "failed": failed, "results": results}
    if json_out:
        _json_print(out)
    return 0 if failed == 0 else 1
