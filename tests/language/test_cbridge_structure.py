"""The contract for the `vm/cbridge.py` split.

`vm/cbridge.py` was one 363-line module: the native vocabulary, the storage
guards, the capability reporters, the host adapter and the two bytecode runners.
It is now a facade over `cbridge_groups/`, one module per concern, with every
declaration moved verbatim except one import-depth token in `_load_ext`.

This lives in its own module because the shared gate, `test_source_structure.py`,
sits at its declared ceiling - that file's own comment says the next subsystem's
contract moves out rather than the ceiling rising.
"""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "mellowlang"
PKG = SRC / "vm" / "cbridge_groups"
FACADE = SRC / "vm" / "cbridge.py"

PKG_MODULES = ("host", "native", "storage")
# The three groups are peers: none imports another, the facade is the only
# assembler.
PKG_LAYER_RANK = {"native": 0, "host": 0, "storage": 0}
# Where each declaration must live. The capability reporters and the runners stay
# in the facade because callers and tests patch `_load_ext` there, so their
# globals must remain this module's.
PKG_MEMBER_HOME = {
    "CVMUnsupportedOpcode": "native", "NativeRunResult": "native",
    "NativeExecutionRequiredError": "native", "_load_ext": "native",
    "NativeHostAdapter": "host",
    "_lock_native_storage_dir": "storage", "_storage_path_unsafe": "storage",
    "_validate_native_storage_bytecode": "storage",
    "c_vm_available": "facade", "c_vm_capabilities": "facade",
    "c_vm_debug_supported": "facade",
    "run_bytecode": "facade", "run_bytecode_ex": "facade",
}
PKG_EXPORTS = {name for name in PKG_MEMBER_HOME if not name.startswith("_")}
PKG_INTERNAL = {name for name in PKG_MEMBER_HOME if name.startswith("_")}
# The only modules a group may reach outside its own package (relative level 3).
PKG_OUTSIDE = {"native": set(), "host": {"data_core"}, "storage": {"constants"}}


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


def test_cbridge_is_split_by_concern() -> None:
    source = FACADE.read_text(encoding="utf-8")
    assert _line_count(FACADE) <= 170, (
        "the facade keeps the loader-facing public API, not the adapter internals")
    assert "from .cbridge_groups." in source

    modules = sorted(p.stem for p in PKG.glob("*.py") if p.stem != "__init__")
    assert modules == sorted(PKG_MODULES), modules
    for module in [*modules, "__init__"]:
        assert _line_count(PKG / f"{module}.py") <= 300, (
            f"vm/cbridge_groups/{module}.py grew past one concern")

    homes: dict[str, str] = {}
    for module in modules:
        for name in _declared_names(PKG / f"{module}.py"):
            assert name not in homes, f"{name} is declared in two cbridge groups"
            homes[name] = module
    facade_names = _declared_names(FACADE)
    assert facade_names == {name for name, home in PKG_MEMBER_HOME.items()
                            if home == "facade"}, sorted(facade_names)
    assert homes == {name: home for name, home in PKG_MEMBER_HOME.items()
                     if home != "facade"}, (
        "the cbridge groups drifted from their declared concerns: "
        f"{sorted(set(homes.items()) ^ set(PKG_MEMBER_HOME.items()))}")

    # layering: no group reaches a sibling, and outside imports stay declared
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
                assert node.level == 3 and dep in PKG_OUTSIDE[module], (
                    f"{module}.py imports outside the package and its siblings: {dep}")

    exported = {alias.name for node in ast.parse(source).body
                if isinstance(node, ast.ImportFrom)
                and (node.module or "").startswith("cbridge_groups.")
                for alias in node.names}
    assert exported == set(PKG_MEMBER_HOME) - facade_names, sorted(
        exported ^ (set(PKG_MEMBER_HOME) - facade_names))
    assert PKG_EXPORTS == {
        "CVMUnsupportedOpcode", "NativeRunResult", "NativeExecutionRequiredError",
        "NativeHostAdapter", "c_vm_available", "c_vm_capabilities",
        "c_vm_debug_supported", "run_bytecode", "run_bytecode_ex"}, sorted(PKG_EXPORTS)
    assert PKG_INTERNAL == {
        "_load_ext", "_lock_native_storage_dir", "_storage_path_unsafe",
        "_validate_native_storage_bytecode"}, sorted(PKG_INTERNAL)

    consumers = []
    for path in sorted(SRC.rglob("*.py")):
        if PKG in path.parents or path == FACADE:
            continue
        reaching = {node.module for node in ast.walk(
                        ast.parse(path.read_text(encoding="utf-8")))
                    if isinstance(node, ast.ImportFrom)
                    and (node.module or "").startswith("cbridge_groups")}
        if reaching:
            consumers.append((path.relative_to(SRC).as_posix(), sorted(reaching)))
    assert not consumers, f"import mellowlang.vm.cbridge instead: {consumers}"


def test_the_loader_is_the_only_authored_token() -> None:
    """The monolith sits in `mellowlang.vm`; the group sits one level deeper."""
    tree = ast.parse((PKG / "native.py").read_text(encoding="utf-8"))
    loader = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef) and node.name == "_load_ext")
    imports = [node for node in ast.walk(loader) if isinstance(node, ast.ImportFrom)]
    assert [(node.level, node.module, [a.name for a in node.names]) for node in imports] == [
        (3, None, ["_mellowvm"])], ast.dump(loader)
