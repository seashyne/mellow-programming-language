"""The contract for the `mellow run` / `test` / `record` / `replay` / `diff` split.

`cli/commands/runtime.py` was one 661-line module. It is now a facade over
`runtime_groups/`, one module per subject, plus the one extraction that could not be a
plain move: the 180-line `RunConfig` assembly inside the handler became
`build_run_config(s: RunSettings)`, which opens the settings into the handler's own names
so the assembly itself stayed byte-identical.

This lives in its own module because the shared gate, `test_source_structure.py`, sits at
its declared ceiling - that file's own comment says the next subsystem's contract moves
out rather than the ceiling rising.
"""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "mellowlang"
RT_GROUPS = SRC / "cli" / "commands" / "runtime_groups"
RT_FACADE = SRC / "cli" / "commands" / "runtime.py"

RT_MODULES = ("deps", "standalone", "run_config", "run", "suite", "golden")
# A group may import only a subject strictly below it: the record/replay/diff trio is the
# only thing that knows the handler, and nothing knows the suite.
RT_LAYER_RANK = {"deps": 0, "standalone": 1, "run_config": 1, "suite": 1,
                 "run": 2, "golden": 3}
# Where each name must live, so the seams stay meaningful rather than merely small.
RT_MEMBER_HOME = {
    "pkg_auto_fetch_for_run": "deps",
    "_standalone_mellow_binary": "standalone", "_can_use_standalone_native": "standalone",
    "_cmd_run": "run",
    "_iter_test_files": "suite", "_run_one_script": "suite", "_golden_output_for": "suite",
    "_cmd_test": "suite",
    "_cmd_replay": "golden", "_cmd_record": "golden", "_cmd_diff": "golden",
    # the extraction's own vocabulary, which nothing outside runtime_groups/ reaches for
    "RunSettings": "run_config", "build_run_config": "run_config",
}
# The five commands `cli/main.py` imports, plus the alias the facade re-exports.
RT_EXPORTS = {"_cmd_run", "_cmd_test", "_cmd_record", "_cmd_replay", "_cmd_diff",
              "pkg_auto_fetch_for_run"}
# Dead in the monolith, deleted rather than moved: nothing in the repository called it.
RT_DROPPED = "_project_root"


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


def test_cli_runtime_commands_are_split_by_subject() -> None:
    source = RT_FACADE.read_text(encoding="utf-8")
    assert _line_count(RT_FACADE) <= 30, "the facade re-exports, it does not run anything"
    assert "def " not in source, "the facade holds no logic"
    assert "class " not in source, "the facade declares no types"
    assert "from .runtime_groups." in source

    modules = sorted(p.stem for p in RT_GROUPS.glob("*.py") if p.stem != "__init__")
    assert modules == sorted(RT_MODULES), modules
    for module in [*modules, "__init__"]:
        assert _line_count(RT_GROUPS / f"{module}.py") <= 300, (
            f"runtime_groups/{module}.py grew past one subject")

    homes: dict[str, str] = {}
    for module in modules:
        for name in _declared_names(RT_GROUPS / f"{module}.py"):
            assert name not in homes, f"{name} is declared in two runtime groups"
            homes[name] = module
    assert homes == RT_MEMBER_HOME, (
        "the runtime groups drifted from their declared subjects: "
        f"{sorted(set(homes.items()) ^ set(RT_MEMBER_HOME.items()))}")

    # the settings and the assembly cannot drift apart: the first statements of
    # build_run_config open exactly the fields RunSettings declares, and the handler
    # hands over exactly those fields by keyword
    cfg_tree = ast.parse((RT_GROUPS / "run_config.py").read_text(encoding="utf-8"))
    settings = next(n for n in cfg_tree.body
                    if isinstance(n, ast.ClassDef) and n.name == "RunSettings")
    fields = [n.target.id for n in settings.body if isinstance(n, ast.AnnAssign)]
    assert fields, "RunSettings declares no fields"
    build = next(n for n in cfg_tree.body if isinstance(n, ast.FunctionDef))
    opened: list[str] = []
    for stmt in [s for s in build.body
                 if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]:
        if (isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Attribute)
                and getattr(stmt.value.value, "id", "") == "s"
                and stmt.targets[0].id == stmt.value.attr):
            opened.append(stmt.targets[0].id)
        else:
            break
    assert opened == fields, "the assembly unpacks fields RunSettings does not declare"
    run_src = (RT_GROUPS / "run.py").read_text(encoding="utf-8")
    assert "RunConfig(" not in run_src, "the assembly lives in run_config.py, not the handler"
    settings_call = next(n for n in ast.walk(ast.parse(run_src)) if isinstance(n, ast.Call)
                         and isinstance(n.func, ast.Name) and n.func.id == "RunSettings")
    assert [k.arg for k in settings_call.keywords] == fields, (
        "run.py passes a different set of settings than the assembly reads")
    assert all(isinstance(k.value, ast.Name) and k.arg == k.value.id
               for k in settings_call.keywords), "a keyword must carry the local of its name"

    # layering, then the facade's surface, then the only caller it is allowed to have
    for module in modules:
        tree = ast.parse((RT_GROUPS / f"{module}.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                dep = (node.module or "").split(".")[0]
                assert dep in RT_LAYER_RANK, f"{module}.py imports unknown group {dep}"
                assert RT_LAYER_RANK[dep] < RT_LAYER_RANK[module], (
                    f"{module}.py imports {dep}, which is not below it")

    exported = {alias.name for node in ast.parse(source).body
                if isinstance(node, ast.ImportFrom)
                and (node.module or "").startswith("runtime_groups.")
                for alias in node.names}
    assert exported == RT_EXPORTS, sorted(exported ^ RT_EXPORTS)
    assert RT_DROPPED not in homes and RT_DROPPED not in source
    consumers = []
    for path in sorted(SRC.rglob("*.py")):
        if RT_GROUPS in path.parents or path == RT_FACADE:
            continue
        reaching = {node.module for node in ast.walk(
                        ast.parse(path.read_text(encoding="utf-8")))
                    if isinstance(node, ast.ImportFrom)
                    and (node.module or "").split(".")[0] == "runtime_groups"}
        if reaching:
            consumers.append((path.relative_to(SRC).as_posix(), sorted(reaching)))
    assert not consumers, f"import commands.runtime instead: {consumers}"
