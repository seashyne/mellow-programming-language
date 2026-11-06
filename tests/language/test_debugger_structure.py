"""The contract for the `vm/debugger.py` split.

`vm/debugger.py` was one 366-line module: a single 359-line `DebuggerMixin` holding
breakpoint parsing, the trace/step hook and resume modes, frame inspection, and the
snapshot/rendering helpers. It is now a facade that assembles `DebuggerMixin` from
`debugger_groups/`, one mixin per subject, with every method moved verbatim.

This lives in its own module because the shared gate, `test_source_structure.py`, sits
at its declared ceiling - that file's own comment says the next subsystem's contract
moves out rather than the ceiling rising.
"""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "mellowlang"
PKG = SRC / "vm" / "debugger_groups"
FACADE = SRC / "vm" / "debugger.py"

DEBUG_MODULES = ("breakpoints", "stepping", "inspection", "rendering")
# No group imports another: every cross-subject call goes through `self`, so the
# mixins are peers a caller may reorder only at the assembler.
DEBUG_LAYER_RANK = {"breakpoints": 0, "stepping": 0, "inspection": 0, "rendering": 0}
# Where each method (and the mixin that contributes it) must live.
DEBUG_MEMBER_HOME = {
    "_parse_break_lines": "breakpoints",
    "_debug_hook": "stepping", "debug_resume": "stepping",
    "_maybe_pause_runtime_debugger": "stepping", "run_until_pause": "stepping",
    "_instr_name": "inspection", "_current_frame_depth": "inspection",
    "_typed_value": "inspection", "_typed_scope": "inspection",
    "_typed_stack": "inspection", "_eval_debug_expr": "inspection",
    "_debug_watch_expr_values": "inspection", "_typed_frames": "inspection",
    "_debug_dump_watch": "rendering", "_source_span": "rendering",
    "_debug_snapshot": "rendering",
    "BreakpointMixin": "breakpoints", "SteppingMixin": "stepping",
    "InspectionMixin": "inspection", "RenderingMixin": "rendering",
}
# The only name a consumer is allowed to reach: `vm/interp/vm.py` and
# `vm/python_vm.py` both import it and assemble it last-but-one in the MRO.
DEBUG_EXPORTS = {"DebuggerMixin"}
DEBUG_MIXINS = ("BreakpointMixin", "SteppingMixin", "InspectionMixin",
                "RenderingMixin")
DEBUG_METHODS = {name for name in DEBUG_MEMBER_HOME if name not in DEBUG_MIXINS}


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _declared_names(path: Path) -> set[str]:
    """Every name a module declares, including the methods of its classes."""
    names: set[str] = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
            if isinstance(node, ast.ClassDef):
                names |= {n.name for n in node.body
                          if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names |= {t.id for t in targets if isinstance(t, ast.Name)}
    return names


def test_debugger_is_split_by_subject() -> None:
    source = FACADE.read_text(encoding="utf-8")
    assert _line_count(FACADE) <= 90, "the facade assembles the class, it does not implement it"
    assert "def " not in source, "the facade holds no logic"
    assert "from .debugger_groups." in source

    modules = sorted(p.stem for p in PKG.glob("*.py") if p.stem != "__init__")
    assert modules == sorted(DEBUG_MODULES), modules
    for module in [*modules, "__init__"]:
        assert _line_count(PKG / f"{module}.py") <= 300, (
            f"vm/debugger_groups/{module}.py grew past one subject")

    homes: dict[str, str] = {}
    for module in modules:
        for name in _declared_names(PKG / f"{module}.py"):
            assert name not in homes, f"{name} is declared in two debugger groups"
            homes[name] = module
    assert homes == DEBUG_MEMBER_HOME, (
        "the debugger groups drifted from their declared subjects: "
        f"{sorted(set(homes.items()) ^ set(DEBUG_MEMBER_HOME.items()))}")

    # the assembler is a header and nothing else: its whole body is the mixin tuple
    assembler = next(n for n in ast.parse(source).body
                     if isinstance(n, ast.ClassDef) and n.name == "DebuggerMixin")
    assert [b.id for b in assembler.bases] == list(DEBUG_MIXINS), assembler.bases
    assert [type(n).__name__ for n in assembler.body] == ["Pass"], (
        "DebuggerMixin must define no method of its own")

    # layering: no group reaches another, the facade is the only assembler
    for module in modules:
        tree = ast.parse((PKG / f"{module}.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                dep = (node.module or "").split(".")[0]
                assert dep in DEBUG_LAYER_RANK, f"{module}.py imports unknown group {dep}"
                assert DEBUG_LAYER_RANK[dep] < DEBUG_LAYER_RANK[module], (
                    f"{module}.py imports {dep}, which is not below it")

    exported = {alias.name for node in ast.parse(source).body
                if isinstance(node, ast.ImportFrom)
                and (node.module or "").startswith("debugger_groups.")
                for alias in node.names}
    assert exported == set(DEBUG_MIXINS), sorted(exported ^ set(DEBUG_MIXINS))
    assert DEBUG_EXPORTS == {"DebuggerMixin"}

    # the assembled class merges each original method exactly once, from its home
    from mellowlang.vm import debugger as impl

    assert [c.__name__ for c in impl.DebuggerMixin.__mro__] == [
        "DebuggerMixin", *DEBUG_MIXINS, "object"]
    merged: list[str] = []
    for base in impl.DebuggerMixin.__mro__[1:-1]:
        merged += [name for name in vars(base) if not name.startswith("__")]
    assert sorted(merged) == sorted(DEBUG_METHODS), (
        "the assembled class does not hold the monolith's methods exactly once: "
        f"{sorted(set(merged) ^ DEBUG_METHODS)}")
    for method in DEBUG_METHODS:
        owner = getattr(impl.DebuggerMixin, method).__module__
        assert owner == f"mellowlang.vm.debugger_groups.{DEBUG_MEMBER_HOME[method]}", (
            method, owner)

    consumers = []
    for path in sorted(SRC.rglob("*.py")):
        if PKG in path.parents or path == FACADE:
            continue
        reaching = {node.module for node in ast.walk(
                        ast.parse(path.read_text(encoding="utf-8")))
                    if isinstance(node, ast.ImportFrom)
                    and (node.module or "").startswith("vm.debugger_groups")}
        if reaching:
            consumers.append((path.relative_to(SRC).as_posix(), sorted(reaching)))
    assert not consumers, f"import vm.debugger instead: {consumers}"
