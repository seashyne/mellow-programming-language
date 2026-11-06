"""The contract for the `agents/control_plane.py` split.

`agents/control_plane.py` was one 536-line module: the state file, the HTTP
transport, traffic splitting, deployment registration, inspection, rollouts,
metrics, autoscaling and alerts, all in one file. It is now a facade over
`control_plane_groups/`, one module per concern, with every declaration moved
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
PKG = SRC / "agents" / "control_plane_groups"
FACADE = SRC / "agents" / "control_plane.py"

PKG_MODULES = ("state", "transport", "traffic", "deploy", "inspection",
               "rollout", "metrics", "alerts", "observability")
# A group may import only a subject strictly below it. The state file and the HTTP
# transport are leaves; nothing below the facade knows about a deployment record.
PKG_LAYER_RANK = {
    "state": 0, "transport": 0,
    "traffic": 1, "metrics": 1,
    "deploy": 2, "inspection": 2, "rollout": 2, "alerts": 2,
    "observability": 3,
}
# Where each name must live, so the seams stay meaningful rather than merely small.
PKG_MEMBER_HOME = {
    "CONTROL_PLANE_HOME": "state", "_now_iso": "state", "_slugify": "state",
    "_state_path": "state", "_load_state": "state", "_save_state": "state",
    "_is_remote_control_plane": "transport", "_request_json": "transport",
    "_remote_url": "transport",
    "_normalize_split": "traffic", "_rev_status_for": "traffic",
    "_find_local_target": "traffic",
    "_ensure_revision": "deploy", "_upsert_local_deployment": "deploy",
    "register_deployment": "deploy", "sync_deployment": "deploy",
    "list_deployments": "inspection", "get_deployment_status": "inspection",
    "list_revisions": "inspection", "run_health_check": "inspection",
    "rollout_revision": "rollout", "update_traffic_split": "rollout",
    "rollback_deployment": "rollout",
    "_coerce_float": "metrics", "_coerce_int": "metrics",
    "_metrics_history_for": "metrics", "_compute_autoscaling_signals": "metrics",
    "_evaluate_alerts_local": "alerts",
    "record_deployment_metrics": "observability",
    "get_deployment_metrics": "observability",
    "get_autoscaling_signals": "observability",
    "set_alert_rules": "observability", "evaluate_alerts": "observability",
}
# The public surface `agents/__init__.py`, the CLI and the tests import.
PKG_EXPORTS = {name for name in PKG_MEMBER_HOME if not name.startswith("_")}
# Helpers that stay package-internal: no caller outside control_plane_groups/
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
            names |= {t.id for t in targets if isinstance(t, ast.Name)}
    return names


def test_control_plane_is_split_by_concern() -> None:
    source = FACADE.read_text(encoding="utf-8")
    assert _line_count(FACADE) <= 90, "the facade re-exports, it does not run anything"
    assert "def " not in source, "the facade holds no logic"
    assert "class " not in source, "the facade declares no types"
    assert "from .control_plane_groups." in source

    modules = sorted(p.stem for p in PKG.glob("*.py") if p.stem != "__init__")
    assert modules == sorted(PKG_MODULES), modules
    for module in [*modules, "__init__"]:
        assert _line_count(PKG / f"{module}.py") <= 300, (
            f"control_plane_groups/{module}.py grew past one concern")

    homes: dict[str, str] = {}
    for module in modules:
        for name in _declared_names(PKG / f"{module}.py"):
            assert name not in homes, f"{name} is declared in two control plane groups"
            homes[name] = module
    assert homes == PKG_MEMBER_HOME, (
        "the control plane groups drifted from their declared subjects: "
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
                and (node.module or "").startswith("control_plane_groups.")
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
                    and (node.module or "").split(".")[0] == "control_plane_groups"}
        if reaching:
            consumers.append((path.relative_to(SRC).as_posix(), sorted(reaching)))
    assert not consumers, f"import agents.control_plane instead: {consumers}"
