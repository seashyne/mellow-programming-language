"""The contract for the `lint.py` split.

`mellowlang/lint.py` was one 350-line module: the issue record, the builtin name
table, the scope chain, the AST visitor and the two entry points, all in one file.
It is now a facade over `lint_groups/`, one module per subject, with every
declaration moved verbatim.

This lives in its own module because the shared gate, `test_source_structure.py`,
sits at its declared ceiling - that file's own comment says the next subsystem's
contract moves out rather than the ceiling rising.
"""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "mellowlang"
PKG = SRC / "lint_groups"
FACADE = SRC / "lint.py"

PKG_MODULES = ("issues", "linter", "api")
# A group may import only a subject strictly below it. The issue record, the
# builtin table and the scope chain are leaves; the visitor knows no entry point.
PKG_LAYER_RANK = {"issues": 0, "linter": 1, "api": 2}
# Where each name must live, so the seams stay meaningful rather than merely small.
PKG_MEMBER_HOME = {
    "LintIssue": "issues", "_BUILTINS": "issues", "_VarInfo": "issues",
    "_Scope": "issues",
    "_Linter": "linter",
    "lint_source": "api", "format_source": "api",
}
# The public surface `diagnostics.py`, the LSP server, the CLI and the tests import.
PKG_EXPORTS = {name for name in PKG_MEMBER_HOME if not name.startswith("_")}
# Helpers that stay package-internal: no caller outside lint_groups/ reaches them.
PKG_INTERNAL = {name for name in PKG_MEMBER_HOME if name.startswith("_")}
# The only modules a group may reach outside its own package.
PKG_OUTSIDE = {"ast", "parser"}


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


def test_lint_is_split_by_subject() -> None:
    source = FACADE.read_text(encoding="utf-8")
    assert _line_count(FACADE) <= 90, "the facade re-exports, it does not run anything"
    assert "def " not in source, "the facade holds no logic"
    assert "class " not in source, "the facade declares no types"
    assert "from .lint_groups." in source

    modules = sorted(p.stem for p in PKG.glob("*.py") if p.stem != "__init__")
    assert modules == sorted(PKG_MODULES), modules
    for module in [*modules, "__init__"]:
        assert _line_count(PKG / f"{module}.py") <= 300, (
            f"lint_groups/{module}.py grew past one subject")

    homes: dict[str, str] = {}
    for module in modules:
        for name in _declared_names(PKG / f"{module}.py"):
            assert name not in homes, f"{name} is declared in two lint groups"
            homes[name] = module
    assert homes == PKG_MEMBER_HOME, (
        "the lint groups drifted from their declared subjects: "
        f"{sorted(set(homes.items()) ^ set(PKG_MEMBER_HOME.items()))}")

    # layering, then the facade's surface, then the only callers it is allowed to have
    for module in modules:
        tree = ast.parse((PKG / f"{module}.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.ImportFrom) or not node.level:
                continue
            dep = (node.module or "").split(".")[0]
            if node.level == 1:
                assert dep in PKG_LAYER_RANK, f"{module}.py imports unknown group {dep}"
                assert PKG_LAYER_RANK[dep] < PKG_LAYER_RANK[module], (
                    f"{module}.py imports {dep}, which is not below it")
            else:
                assert node.level == 2 and dep in PKG_OUTSIDE, (
                    f"{module}.py imports outside the package and its siblings: {dep}")

    exported = {alias.name for node in ast.parse(source).body
                if isinstance(node, ast.ImportFrom)
                and (node.module or "").startswith("lint_groups.")
                for alias in node.names}
    assert exported == PKG_EXPORTS, sorted(exported ^ PKG_EXPORTS)
    assert not (PKG_INTERNAL & exported), "internal helpers stay inside the package"

    consumers = []
    for path in sorted(SRC.rglob("*.py")):
        if PKG in path.parents or path == FACADE:
            continue
        reaching = {node.module for node in ast.walk(
                        ast.parse(path.read_text(encoding="utf-8")))
                    if isinstance(node, ast.ImportFrom)
                    and (node.module or "").split(".")[0] == "lint_groups"}
        if reaching:
            consumers.append((path.relative_to(SRC).as_posix(), sorted(reaching)))
    assert not consumers, f"import mellowlang.lint instead: {consumers}"
