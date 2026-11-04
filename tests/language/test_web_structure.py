"""The contract for the `mellowlang/web.py` split.

`web.py` was one 510-line module: the page/component model, the mellow-web source
parser, the TSX emitter, the React app scaffold and the dev-server entry points,
all in one file. It is now a facade over `web_groups/`, one module per stage, with
every declaration moved verbatim.

This lives in its own module because the shared gate, `test_source_structure.py`,
sits at its declared ceiling - that file's own comment says the next subsystem's
contract moves out rather than the ceiling rising.
"""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "mellowlang"
PKG = SRC / "web_groups"
FACADE = SRC / "web.py"

PKG_MODULES = ("model", "lexing", "values", "parsing", "emitting", "scaffold",
               "devserver")
# A stage may import only a stage strictly below it. The data model, the static
# React scaffold and the scalar conversions are leaves; the parser reads lexed
# lines, the emitter reads parsed nodes, and the dev server drives both.
PKG_LAYER_RANK = {
    "model": 0, "values": 0, "scaffold": 0,
    "lexing": 1,
    "parsing": 2,
    "emitting": 3,
    "devserver": 4,
}
# Where each name must live, so the seams stay meaningful rather than merely small.
PKG_MEMBER_HOME = {
    "MellowWebError": "model", "WebState": "model", "WebNode": "model",
    "WebComponent": "model",
    "_HEADER_RE": "lexing", "_STATE_RE": "lexing", "_CALL_RE": "lexing",
    "_IDENT_RE": "lexing", "_strip_imports_and_comments": "lexing",
    "_split_args": "lexing", "_split_top_level": "lexing",
    "_split_named_arg": "lexing",
    "_tsx_expr": "values", "_style_size": "values", "_setter_name": "values",
    "_is_quoted": "values", "_unquote": "values",
    "parse_web_source": "parsing", "_parse_nodes": "parsing",
    "_parse_node": "parsing",
    "emit_tsx": "emitting", "_emit_node": "emitting", "_node_to_jsx": "emitting",
    "_emit_props": "emitting", "_event_handler": "emitting", "_emit_text": "emitting",
    "_write_dev_file": "scaffold", "_dev_package_json": "scaffold",
    "_dev_index_html": "scaffold", "_dev_main_tsx": "scaffold",
    "_dev_tsconfig_json": "scaffold", "_dev_vite_config": "scaffold",
    "compile_file_to_tsx": "devserver", "prepare_react_dev_app": "devserver",
    "run_react_dev_app": "devserver",
}
# The public surface `cli/commands/web.py` and the tests import.
PKG_EXPORTS = {name for name in PKG_MEMBER_HOME if not name.startswith("_")}
# Helpers that stay package-internal: no caller outside web_groups/ reaches them.
PKG_INTERNAL = {name for name in PKG_MEMBER_HOME if name.startswith("_")}


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


def test_web_is_split_by_stage() -> None:
    source = FACADE.read_text(encoding="utf-8")
    assert _line_count(FACADE) <= 90, "the facade re-exports, it does not run anything"
    assert "def " not in source, "the facade holds no logic"
    assert "class " not in source, "the facade declares no types"
    assert "from .web_groups." in source

    modules = sorted(p.stem for p in PKG.glob("*.py") if p.stem != "__init__")
    assert modules == sorted(PKG_MODULES), modules
    for module in [*modules, "__init__"]:
        assert _line_count(PKG / f"{module}.py") <= 300, (
            f"web_groups/{module}.py grew past one stage")

    homes: dict[str, str] = {}
    for module in modules:
        for name in _declared_names(PKG / f"{module}.py"):
            assert name not in homes, f"{name} is declared in two web groups"
            homes[name] = module
    assert homes == PKG_MEMBER_HOME, (
        "the web groups drifted from their declared stages: "
        f"{sorted(set(homes.items()) ^ set(PKG_MEMBER_HOME.items()))}")

    # layering, then the facade's surface, then the only callers it is allowed to have
    for module in modules:
        tree = ast.parse((PKG / f"{module}.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                dep = (node.module or "").split(".")[0]
                assert dep in PKG_LAYER_RANK, f"{module}.py imports unknown group {dep}"
                assert PKG_LAYER_RANK[dep] < PKG_LAYER_RANK[module], (
                    f"{module}.py imports {dep}, which is not below it")

    exported = {alias.name for node in ast.parse(source).body
                if isinstance(node, ast.ImportFrom)
                and (node.module or "").startswith("web_groups.")
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
                    and (node.module or "").split(".")[0] == "web_groups"}
        if reaching:
            consumers.append((path.relative_to(SRC).as_posix(), sorted(reaching)))
    assert not consumers, f"import mellowlang.web instead: {consumers}"
