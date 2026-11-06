"""The contract for the `compiler/ir_lowering.py` split.

`ir_lowering.py` was one 597-line module: the lowering vocabulary, the two syscall
helpers, the machine that owns the instruction list, and both dispatch chains in one
class. It is now a facade over `compiler/lowering/`, one module per concern, with
`IRLowerer` assembled from a driver mixin plus one mixin per chain.

This lives in its own module because the shared gate, `test_source_structure.py`, sits
at its declared ceiling - that file's own comment says the next subsystem's contract
moves out rather than the ceiling rising.
"""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "mellowlang"
LOWERING = SRC / "compiler" / "lowering"
FACADE = SRC / "compiler" / "ir_lowering.py"

LOWER_MODULES = ("tables", "errors", "syscalls", "driver", "statements",
                 "expressions", "lowerer")
# A module may import only a subject strictly below it, so the vocabulary stays a leaf
# and the assembler is the only thing that knows all three mixins.
LOWER_LAYER_RANK = {"tables": 0, "errors": 0, "driver": 0, "syscalls": 1,
                    "statements": 2, "expressions": 2, "lowerer": 3}
# Where each name must live, so the seams stay meaningful rather than merely small.
LOWER_MEMBER_HOME = {
    "STDLIB_CALLS": "tables", "SYSCALL_ARGUMENTS": "tables",
    "UnsupportedLoweringError": "errors",
    "_module_syscall": "syscalls", "_bind_call_arguments": "syscalls",
    "_LoopCtx": "driver", "__init__": "driver", "lower": "driver", "emit": "driver",
    "pos": "driver", "new_label": "driver", "new_temp": "driver",
    "_stmt": "statements", "_expr": "expressions",
    "IRLowerer": "lowerer",
    # the mixin each module contributes to the assembled class
    "LoweringDriverMixin": "driver", "StatementMixin": "statements",
    "ExpressionMixin": "expressions",
}
# What `compiler.py` needs, plus the module-level names the monolith exposed.
LOWER_EXPORTS = {"IRLowerer", "UnsupportedLoweringError", "STDLIB_CALLS",
                 "SYSCALL_ARGUMENTS", "_LoopCtx", "_module_syscall",
                 "_bind_call_arguments"}
# Imported but never read in the monolith; not re-exported from the facade.
LOWER_DROPPED = "Optional"


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


def test_ir_lowering_is_split_by_concern() -> None:
    source = FACADE.read_text(encoding="utf-8")
    assert _line_count(FACADE) <= 20, "the facade re-exports, it does not run anything"
    assert "def " not in source, "the facade holds no logic"
    assert "class " not in source, "the facade declares no types"
    assert "from .lowering." in source

    modules = sorted(p.stem for p in LOWERING.glob("*.py") if p.stem != "__init__")
    assert modules == sorted(LOWER_MODULES), modules
    for module in [*modules, "__init__"]:
        assert _line_count(LOWERING / f"{module}.py") <= 300, (
            f"compiler/lowering/{module}.py grew past one concern")

    homes: dict[str, str] = {}
    for module in modules:
        for name in _declared_names(LOWERING / f"{module}.py"):
            assert name not in homes, f"{name} is declared in two lowering modules"
            homes[name] = module
    assert homes == LOWER_MEMBER_HOME, (
        "the lowering modules drifted from their declared concerns: "
        f"{sorted(set(homes.items()) ^ set(LOWER_MEMBER_HOME.items()))}")

    # the assembler is a header and nothing else: its whole body is the three mixins
    assembler = next(n for n in ast.parse(
        (LOWERING / "lowerer.py").read_text(encoding="utf-8")).body
        if isinstance(n, ast.ClassDef) and n.name == "IRLowerer")
    assert [b.id for b in assembler.bases] == [
        "LoweringDriverMixin", "StatementMixin", "ExpressionMixin"], assembler.bases
    assert [type(n).__name__ for n in assembler.body] == ["Pass"], (
        "IRLowerer must define no method of its own")

    # the machine methods and the two chains together are exactly the monolith's class,
    # and the class actually resolves them through its mixin bases
    from mellowlang.compiler import ir_lowering as impl

    assert [c.__name__ for c in impl.IRLowerer.__mro__[1:4]] == [
        "LoweringDriverMixin", "StatementMixin", "ExpressionMixin"]
    for method in ("__init__", "lower", "emit", "pos", "new_label", "new_temp",
                   "_stmt", "_expr"):
        owner = getattr(impl.IRLowerer, method).__module__
        assert owner.startswith("mellowlang.compiler.lowering."), (method, owner)
        assert owner.split(".")[-1] == LOWER_MEMBER_HOME[method], (method, owner)

    # layering, then the facade's surface, then the only caller it is allowed to have
    for module in modules:
        tree = ast.parse((LOWERING / f"{module}.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                dep = (node.module or "").split(".")[0]
                assert dep in LOWER_LAYER_RANK, f"{module}.py imports unknown module {dep}"
                assert LOWER_LAYER_RANK[dep] < LOWER_LAYER_RANK[module], (
                    f"{module}.py imports {dep}, which is not below it")

    exported = {alias.name for node in ast.parse(source).body
                if isinstance(node, ast.ImportFrom)
                and (node.module or "").startswith("lowering.")
                for alias in node.names}
    assert exported == LOWER_EXPORTS, sorted(exported ^ LOWER_EXPORTS)
    assert LOWER_DROPPED not in source
    consumers = []
    for path in sorted(SRC.rglob("*.py")):
        if LOWERING in path.parents or path == FACADE:
            continue
        reaching = {node.module for node in ast.walk(
                        ast.parse(path.read_text(encoding="utf-8")))
                    if isinstance(node, ast.ImportFrom)
                    and (node.module or "").startswith("compiler.lowering")}
        if reaching:
            consumers.append((path.relative_to(SRC).as_posix(), sorted(reaching)))
    assert not consumers, f"import compiler.ir_lowering instead: {consumers}"
