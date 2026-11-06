"""The contract for the `mellowlang/desktop_host.py` split.

`desktop_host.py` was one 471-line module: the window-spec parser, the action
vocabulary, the Tk/ttk runtime, the portable bundle builder and the status report,
all in one file. It is now a facade over `desktop_host_groups/`, one module per
concern, with every declaration moved verbatim.

This lives in its own module because the shared gate, `test_source_structure.py`,
sits at its declared ceiling - that file's own comment says the next subsystem's
contract moves out rather than the ceiling rising.
"""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "mellowlang"
PKG = SRC / "desktop_host_groups"
FACADE = SRC / "desktop_host.py"

PKG_MODULES = ("parsing", "actions", "files", "runtime", "bundle", "status")
# A group may import only a concern strictly below it. The spec parser, the bundle
# builder and the status report are leaves; the action vocabulary and the file
# helpers read parsed specs; the runtime drives the actions.
PKG_LAYER_RANK = {
    "parsing": 0, "bundle": 0, "status": 0,
    "actions": 1, "files": 1,
    "runtime": 2,
}
# Where each name must live, so the seams stay meaningful rather than merely small.
PKG_MEMBER_HOME = {
    "WINDOW_RE": "parsing", "CALL_RE": "parsing", "STATE_RE": "parsing",
    "_split_args": "parsing", "_parse_value": "parsing",
    "_extract_named_and_positional": "parsing", "_parse_state": "parsing",
    "parse_window_spec": "parsing",
    "_interpolate": "actions", "_apply_action": "actions",
    "parse_window_file": "files", "dump_spec_json": "files",
    "DesktopRuntime": "runtime", "launch_window": "runtime",
    "_portable_launcher_py": "bundle", "build_desktop_bundle": "bundle",
    "desktop_status": "status",
}
# The public surface `cli/commands/media.py` and the tests import.
PKG_EXPORTS = {name for name in PKG_MEMBER_HOME if not name.startswith("_")}
# Helpers that stay package-internal: no caller outside desktop_host_groups/
# reaches them.
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
            # bundle.py re-points `__file__` at the facade's directory so that
            # `build_desktop_bundle` keeps vendoring the package, not the groups.
            names |= {t.id for t in targets
                      if isinstance(t, ast.Name) and t.id != "__file__"}
    return names


def test_desktop_host_is_split_by_concern() -> None:
    source = FACADE.read_text(encoding="utf-8")
    assert _line_count(FACADE) <= 90, "the facade re-exports, it does not run anything"
    assert "def " not in source, "the facade holds no logic"
    assert "class " not in source, "the facade declares no types"
    assert "from .desktop_host_groups." in source

    modules = sorted(p.stem for p in PKG.glob("*.py") if p.stem != "__init__")
    assert modules == sorted(PKG_MODULES), modules
    for module in [*modules, "__init__"]:
        assert _line_count(PKG / f"{module}.py") <= 300, (
            f"desktop_host_groups/{module}.py grew past one concern")

    homes: dict[str, str] = {}
    for module in modules:
        for name in _declared_names(PKG / f"{module}.py"):
            assert name not in homes, f"{name} is declared in two desktop host groups"
            homes[name] = module
    assert homes == PKG_MEMBER_HOME, (
        "the desktop host groups drifted from their declared concerns: "
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
                and (node.module or "").startswith("desktop_host_groups.")
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
                    and (node.module or "").split(".")[0] == "desktop_host_groups"}
        if reaching:
            consumers.append((path.relative_to(SRC).as_posix(), sorted(reaching)))
    assert not consumers, f"import mellowlang.desktop_host instead: {consumers}"
