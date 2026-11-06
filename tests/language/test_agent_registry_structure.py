"""The contract for the `agents/registry.py` split.

`agents/registry.py` was one 544-line module: the on-disk layout, hashing, manifest
signing, registry auth, the local catalog, archive building, the dependency graph,
the lockfile, installation and the HTTP client, all in one file. It is now a facade
over `registry_groups/`, one module per concern, with every declaration moved
verbatim.

This lives in its own module because the shared gate, `test_source_structure.py`,
sits at its declared ceiling - that file's own comment says the next subsystem's
contract moves out rather than the ceiling rising.
"""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "mellowlang"
RG = SRC / "agents" / "registry_groups"
FACADE = SRC / "agents" / "registry.py"

RG_MODULES = ("layout", "integrity", "auth", "catalog", "archive", "graph",
              "lock", "install", "remote")
# A group may import only a subject strictly below it. The on-disk layout and the
# hashing primitives sit at the bottom; the HTTP client is the only thing that knows
# how to install from a registry.
RG_LAYER_RANK = {
    "layout": 0, "integrity": 0,
    "auth": 1, "catalog": 1,
    "archive": 2, "graph": 2, "lock": 2,
    "install": 3,
    "remote": 4,
}
# Where each name must live, so the seams stay meaningful rather than merely small.
RG_MEMBER_HOME = {
    "AGENT_ROOT": "layout", "AGENT_REGISTRY_ROOT": "layout",
    "AGENT_INSTALLED_ROOT": "layout", "AGENT_CACHE_ROOT": "layout",
    "ARCHIVE_EXT": "layout", "LOCKFILE_NAME": "layout", "REPRO_ZIP_TIMESTAMP": "layout",
    "_agent_cache_root": "layout", "ensure_agent_dirs": "layout",
    "normalize_agent_name": "layout",
    "_canonical_json": "integrity", "_sha256_bytes": "integrity",
    "_sha256_file": "integrity", "_read_manifest_json": "integrity",
    "sign_agent_manifest": "integrity", "verify_agent_manifest_signature": "integrity",
    "get_agent_registry_url": "auth", "get_agent_auth_token": "auth",
    "set_agent_auth_token": "auth", "clear_agent_auth_token": "auth",
    "agent_registry_whoami": "auth",
    "agent_manifest_dict": "catalog", "list_local_agent_versions": "catalog",
    "search_agent_local": "catalog",
    "_iter_agent_files": "archive", "_write_reproducible_zip": "archive",
    "build_agent_archive": "archive", "publish_agent_from_dir": "archive",
    "_collect_graph_local": "graph", "agent_dependency_graph": "graph",
    "_local_archive_and_sha": "lock", "_resolve_local_lock_entries": "lock",
    "generate_agent_lock": "lock", "write_agent_lock": "lock", "read_agent_lock": "lock",
    "_extract_agent_archive": "install", "install_agent_package": "install",
    "install_agent_with_lock": "install", "load_installed_agent": "install",
    "search_agent_remote": "remote", "publish_agent_remote": "remote",
    "install_agent_remote": "remote",
}
# The public surface `agents/__init__.py` and the registry tests import.
RG_EXPORTS = {name for name in RG_MEMBER_HOME if not name.startswith("_")}
# Helpers that stay package-internal: no caller outside registry_groups/ reaches them.
RG_INTERNAL = {name for name in RG_MEMBER_HOME if name.startswith("_")}


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


def test_agent_registry_is_split_by_concern() -> None:
    source = FACADE.read_text(encoding="utf-8")
    assert _line_count(FACADE) <= 90, "the facade re-exports, it does not run anything"
    assert "def " not in source, "the facade holds no logic"
    assert "class " not in source, "the facade declares no types"
    assert "from .registry_groups." in source

    modules = sorted(p.stem for p in RG.glob("*.py") if p.stem != "__init__")
    assert modules == sorted(RG_MODULES), modules
    for module in [*modules, "__init__"]:
        assert _line_count(RG / f"{module}.py") <= 300, (
            f"registry_groups/{module}.py grew past one concern")

    homes: dict[str, str] = {}
    for module in modules:
        for name in _declared_names(RG / f"{module}.py"):
            assert name not in homes, f"{name} is declared in two registry groups"
            homes[name] = module
    assert homes == RG_MEMBER_HOME, (
        "the registry groups drifted from their declared subjects: "
        f"{sorted(set(homes.items()) ^ set(RG_MEMBER_HOME.items()))}")

    # layering, then the facade's surface, then the only callers it is allowed to have
    for module in modules:
        tree = ast.parse((RG / f"{module}.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                dep = (node.module or "").split(".")[0]
                assert dep in RG_LAYER_RANK, f"{module}.py imports unknown group {dep}"
                assert RG_LAYER_RANK[dep] < RG_LAYER_RANK[module], (
                    f"{module}.py imports {dep}, which is not below it")

    exported = {alias.name for node in ast.parse(source).body
                if isinstance(node, ast.ImportFrom)
                and (node.module or "").startswith("registry_groups.")
                for alias in node.names}
    assert exported == RG_EXPORTS, sorted(exported ^ RG_EXPORTS)
    assert not (RG_INTERNAL & exported), "internal helpers stay inside the package"

    consumers = []
    for path in sorted(SRC.rglob("*.py")):
        if RG in path.parents or path == FACADE:
            continue
        reaching = {node.module for node in ast.walk(
                        ast.parse(path.read_text(encoding="utf-8")))
                    if isinstance(node, ast.ImportFrom)
                    and (node.module or "").split(".")[0] == "registry_groups"}
        if reaching:
            consumers.append((path.relative_to(SRC).as_posix(), sorted(reaching)))
    assert not consumers, f"import agents.registry instead: {consumers}"
