"""The contract for the `ast.py` split.

`mellowlang/ast.py` was one 332-line module holding every syntax-tree node. It is
now a facade over `ast_nodes/`: `base.py` holds the three containers, and the two
node families live in `statements.py` and `expressions.py`, which may both import
base but never each other. Every class moved verbatim, and the facade stays at
`mellowlang/ast.py` so `from mellowlang.ast import ...` - and `parser.py`'s
`from .ast import *` - keep resolving.

This lives in its own module because the shared gate, `test_source_structure.py`,
sits at its declared ceiling - that file's own comment says the next subsystem's
contract moves out rather than the ceiling rising.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "mellowlang"
PKG = SRC / "ast_nodes"
FACADE = SRC / "ast.py"

PKG_MODULES = ("base", "statements", "expressions")
# A group may import only a subject strictly below it, which is also what stops
# the two node families from importing each other.
PKG_LAYER_RANK = {"base": 0, "statements": 1, "expressions": 1}
# Where each node must live, so the seams stay meaningful rather than merely small.
PKG_MEMBER_HOME = {
    "Program": "base", "Stmt": "base", "Expr": "base",
    "KeepStmt": "statements", "KeepMultiStmt": "statements", "AssignStmt": "statements",
    "ExprStmt": "statements", "ShowStmt": "statements", "PrecisionStmt": "statements",
    "StopStmt": "statements", "WaitStmt": "statements", "SaveStmt": "statements",
    "LoadStmt": "statements", "PutStmt": "statements", "ReturnStmt": "statements",
    "BreakStmt": "statements", "ContinueStmt": "statements", "TryStmt": "statements",
    "SkillDef": "statements", "IfGroup": "statements", "LoopWhile": "statements",
    "LoopForEach": "statements", "LoopForMap": "statements", "DoBlock": "statements",
    "LoopForRange": "statements", "RepeatUntil": "statements", "LoopCount": "statements",
    "OnDef": "statements", "GetModuleStmt": "statements", "ImportStmt": "statements",
    "SkillDefV2": "statements",
    "Literal": "expressions", "Var": "expressions", "UnaryOp": "expressions",
    "BinaryOp": "expressions", "Call": "expressions", "Index": "expressions",
    "ListLiteral": "expressions", "MapLiteral": "expressions", "FStringExpr": "expressions",
    "GetModuleExpr": "expressions", "CallValExpr": "expressions", "LambdaExpr": "expressions",
    "ListCompExpr": "expressions", "SpreadExpr": "expressions", "SliceExpr": "expressions",
}
# Every node type in ast.py is public: the parser, the compiler, the VM, the linter
# and the tests all import them, and `from .ast import *` re-exports the lot.
PKG_EXPORTS = set(PKG_MEMBER_HOME)
# Nothing in the package is private: the facade hands out every node it moved.
PKG_INTERNAL: set[str] = set()


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _declared_names(path: Path) -> set[str]:
    """Every name a module declares at module level."""
    names: set[str] = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names |= {t.id for t in targets if isinstance(t, ast.Name)}
    return names


def test_ast_is_split_by_node_family() -> None:
    source = FACADE.read_text(encoding="utf-8")
    assert _line_count(FACADE) <= 90, "the facade re-exports, it does not declare nodes"
    assert "def " not in source, "the facade holds no logic"
    assert "class " not in source, "the facade declares no types"
    assert "from .ast_nodes." in source

    modules = sorted(p.stem for p in PKG.glob("*.py") if p.stem != "__init__")
    assert modules == sorted(PKG_MODULES), modules
    for module in [*modules, "__init__"]:
        assert _line_count(PKG / f"{module}.py") <= 300, (
            f"ast_nodes/{module}.py grew past one node family")

    homes: dict[str, str] = {}
    for module in modules:
        for name in _declared_names(PKG / f"{module}.py"):
            assert name not in homes, f"{name} is declared in two node modules"
            homes[name] = module
    assert homes == PKG_MEMBER_HOME, (
        "the node modules drifted from their declared subjects: "
        f"{sorted(set(homes.items()) ^ set(PKG_MEMBER_HOME.items()))}")

    # layering: base only, and no sibling imports
    for module in modules:
        tree = ast.parse((PKG / f"{module}.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.ImportFrom) or not node.level:
                continue
            dep = (node.module or "").split(".")[0]
            assert node.level == 1, f"{module}.py imports outside the package: {node.module}"
            assert dep in PKG_LAYER_RANK, f"{module}.py imports unknown group {dep}"
            assert PKG_LAYER_RANK[dep] < PKG_LAYER_RANK[module], (
                f"{module}.py imports {dep}, which is not below it")

    exported = [alias.name for node in ast.parse(source).body
                if isinstance(node, ast.ImportFrom)
                and (node.module or "").startswith("ast_nodes.")
                for alias in node.names]
    assert len(exported) == len(set(exported)), "a node is exported twice"
    assert set(exported) == PKG_EXPORTS, sorted(set(exported) ^ PKG_EXPORTS)
    assert not (PKG_INTERNAL & set(exported)), "internal helpers stay inside the package"

    consumers = []
    for path in sorted(SRC.rglob("*.py")):
        if PKG in path.parents or path == FACADE:
            continue
        reaching = {node.module for node in ast.walk(
                        ast.parse(path.read_text(encoding="utf-8")))
                    if isinstance(node, ast.ImportFrom)
                    and (node.module or "").split(".")[0] == "ast_nodes"}
        if reaching:
            consumers.append((path.relative_to(SRC).as_posix(), sorted(reaching)))
    assert not consumers, f"import mellowlang.ast instead: {consumers}"


def test_ast_facade_does_not_shadow_the_stdlib_module() -> None:
    """`mellowlang/ast.py` must only shadow the name for relative imports."""
    stdlib = sys.modules.get("ast")
    assert stdlib is not None and stdlib.__file__ is not None
    assert not Path(stdlib.__file__).resolve().is_relative_to(SRC.resolve()), (
        f"`import ast` resolved to {stdlib.__file__}")
    import mellowlang.ast as facade

    assert Path(facade.__file__).resolve() == FACADE.resolve()
    assert facade is not stdlib
