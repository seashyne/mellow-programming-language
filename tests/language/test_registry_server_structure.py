"""The contract for the `registry/server.py` split.

`src/mellowlang/registry/server.py` was one 446-line module: the manifest helpers,
the on-disk store, the HTTP handler and the launcher, all in one file. It is now a
facade over `server_groups/`, one module per concern, with every declaration moved
verbatim.

The facade is imports-only apart from the `if __name__ == "__main__"` guard, which
has to stay there: `python -m mellowlang.registry.server` executes the module itself,
and tests/test_v152_online_registry.py and tests/test_v153_public_registry.py spawn
exactly that.

This lives in its own module because the shared gate, `test_source_structure.py`,
sits at its declared ceiling - that file's own comment says the next subsystem's
contract moves out rather than the ceiling rising.
"""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "mellowlang"
PKG = SRC / "registry" / "server_groups"
FACADE = SRC / "registry" / "server.py"

PKG_MODULES = ("manifest", "store", "handler", "launch")
# A group may import only a subject strictly below it. The manifest helpers are the
# leaf; the store reads them, the handler drives the store, and only the launcher
# binds a server.
PKG_LAYER_RANK = {"manifest": 0, "store": 1, "handler": 2, "launch": 3}
# Where each name must live, so the seams stay meaningful rather than merely small.
PKG_MEMBER_HOME = {
    "_json_load": "manifest", "_authors_from_manifest": "manifest",
    "_creator_from_manifest": "manifest", "_list_from_manifest": "manifest",
    "_package_badges": "manifest",
    "RegistryStore": "store",
    "Handler": "handler",
    "run_registry_server": "launch", "main": "launch",
}
# The public surface `registry/__init__.py`, the `mellow pkg serve` command and
# `python -m mellowlang.registry.server` import.
PKG_EXPORTS = {name for name in PKG_MEMBER_HOME if not name.startswith("_")}
# Helpers that stay package-internal: no caller outside server_groups/ reaches them.
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


def test_registry_server_is_split_by_concern() -> None:
    source = FACADE.read_text(encoding="utf-8")
    assert _line_count(FACADE) <= 90, "the facade re-exports, it does not run anything"
    assert "def " not in source, "the facade holds no logic"
    assert "class " not in source, "the facade declares no types"
    assert "from .server_groups." in source
    # the one authored statement: `python -m mellowlang.registry.server` runs this
    # module as `__main__`, so the guard cannot live in a group module
    assert 'if __name__ == "__main__":' in source, "the facade keeps the -m guard"
    assert "raise SystemExit(main())" in source

    modules = sorted(p.stem for p in PKG.glob("*.py") if p.stem != "__init__")
    assert modules == sorted(PKG_MODULES), modules
    for module in [*modules, "__init__"]:
        assert _line_count(PKG / f"{module}.py") <= 300, (
            f"server_groups/{module}.py grew past one concern")

    homes: dict[str, str] = {}
    for module in modules:
        for name in _declared_names(PKG / f"{module}.py"):
            assert name not in homes, f"{name} is declared in two registry groups"
            homes[name] = module
    assert homes == PKG_MEMBER_HOME, (
        "the registry groups drifted from their declared subjects: "
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
                and (node.module or "").startswith("server_groups.")
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
                    and (node.module or "").split(".")[0] == "server_groups"}
        if reaching:
            consumers.append((path.relative_to(SRC).as_posix(), sorted(reaching)))
    assert not consumers, f"import registry.server instead: {consumers}"
