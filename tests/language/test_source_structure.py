from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "mellowlang"
NATIVE_VM = ROOT / "native" / "mellowvm" / "src"
STANDALONE = ROOT / "native" / "standalone" / "src"
HOST_FAMILIES = SRC / "host" / "families"
AI_FAMILIES = SRC / "ai"
OPTIMIZATIONS = SRC / "compiler" / "optimizations"
PARSING = SRC / "parsing"
INTERP = SRC / "vm" / "interp"
AGENT_GROUPS = SRC / "cli" / "commands" / "agent_groups"
SCHEDULING = SRC / "agents" / "scheduling"
MVI = SRC / "mvi"
FASTLANG = SRC / "fastlang"

# One module per IR pass section, plus the shared value types and the driver.
PASS_MODULES = ("graph", "folding", "dataflow", "rewrite", "gvn", "sccp", "loops",
                "cleanup", "exprs")
OPTIMIZER_VALUE_TYPES = ("BasicBlock", "ControlFlowGraph", "DominatorTree", "DefUseInfo",
                         "PhiNode", "SSAProgram", "OptimizationSummary", "_StackValue",
                         "_CONST_TOP")
# Where a pass must live, so the seams stay meaningful instead of merely small.
PASS_HOME = {
    "build_cfg": "graph", "build_dominator_tree": "graph", "build_def_use": "graph",
    "build_ssa": "graph", "_compute_dominance_frontier": "graph",
    "_constant_fold": "folding", "_cfg_dataflow_optimize": "dataflow",
    "_transfer_env": "dataflow", "_merge_envs": "dataflow", "_rewrite_block": "rewrite",
    "_global_value_numbering": "gvn", "_sccp_optimize": "sccp",
    "_loop_invariant_motion": "loops", "_simplify_jumps": "cleanup",
    "_eliminate_dead_code": "cleanup", "_remove_unused_labels": "cleanup",
    "_eval_binary": "exprs", "_eval_unary": "exprs", "_vars_in_expr": "exprs",
}

# parser.py is a facade over parsing/: three value layers (errors, line text, the
# expression parser) and the statement driver, whose long if-chain is one run
# method per stmt_* mixin. The run order is the order the chain tested them in.
PARSE_LAYER_MODULES = ("errors", "line_text", "expressions", "expression_atoms",
                       "expression_postfix", "block_core", "blocks")
PARSE_STATEMENT_MODULES = ("stmt_loops", "stmt_definitions", "stmt_control",
                           "stmt_bindings", "stmt_output", "stmt_calls")
PARSE_RUN_HOME = {
    "_run_scope_loops": "stmt_loops", "_run_loop_forms": "stmt_loops",
    "_run_definitions": "stmt_definitions",
    "_run_exceptions": "stmt_control", "_run_conditionals": "stmt_control",
    "_run_bindings": "stmt_bindings",
    "_run_output": "stmt_output", "_run_utility": "stmt_output",
    "_run_module_calls": "stmt_calls",
}

# python_vm.py is a facade over vm/interp/: the driver dispatches every opcode
# through the OP_HANDLERS table to one _exec_* family method, the CALL arm walks
# the storage builtins through STORAGE_GROUPS, and the frame/error/syscall/event
# helpers live beside them.
OP_FAMILY_MODULES = ("op_bindings", "op_math", "op_io", "op_collections",
                     "op_call", "op_control", "op_import")
STORAGE_GROUP_MODULES = ("call_save", "call_net", "call_fs")
INTERP_SUPPORT_MODULES = ("actions", "call_storage", "errors", "events", "execute",
                          "frame", "invocation", "syscalls", "vm")
# Where each dispatched family must live, so the seams stay meaningful rather
# than merely small.
OP_FAMILY_HOME = {
    "_exec_bindings": "op_bindings",
    "_exec_arithmetic": "op_math", "_exec_comparisons": "op_math", "_exec_mod_pow": "op_math",
    "_exec_output": "op_io", "_exec_interaction": "op_io", "_exec_persistence": "op_io",
    "_exec_collections": "op_collections", "_exec_list_ops": "op_collections",
    "_exec_call": "op_call", "_exec_syscall": "op_call", "_exec_first_class": "op_call",
    "_exec_try_frames": "op_control", "_exec_jumps": "op_control",
    "_exec_skill_return": "op_control",
    "_exec_import": "op_import",
}
STORAGE_GROUP_HOME = {
    "_call_save_builtins": "call_save",
    "_call_net_builtins": "call_net",
    "_call_fs_builtins": "call_fs",
}

# commands/agents.py is a facade over agent_groups/: deps.py holds the lazy import
# surface the handlers were written against, support.py the helpers more than one
# group needs, and the six command modules hold one subject each.
AGENT_SUPPORT_MODULES = ("deps", "support")
AGENT_COMMAND_MODULES = ("runtime", "lifecycle", "inspection", "serve",
                         "control_plane", "automation")
# Where each command handler must live, so the seams stay meaningful rather than
# merely small.
AGENT_COMMAND_HOME = {
    "_cmd_agent_run": "runtime", "_cmd_agent_workflow": "runtime",
    "_cmd_agent_demo": "runtime", "_cmd_agent_inspect_log": "runtime",
    "_cmd_agent_package_init": "lifecycle", "_cmd_agent_package_lock": "lifecycle",
    "_cmd_agent_package_build": "lifecycle", "_cmd_agent_package_publish": "lifecycle",
    "_cmd_agent_package_install": "lifecycle", "_cmd_agent_package_graph": "lifecycle",
    "_cmd_agent_package_search": "lifecycle", "_cmd_agent_registry_login": "lifecycle",
    "_cmd_agent_registry_logout": "lifecycle", "_cmd_agent_registry_whoami": "lifecycle",
    "_cmd_agent_secret": "lifecycle",
    "_cmd_agent_prompt": "inspection", "_cmd_agent_prompt_debug": "inspection",
    "_cmd_agent_trace": "inspection", "_cmd_agent_preview": "inspection",
    "_cmd_playground": "serve", "_cmd_agent_playground": "serve", "_cmd_agent_serve": "serve",
    "_cmd_agent_marketplace": "serve", "_cmd_agent_deploy": "serve",
    "_cmd_agent_control_plane": "control_plane", "_cmd_agent_policy_sign": "control_plane",
    "_cmd_agent_policy_verify": "control_plane",
    "_scheduled_job_callback": "automation", "_cmd_agent_schedule": "automation",
    "_cmd_agent_trigger": "automation", "_cmd_agent_webhook": "automation",
    "_cmd_agent_queue": "automation", "_cmd_agent_jobs": "automation",
    "_cmd_agent_runner": "automation",
}
# The helpers are shared, so they have a module of their own instead of a home
# inside whichever group added them first.
AGENT_SUPPORT_HOME = {
    "_load_rag_index": "support", "_make_agent_runtime": "support",
    "_agent_prompt_context": "support", "_run_agent_package": "support",
    "_print_graph": "support", "_resolve_agent_package_ref": "support",
    "_parse_jsonish": "support", "_parse_filters": "support", "_build_backoff": "support",
}

# agents/scheduler.py is a facade over scheduling/: paths.py owns the state dir and
# the small serialisation helpers, state.py owns every read and write of a scheduler
# file, cron.py and backoff.py are pure functions, then one module per subject.
SCHED_SUPPORT_MODULES = ("paths", "state", "cron", "backoff")
SCHED_SUBJECT_MODULES = ("jobs", "webhooks", "queue")
SCHED_DRIVER_MODULES = ("runner", "drain", "http_api")
# Where each function must live, so the seams stay meaningful rather than merely small.
SCHED_SUBJECT_HOME = {
    "_root": "paths", "_jobs_path": "paths", "_runner_path": "paths",
    "_triggers_path": "paths", "_queue_path": "paths", "_queue_log_path": "paths",
    "_dead_letter_path": "paths", "_webhooks_path": "paths", "_server_path": "paths",
    "_job_api_path": "paths", "_now_iso": "paths", "_parse_iso": "paths",
    "_append_jsonl": "paths", "_load_json": "paths", "_save_json": "paths",
    "_load_jobs": "state", "_save_jobs": "state", "_load_triggers": "state",
    "_save_triggers": "state", "_load_queue": "state", "_save_queue": "state",
    "_load_dead_letter": "state", "_save_dead_letter": "state",
    "_load_webhooks": "state", "_save_webhooks": "state",
    "_load_server_state": "state", "_save_server_state": "state",
    "_load_job_api_state": "state", "_save_job_api_state": "state",
    "_parse_field": "cron", "cron_matches": "cron", "next_run": "cron",
    "_normalize_backoff": "backoff", "_compute_backoff_delay_ms": "backoff",
    "add_job": "jobs", "list_jobs": "jobs", "add_trigger": "jobs",
    "list_triggers": "jobs",
    "add_webhook": "webhooks", "list_webhooks": "webhooks", "_filter_match": "webhooks",
    "emit_event": "webhooks", "receive_webhook": "webhooks",
    "_queue_item_from_trigger": "queue", "enqueue_job": "queue", "submit_job": "queue",
    "get_queue_item": "queue", "list_queue": "queue", "list_dead_letter": "queue",
    "_should_run": "runner", "run_due_jobs": "runner", "write_runner_status": "runner",
    "read_runner_status": "runner", "run_background_runner": "runner",
    "_move_to_dead_letter": "drain", "retry_queue_item": "drain",
    "_is_available": "drain", "_process_queue_item": "drain", "drain_queue": "drain",
    "read_queue_log": "drain", "queue_stats": "drain",
    "_read_request_payload": "http_api", "_json_response": "http_api",
    "start_webhook_server": "http_api", "read_webhook_server_status": "http_api",
    "read_job_api_status": "http_api",
}
# How far above the state dir each module sits. An import may only point downwards,
# which is what keeps a webhook from reaching into the runner that fires it.
SCHED_LAYER_RANK = {
    "paths": 0, "backoff": 0, "state": 1, "cron": 1, "jobs": 2, "queue": 2,
    "drain": 3, "webhooks": 3, "runner": 4, "http_api": 4,
}

# standalone_image.py is a facade over mvi/: the format and the tables it reads, the
# anchors under the project root, the accumulators one lowering carries, the steps that
# fill them, and the three entry points on top. The 391-line pass is a driver plus the
# named steps below, run in the order the monolith ran its blocks.
MVI_FORMAT_MODULES = ("ops", "format", "binary", "consts")
MVI_PASS_MODULES = ("state", "scopes", "emit", "entries", "lowering")
MVI_SURFACE_MODULES = ("compile",)
MVI_MODULES = (*MVI_FORMAT_MODULES, *MVI_PASS_MODULES, *MVI_SURFACE_MODULES)
# An import may only point at a module earlier in this order, which is what keeps the
# byte format from knowing anything about the pass that fills it.
MVI_LAYER_RANK = {name: index for index, name in enumerate(MVI_MODULES)}
# Where each member the monolith owned at module level must live.
MVI_MEMBER_HOME = {
    "MAGIC": "format", "VERSION": "format", "FunctionEntry": "format",
    "EventEntry": "format", "ModuleEntry": "format", "StandaloneImage": "format",
    "_pack_string": "format",
    "_STANDALONE_OPS": "ops", "_COMPARE_MAP": "ops", "_SYSCALL_NAME_MAP": "ops",
    "_project_root": "binary", "_standalone_binary": "binary",
    "_core_module_candidates": "binary",
    "_add_const": "consts", "_const_from_python": "consts", "_span_tuple": "consts",
    "compile_source_to_standalone_image": "compile",
    "compile_file_to_standalone_image": "compile", "run_standalone_image": "compile",
}
# Where each step cut out of the lowering function must live.
MVI_STEP_HOME = {
    "Lowering": "state",
    "rebuild_func_table": "scopes", "scan_func_scopes": "scopes",
    "emit_instruction": "emit",
    "build_function_entries": "entries", "seed_core_module": "entries",
    "remap_function_addresses": "entries", "rewrite_jump_targets": "entries",
    "dedupe_modules": "entries",
    "lower_compiled_to_standalone_image": "lowering",
}
# The two helpers the monolith nested inside the pass became methods of the accumulators,
# and the byte writer stayed a method of the image it writes.
MVI_METHOD_HOME = {
    "slot_for": ("state", "Lowering"), "enter_scope": ("state", "Lowering"),
    "to_bytes": ("format", "StandaloneImage"),
}

# fast_compiler.py is a facade over fastlang/: the Python prelude it emits, the name
# mangler, the three emitter mixins, the class that assembles them, and the runner.
# The monolith's methods already sat at class indentation, so each mixin is HEAD's text
# with no edit at all - which is only provable if the seams stay this shape.
FL_LEAF_MODULES = ("builtins", "names", "writer")
FL_EMITTER_MODULES = ("statements", "expressions")
FL_SURFACE_MODULES = ("transpiler", "runner")
FL_MODULES = (*FL_LEAF_MODULES, *FL_EMITTER_MODULES, *FL_SURFACE_MODULES)
# An import may only point at a module earlier in this order: an emitter knows the name
# mangler, never another emitter, and the runner knows only the transpiler.
FL_LAYER_RANK = {name: index for index, name in enumerate(FL_MODULES)}
# Where each member the monolith declared at module level must live.
FL_MEMBER_HOME = {"_MELLOW_BUILTINS_SRC": "builtins", "_py_name": "names",
                  "PyTranspiler": "transpiler", "FastRunner": "runner"}
# The class that used to hold every method is now assembled from these.
FL_MIXIN_HOME = {"WriterMixin": "writer", "StatementMixin": "statements",
                 "ExpressionMixin": "expressions"}
# Every method the monolith's two classes owned, by the module that now carries it.
FL_METHOD_HOME = {
    "WriterMixin._w": ("writer", "WriterMixin"),
    "WriterMixin._w_raw": ("writer", "WriterMixin"),
    "WriterMixin._new_tmp": ("writer", "WriterMixin"),
    "StatementMixin._stmt": ("statements", "StatementMixin"),
    "StatementMixin._skill_def": ("statements", "StatementMixin"),
    "StatementMixin._import_stmt": ("statements", "StatementMixin"),
    "ExpressionMixin._expr": ("expressions", "ExpressionMixin"),
    "ExpressionMixin._call_expr": ("expressions", "ExpressionMixin"),
    "PyTranspiler.__init__": ("transpiler", "PyTranspiler"),
    "PyTranspiler.transpile": ("transpiler", "PyTranspiler"),
    "FastRunner.__init__": ("runner", "FastRunner"),
    "FastRunner.run": ("runner", "FastRunner"),
}

# Any file longer than this must appear in LINE_CEILINGS, so a new oversized
# file is a deliberate decision instead of an accident.
FILE_LENGTH_LIMIT = 1_000
# Largest each long file may become. Lower the number when the file shrinks;
# never raise it to make this test pass - split the file instead.
LINE_CEILINGS: dict[str, int] = {
    "src/mellowlang/package_manager.py": 1_100,
    "native/mellowvm/src/mellowvm_exec.inc": 800,
    "native/mellowvm/src/mellowvm_module.c": 700,
    "native/mellowvm/src/mellowvm_storage.inc": 800,
    "native/mellowvm/src/mellowvm_syscalls.inc": 900,
    "native/standalone/src/mellowrt_core.c": 950,
    "native/standalone/src/mellowrt_ledger.c": 975,
    "native/standalone/src/mellowrt_storage.c": 1_000,
    "native/standalone/src/mellowrt_syscalls.c": 975,
    "tests/native/test_full_native_c_cli.py": 1_375,
    # This gate is one self-contained file on purpose: nothing under tests/ imports a
    # helper in-tree, and every declared boundary reads in one place. Each split adds its
    # tables and its contract, so the headroom is deliberate - when a further split
    # reaches past it, the per-subsystem split tests move to their own module rather
    # than the ceiling rising again.
    "tests/language/test_source_structure.py": 1_100,
}

LENGTH_SUFFIXES = {".py", ".c", ".h", ".inc"}
LENGTH_SCAN_ROOTS = ("src", "native", "tests", "stdlib", "benchmarks", "scripts", "sdk")
SKIP_PARTS = {"build", "node_modules", "dist", "__pycache__", ".venv"}


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _top_level_names(path: Path) -> set[str]:
    """Every name a module declares at module level."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names |= {t.id for t in targets if isinstance(t, ast.Name)}
    return names


def _functions(path: Path) -> list[str]:
    """The functions a module declares at module level, in source order."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _surface_names(path: Path) -> set[str]:
    """Everything a package hands out: its own declarations and its re-exports."""
    names = _top_level_names(path)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and not any(a.name == "*" for a in node.names):
            names |= {alias.asname or alias.name for alias in node.names}
    return names


def _long_files() -> dict[str, int]:
    sizes: dict[str, int] = {}
    for root_name in LENGTH_SCAN_ROOTS:
        for path in (ROOT / root_name).rglob("*"):
            if not path.is_file() or path.suffix not in LENGTH_SUFFIXES:
                continue
            if SKIP_PARTS & set(path.parts):
                continue
            relative = path.relative_to(ROOT).as_posix()
            sizes[relative] = _line_count(path)
    return sizes


def test_cli_entrypoint_stays_thin() -> None:
    path = SRC / "cli" / "main.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    functions = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    assert functions == ["main"]
    assert _line_count(path) <= 600


def test_large_subsystems_have_explicit_boundaries() -> None:
    sizes = _long_files()
    undeclared = sorted(
        f"{name} ({size} lines)"
        for name, size in sizes.items()
        if size > FILE_LENGTH_LIMIT and name not in LINE_CEILINGS
    )
    assert not undeclared, (
        "split along the workspace boundaries, or add a ceiling that is a real "
        f"decision: {undeclared}"
    )
    over_budget = sorted(
        f"{name}: {sizes[name]} > {ceiling}"
        for name, ceiling in LINE_CEILINGS.items()
        if name in sizes and sizes[name] > ceiling
    )
    assert not over_budget, f"these files grew past their declared ceiling: {over_budget}"
    missing = sorted(name for name in LINE_CEILINGS if name not in sizes)
    assert not missing, f"declared ceiling points at a file that no longer exists: {missing}"
    assert (SRC / "vm" / "debugger.py").is_file()
    assert (SRC / "vm" / "storage.py").is_file()


def test_host_syscall_registry_is_split_by_family() -> None:
    """The host registry is an assembler; syscall bodies live in host/families."""
    runtime = SRC / "host" / "runtime.py"
    assert _line_count(runtime) <= 120
    assert (SRC / "host" / "base.py").is_file()
    assert (HOST_FAMILIES / "support.py").is_file(), "shared arg predicates live here"

    families = sorted(
        path.stem for path in HOST_FAMILIES.glob("*.py") if path.stem != "__init__"
    )
    assert "support" in families
    assert len(families) >= 14, "syscall families were split out of runtime.py"

    assembler = runtime.read_text(encoding="utf-8")
    for family in families:
        if family == "support":
            continue
        assert f"register_{family}_functions" in assembler, f"{family} is not assembled"
        module = (HOST_FAMILIES / f"{family}.py").read_text(encoding="utf-8")
        assert f"def register_{family}_functions(" in module
    # no syscall is registered by the assembler except the trivial echo probe
    assert assembler.count("HostFunction(") == 1


def test_ai_engine_is_split_by_concern() -> None:
    """ai_core.py is a facade; the AI engine lives in ai/ concern modules."""
    facade = SRC / "ai_core.py"
    assert _line_count(facade) <= 200, "the facade re-exports, it does not implement"
    source = facade.read_text(encoding="utf-8")
    assert "def ai_" not in source
    assert "from .ai import" in source

    families = sorted(p.stem for p in AI_FAMILIES.glob("*.py") if p.stem != "__init__")
    for expected in ("state", "numerics", "network", "language_model", "models",
                     "sessions", "llm_api", "llm_service", "providers", "registration"):
        assert expected in families, f"ai/{expected}.py is missing"
    for family in families:
        assert _line_count(AI_FAMILIES / f"{family}.py") <= 300, f"ai/{family}.py grew back"

    # The mutable AI stores live in exactly one module, so a handler can never
    # write to a private copy of the registry.
    stores = ("_MODELS", "_LLM_MODELS", "_SESSIONS", "_RUNTIME_STATE", "_API_CONFIG")
    declared = re.compile(
        rf"^({'|'.join(stores)})[:=]", re.MULTILINE)
    state = (AI_FAMILIES / "state.py").read_text(encoding="utf-8")
    assert set(declared.findall(state)) == set(stores), "ai/state.py owns every store"
    for family in families:
        if family == "state":
            continue
        text = (AI_FAMILIES / f"{family}.py").read_text(encoding="utf-8")
        assert not declared.findall(text), f"a store is re-created in ai/{family}.py"

    # registration is the only place that binds AI syscalls
    assert "def register_ai_functions(" in (
        AI_FAMILIES / "registration.py").read_text(encoding="utf-8")
    for other in families:
        if other == "registration":
            continue
        assert "HostFunction(" not in (AI_FAMILIES / f"{other}.py").read_text(encoding="utf-8")


def test_optimizer_passes_are_split_by_pass() -> None:
    """compiler/optimizer.py is a facade; one module per pass lives in optimizations/."""
    facade = SRC / "compiler" / "optimizer.py"
    assert _line_count(facade) <= 200, "the facade re-exports, it does not implement"
    source = facade.read_text(encoding="utf-8")
    assert "def " not in source, "the facade holds no logic"
    assert "@dataclass" not in source, "the facade declares no types"
    assert "from .optimizations import" in source

    for module in PASS_MODULES + ("ir_data", "optimizer", "__init__"):
        path = OPTIMIZATIONS / f"{module}.py"
        assert path.is_file(), f"compiler/optimizations/{module}.py is missing"
        assert _line_count(path) <= 300, f"{module}.py grew past one pass"

    # the driver assembles the mixins and owns the pipeline and the op sets; it
    # carries no pass body of its own beyond optimize()
    driver = next(n for n in ast.parse(
        (OPTIMIZATIONS / "optimizer.py").read_text(encoding="utf-8")).body
        if isinstance(n, ast.ClassDef) and n.name == "IROptimizer")
    bases = sorted(ast.unparse(b) for b in driver.bases)
    assert len(bases) == len(PASS_MODULES), "one mixin per pass section"
    assert all(name.endswith("Mixin") for name in bases), bases
    methods = [n.name for n in driver.body if isinstance(n, ast.FunctionDef)]
    assert methods == ["optimize"], f"the driver only drives: {methods}"
    constants = [t.id for n in driver.body if isinstance(n, ast.Assign)
                 for t in n.targets if isinstance(t, ast.Name)]
    assert set(constants) >= {"TERMINATORS", "STORE_OPS", "BINARY_OPS", "UNARY_OPS",
                              "SIDE_EFFECT_BARRIERS"}, "the op sets stay on the driver"

    # every mixin module declares exactly the class the driver inherits
    homes: dict[str, str] = {}
    for module in PASS_MODULES:
        tree = ast.parse((OPTIMIZATIONS / f"{module}.py").read_text(encoding="utf-8"))
        classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
        assert len(classes) == 1, f"{module}.py declares {len(classes)} classes"
        assert classes[0].name in bases, f"{module}.py is not assembled into IROptimizer"
        for fn in classes[0].body:
            if isinstance(fn, ast.FunctionDef):
                assert fn.name not in homes, f"{fn.name} is defined in two pass modules"
                homes[fn.name] = module
    for method, module in PASS_HOME.items():
        assert homes.get(method) == module, (
            f"{method} belongs in compiler/optimizations/{module}.py, "
            f"found in {homes.get(method)}")

    # the shared IR value types are declared once, in ir_data.py
    data = ast.parse((OPTIMIZATIONS / "ir_data.py").read_text(encoding="utf-8"))
    declared = {n.name for n in data.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
    declared |= {t.id for n in data.body if isinstance(n, ast.Assign)
                 for t in n.targets if isinstance(t, ast.Name)}
    assert set(OPTIMIZER_VALUE_TYPES) <= declared, "ir_data.py owns the shared value types"
    for module in PASS_MODULES + ("optimizer",):
        tree = ast.parse((OPTIMIZATIONS / f"{module}.py").read_text(encoding="utf-8"))
        top = {n.name for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
        top |= {t.id for n in tree.body if isinstance(n, ast.Assign)
                for t in n.targets if isinstance(t, ast.Name)}
        assert not top & set(OPTIMIZER_VALUE_TYPES), f"{module}.py re-declares a value type"


def test_parser_grammar_is_split_by_layer() -> None:
    """parser.py is a facade; parsing/ holds the grammar, one run per stmt mixin."""
    facade = SRC / "parser.py"
    assert _line_count(facade) <= 200, "the facade re-exports, it does not implement"
    source = facade.read_text(encoding="utf-8")
    assert "def " not in source, "the facade holds no logic"
    assert "class " not in source, "the facade declares no types"
    assert "from .ast import *" in source, "the node re-export is part of the old surface"
    assert "from .parsing import" in source

    modules = sorted(p.stem for p in PARSING.glob("*.py") if p.stem != "__init__")
    assert modules == sorted([*PARSE_LAYER_MODULES, *PARSE_STATEMENT_MODULES]), modules
    for module in [*modules, "__init__"]:
        assert _line_count(PARSING / f"{module}.py") <= 300, (
            f"parsing/{module}.py grew past one grammar layer")

    # BLOCK_RUNS is data: it fixes the order the statement chain is tested in.
    core = ast.parse((PARSING / "block_core.py").read_text(encoding="utf-8"))
    runs = next(
        tuple(ast.literal_eval(value) for value in node.value.elts)
        for node in core.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(isinstance(t, ast.Name) and t.id == "BLOCK_RUNS"
                for t in ([node.target] if isinstance(node, ast.AnnAssign)
                          else node.targets))
    )
    assert len(runs) == len(set(runs)) == len(PARSE_RUN_HOME), runs

    # each run is declared once, by a mixin in the module holding its statements
    homes: dict[str, str] = {}
    owner: dict[str, str] = {}
    classes: dict[str, str] = {}
    for module in PARSE_STATEMENT_MODULES:
        tree = ast.parse((PARSING / f"{module}.py").read_text(encoding="utf-8"))
        for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
            classes[cls.name] = module
            methods = [n.name for n in cls.body if isinstance(n, ast.FunctionDef)]
            assert not {"__init__", "parse", "sub_block"} & set(methods), (
                f"{module}.py carries parser state, not just statements")
            for name in methods:
                if not name.startswith("_run_"):
                    continue
                assert name not in homes, f"{name} is defined in two statement modules"
                homes[name] = module
                owner[name] = cls.name
    assert sorted(homes) == sorted(runs), (
        f"BLOCK_RUNS and the mixins drifted apart: {sorted(set(homes) ^ set(runs))}")
    for run, module in PARSE_RUN_HOME.items():
        assert homes.get(run) == module, (
            f"{run} belongs in parsing/{module}.py, found in {homes.get(run)}")

    # blocks.py assembles the runs; the base owns the cursor and the driver loop
    blocks = ast.parse((PARSING / "blocks.py").read_text(encoding="utf-8"))
    parser_cls = next(n for n in blocks.body
                      if isinstance(n, ast.ClassDef) and n.name == "BlockParser")
    bases = [ast.unparse(b) for b in parser_cls.bases]
    assert bases == [owner[run] for run in runs] + ["BlockParserBase"], (
        "the assembly order must match BLOCK_RUNS")
    driver = next(n for n in core.body
                  if isinstance(n, ast.ClassDef) and n.name == "BlockParserBase")
    methods = [n.name for n in driver.body if isinstance(n, ast.FunctionDef)]
    assert set(methods) == {"__init__", "parse", "sub_block"}, methods
    assert set(_top_level_names(PARSING / "blocks.py")) >= {
        "BlockParser", "_parse_block", "parse_program"}
    for module in PARSE_STATEMENT_MODULES:
        text = (PARSING / f"{module}.py").read_text(encoding="utf-8")
        assert "from .blocks import" not in text, (
            f"{module}.py reaches back into the assembly - the runs stay below it")

    # the value layers are each declared once, in the layer that owns them
    layer_owner = {
        "ParseError": "errors",
        "ExprParser": "expressions", "PRECEDENCE": "expressions",
        "parse_expr": "expressions", "_expr_col": "line_text",
        "_split_top_level_commas": "line_text", "_collect_multiline_expr": "line_text",
        "_rewrite_modern_aliases": "line_text",
        "ExpressionAtomMixin": "expression_atoms",
        "ExpressionPostfixMixin": "expression_postfix",
        "_extract_cond": "block_core", "_consume_end": "block_core",
        "BlockParserBase": "block_core", "BLOCK_RUNS": "block_core",
    }
    for name, module in layer_owner.items():
        declared = [m for m in [*modules, "__init__"]
                    if name in _top_level_names(PARSING / f"{m}.py")]
        assert declared == [module], f"{name} is declared in {declared}, not only {module}.py"
    exprs = ast.parse((PARSING / "expressions.py").read_text(encoding="utf-8"))
    expr_cls = next(n for n in exprs.body
                    if isinstance(n, ast.ClassDef) and n.name == "ExprParser")
    assert sorted(ast.unparse(b) for b in expr_cls.bases) == [
        "ExpressionAtomMixin", "ExpressionPostfixMixin"], "the two expression halves assemble"


def test_vm_interpreter_is_split_by_family() -> None:
    """python_vm.py is a facade; vm/interp/ holds one module per opcode family."""
    facade = SRC / "vm" / "python_vm.py"
    assert _line_count(facade) <= 60, "the facade re-exports, it does not interpret"
    source = facade.read_text(encoding="utf-8")
    assert "def " not in source, "the facade holds no logic"
    assert "class " not in source, "the facade declares no types"
    assert "from .interp import MellowLangVM" in source

    modules = sorted(p.stem for p in INTERP.glob("*.py") if p.stem != "__init__")
    assert modules == sorted([*OP_FAMILY_MODULES, *STORAGE_GROUP_MODULES,
                              *INTERP_SUPPORT_MODULES]), modules
    for module in [*modules, "__init__"]:
        assert _line_count(INTERP / f"{module}.py") <= 300, (
            f"vm/interp/{module}.py grew past one family")

    # OP_HANDLERS is data: it fixes which family owns which opcode.
    execute = ast.parse((INTERP / "execute.py").read_text(encoding="utf-8"))
    execute_cls = next(n for n in execute.body
                       if isinstance(n, ast.ClassDef) and n.name == "ExecuteMixin")
    table = next(
        node.value for node in execute_cls.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "OP_HANDLERS" for t in node.targets)
    )
    assert isinstance(table, ast.Dict), "dispatch has to stay a table, not code"
    dispatch = {ast.unparse(key): ast.literal_eval(value)
                for key, value in zip(table.keys, table.values)}
    constants = ast.parse((SRC / "constants.py").read_text(encoding="utf-8"))
    op_cls = next(n for n in constants.body
                  if isinstance(n, ast.ClassDef) and n.name == "Op")
    op_names = {t.id for node in op_cls.body if isinstance(node, ast.Assign)
                for t in node.targets if isinstance(t, ast.Name)}
    assert all(key.startswith("Op.") for key in dispatch), "keys are opcodes"
    assert {key[3:] for key in dispatch} <= op_names, "dispatch invented an opcode"

    # every family is declared once, in the module that owns it, and dispatched
    homes: dict[str, str] = {}
    for module in [*OP_FAMILY_MODULES, *STORAGE_GROUP_MODULES]:
        tree = ast.parse((INTERP / f"{module}.py").read_text(encoding="utf-8"))
        for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
            methods = [n.name for n in cls.body if isinstance(n, ast.FunctionDef)]
            assert "__init__" not in methods, (
                f"{module}.py carries interpreter state, not just a family")
            for name in methods:
                if name.startswith("_exec_") or name.startswith("_call_"):
                    assert name not in homes, f"{name} is defined in two modules"
                    homes[name] = module
    assert homes == {**OP_FAMILY_HOME, **STORAGE_GROUP_HOME}, (
        f"the family modules drifted from their declared homes: "
        f"{set(homes.items()) ^ set({**OP_FAMILY_HOME, **STORAGE_GROUP_HOME}.items())}")
    assert set(dispatch.values()) == set(OP_FAMILY_HOME), (
        "a family method is declared but never dispatched, or dispatched but missing")
    assert len(table.keys) == len(dispatch), "an opcode is dispatched twice"
    for family, module in OP_FAMILY_HOME.items():
        cls = next(n for n in ast.parse((INTERP / f"{module}.py").read_text(encoding="utf-8")).body
                   if isinstance(n, ast.ClassDef))
        node = next(n for n in cls.body
                    if isinstance(n, ast.FunctionDef) and n.name == family)
        assert [a.arg for a in node.args.args] == ["self", "op", "instr"], (
            f"{family} must take the instruction the driver hands it")

    # the driver dispatches through the table and owns no opcode body
    driver = next(n for n in execute_cls.body
                  if isinstance(n, ast.FunctionDef) and n.name == "run")
    assert "self.OP_HANDLERS" in ast.unparse(driver), "run() must dispatch, not branch"
    assert not any(node.name.startswith("_exec_") for node in execute_cls.body
                   if isinstance(node, ast.FunctionDef)), (
        "execute.py drives the loop, the families hold the bodies")

    # STORAGE_GROUPS is data too: the order the CALL arm tests the name groups in
    storage = ast.parse((INTERP / "call_storage.py").read_text(encoding="utf-8"))
    groups = next(
        ast.literal_eval(node.value) for node in storage.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(isinstance(t, ast.Name) and t.id == "STORAGE_GROUPS"
                for t in ([node.target] if isinstance(node, ast.AnnAssign) else node.targets))
    )
    assert groups == tuple(STORAGE_GROUP_HOME), "the storage walk order changed"

    # vm.py assembles the mixins; the host mixins stay behind the interpreter's own
    assembly = ast.parse((INTERP / "vm.py").read_text(encoding="utf-8"))
    vm_cls = next(n for n in assembly.body
                  if isinstance(n, ast.ClassDef) and n.name == "MellowLangVM")
    bases = [ast.unparse(b) for b in vm_cls.bases]
    assert bases[-2:] == ["DebuggerMixin", "StorageMixin"], (
        "the vm/ mixins the host already ships must stay last in the MRO")
    declared_mixins = {}
    for module in [*OP_FAMILY_MODULES, *STORAGE_GROUP_MODULES, *INTERP_SUPPORT_MODULES]:
        if module in ("vm", "actions"):
            continue        # vm.py assembles, actions.py holds the sentinels
        tree = ast.parse((INTERP / f"{module}.py").read_text(encoding="utf-8"))
        classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
        assert len(classes) == 1, f"{module}.py declares {classes}, one class was expected"
        assert classes[0].endswith("Mixin"), f"{module}.py is not a mixin"
        declared_mixins[classes[0]] = module
    assert sorted(bases[:-2]) == sorted(declared_mixins), (
        "the assembly imports exactly the mixins the modules declare")
    assert len(bases) == len(set(bases)), "a mixin is assembled twice"
    for name, module in STORAGE_GROUP_HOME.items():
        cls = next(n for n in ast.parse((INTERP / f"{module}.py").read_text(encoding="utf-8")).body
                   if isinstance(n, ast.ClassDef))
        node = next(n for n in cls.body
                    if isinstance(n, ast.FunctionDef) and n.name == name)
        assert [a.arg for a in node.args.args] == ["self", "f_name", "args", "kwargs"], (
            f"{name} must take the name the storage walk is testing")

    # the action sentinels are shared values, defined once, never re-created
    for sentinel in ("_PASS", "_STEP", "_NEXT", "_HALT"):
        declared = [m for m in modules if sentinel in _top_level_names(INTERP / f"{m}.py")]
        assert declared == ["actions"], f"{sentinel} is declared in {declared}"
    assert "MellowLangVM" in _top_level_names(INTERP / "vm.py")
    for module in [*OP_FAMILY_MODULES, *STORAGE_GROUP_MODULES]:
        text = (INTERP / f"{module}.py").read_text(encoding="utf-8")
        assert "from .vm import" not in text and "python_vm" not in text, (
            f"{module}.py reaches back into the assembly")


def test_cli_agent_commands_are_split_by_group() -> None:
    """commands/agents.py is a facade; agent_groups/ holds one module per subject."""
    facade = SRC / "cli" / "commands" / "agents.py"
    assert _line_count(facade) <= 60, "the facade re-exports, it does not implement"
    source = facade.read_text(encoding="utf-8")
    assert "def " not in source, "the facade holds no logic"
    assert "class " not in source, "the facade declares no types"
    assert "from .agent_groups.deps import" in source

    modules = sorted(p.stem for p in AGENT_GROUPS.glob("*.py") if p.stem != "__init__")
    assert modules == sorted([*AGENT_SUPPORT_MODULES, *AGENT_COMMAND_MODULES]), modules
    for module in [*modules, "__init__"]:
        assert _line_count(AGENT_GROUPS / f"{module}.py") <= 300, (
            f"agent_groups/{module}.py grew past one subject")

    # every handler is declared once, in the group that owns its subject
    homes: dict[str, str] = {}
    for module in [*AGENT_SUPPORT_MODULES, *AGENT_COMMAND_MODULES]:
        for name in _functions(AGENT_GROUPS / f"{module}.py"):
            assert name not in homes, f"{name} is defined in two agent modules"
            homes[name] = module
    expected = {**AGENT_COMMAND_HOME, **AGENT_SUPPORT_HOME}
    assert homes == expected, (
        "the agent groups drifted from their declared subjects: "
        f"{sorted(set(homes.items()) ^ set(expected.items()))}")

    # the facade re-exports the whole surface the split moved, and nothing else, so
    # `mellowlang.cli.main` and the tests keep importing every name from agents.py
    exported = {alias.name for node in ast.parse(source).body
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("agent_groups.")
                for alias in node.names}
    declared = {name for module in modules
                for name in _top_level_names(AGENT_GROUPS / f"{module}.py")}
    assert exported == declared, (
        f"the facade drifted from the group modules: {sorted(exported ^ declared)}")
    main = ast.parse((SRC / "cli" / "main.py").read_text(encoding="utf-8"))
    needed = {alias.name for node in main.body if isinstance(node, ast.ImportFrom)
              and node.level == 1 and node.module == "commands.agents" for alias in node.names}
    assert needed and needed <= exported, "the CLI entry point lost an agent handler"
    handlers = {n for n in AGENT_COMMAND_HOME if n.startswith("_cmd_")}
    assert handlers <= needed, (
        f"an agent handler is not wired into the CLI: {sorted(handlers - needed)}")

    # deps.py is the lazy import surface, and nothing else: no handler body lives there
    assert not _functions(AGENT_GROUPS / "deps.py"), "deps.py holds aliases, not commands"

    # layering: a command group may use deps and support, never a sibling group -
    # that is what keeps one subject from reaching into another's private state
    for module in AGENT_COMMAND_MODULES:
        text = (AGENT_GROUPS / f"{module}.py").read_text(encoding="utf-8")
        for sibling in AGENT_COMMAND_MODULES:
            assert f"from .{sibling} import" not in text, (
                f"{module}.py reaches into the {sibling} group instead of its own subject")
    deps_text = (AGENT_GROUPS / "deps.py").read_text(encoding="utf-8")
    for module in [*AGENT_SUPPORT_MODULES, *AGENT_COMMAND_MODULES][1:]:
        assert f"from .{module} import" not in deps_text, "deps.py is the bottom layer"

    # every alias points at a name the target package still hands out, so a renamed
    # agent builtin fails here rather than inside a command handler at run time
    aliases: dict[str, str] = {}
    body = [n for n in ast.parse(deps_text).body
            if not isinstance(n, (ast.Import, ast.ImportFrom))]
    assert isinstance(body[0], ast.Expr), "deps.py opens with a docstring, then aliases only"
    for node in body[1:]:
        assert isinstance(node, ast.Assign) and len(node.targets) == 1, (
            "deps.py holds one assignment per alias")
        name = node.targets[0]
        assert isinstance(name, ast.Name), "deps.py aliases are module-level names"
        if isinstance(node.value, ast.Constant):
            assert name.id == "_AG", f"deps.py/{name.id} is not an alias"
            aliases["_AG"] = node.value.value
            continue
        call = node.value
        assert (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                and call.func.id == "_lazy_attr" and len(call.args) == 2), (
            f"deps.py/{name.id} is not a lazy alias")
        package = call.args[0]
        package = (package.value if isinstance(package, ast.Constant)
                   else aliases.get(getattr(package, "id", ""), ""))
        attr = ast.literal_eval(call.args[1])
        assert isinstance(package, str) and isinstance(attr, str), f"deps.py/{name.id}"
        target = SRC.joinpath(*package.split(".")[1:])
        init = target / "__init__.py"
        target = init if init.is_file() else target.with_suffix(".py")
        assert target.is_file(), f"{package} has no module to check"
        assert attr in _surface_names(target), f"{package} no longer exports {attr}"


def test_agents_scheduler_is_split_by_subject() -> None:
    """agents/scheduler.py is a facade; scheduling/ holds one module per subject."""
    facade = SRC / "agents" / "scheduler.py"
    assert _line_count(facade) <= 120, "the facade re-exports, it does not schedule"
    source = facade.read_text(encoding="utf-8")
    assert "def " not in source, "the facade holds no logic"
    assert "class " not in source, "the facade declares no types"
    assert "from .scheduling." in source

    modules = sorted(p.stem for p in SCHEDULING.glob("*.py") if p.stem != "__init__")
    assert modules == sorted([*SCHED_SUPPORT_MODULES, *SCHED_SUBJECT_MODULES,
                              *SCHED_DRIVER_MODULES]), modules
    for module in [*modules, "__init__"]:
        assert _line_count(SCHEDULING / f"{module}.py") <= 300, (
            f"agents/scheduling/{module}.py grew past one subject")

    # every function is declared once, in the module that owns its subject
    homes: dict[str, str] = {}
    for module in modules:
        for name in _functions(SCHEDULING / f"{module}.py"):
            assert name not in homes, f"{name} is defined in two scheduling modules"
            homes[name] = module
    assert homes == SCHED_SUBJECT_HOME, (
        "the scheduling modules drifted from their declared subjects: "
        f"{sorted(set(homes.items()) ^ set(SCHED_SUBJECT_HOME.items()))}")

    # the state dir is a fact of one module, so a subject cannot invent a second one
    where = [m for m in modules if "SCHEDULER_HOME" in _top_level_names(SCHEDULING / f"{m}.py")]
    assert where == ["paths"], f"SCHEDULER_HOME is declared in {where}"

    # the facade re-exports the whole surface the split moved, and nothing else, so
    # `mellowlang.agents` and the tests keep importing every name from scheduler.py
    exported = {alias.name for node in ast.parse(source).body
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("scheduling.")
                for alias in node.names}
    declared = {name for module in modules
                for name in _top_level_names(SCHEDULING / f"{module}.py")}
    assert exported == declared, (
        f"the facade drifted from the subject modules: {sorted(exported ^ declared)}")

    init = ast.parse((SRC / "agents" / "__init__.py").read_text(encoding="utf-8"))
    needed = {alias.name for node in init.body if isinstance(node, ast.ImportFrom)
              and node.level == 1 and node.module == "scheduler" for alias in node.names}
    assert needed and needed <= exported, "the agents package lost a scheduler entry point"
    for test in sorted((ROOT / "tests").rglob("test_*.py")):
        tree = ast.parse(test.read_text(encoding="utf-8"))
        imported = {alias.name for node in tree.body if isinstance(node, ast.ImportFrom)
                    and node.module == "mellowlang.agents.scheduler" for alias in node.names}
        assert imported <= exported, (
            f"{test.name} imports {sorted(imported - exported)} from the facade")

    # layering: a module may only import from a layer below it, never a peer or the
    # driver above it - that is what stops a webhook from reaching into the runner
    # that fires it, and what keeps the package free of import cycles
    for module in modules:
        tree = ast.parse((SCHEDULING / f"{module}.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if not (isinstance(node, ast.ImportFrom) and node.level == 1):
                continue
            dep = (node.module or "").split(".")[0]
            assert dep in SCHED_LAYER_RANK, (
                f"{module}.py imports .{node.module}, which is not a subject module")
            assert SCHED_LAYER_RANK[dep] < SCHED_LAYER_RANK[module], (
                f"{module}.py imports {dep}, which is not a layer below it")


def test_standalone_image_format_is_split_by_concern() -> None:
    """standalone_image.py is a facade; mvi/ holds the format, the pass and the surface."""
    facade = SRC / "standalone_image.py"
    assert _line_count(facade) <= 40, "the facade re-exports, it does not lower"
    source = facade.read_text(encoding="utf-8")
    assert "def " not in source, "the facade holds no logic"
    assert "class " not in source, "the facade declares no types"
    assert "from .mvi." in source

    modules = sorted(p.stem for p in MVI.glob("*.py") if p.stem != "__init__")
    assert modules == sorted(MVI_MODULES), modules
    for module in [*modules, "__init__"]:
        assert _line_count(MVI / f"{module}.py") <= 300, (
            f"mvi/{module}.py grew past one concern")

    # every module-level name the monolith owned is declared once, in the module
    # that owns its concern
    homes: dict[str, str] = {}
    for module in modules:
        for name in _top_level_names(MVI / f"{module}.py"):
            assert name not in homes, f"{name} is declared in two mvi modules"
            homes[name] = module
    assert homes == {**MVI_MEMBER_HOME, **MVI_STEP_HOME}, (
        "the mvi modules drifted from their declared concerns: "
        f"{sorted(set(homes.items()) ^ set({**MVI_MEMBER_HOME, **MVI_STEP_HOME}.items()))}")

    # the pass carries its accumulators on one state object, because the monolith's
    # 391-line body shared them across every block - a step that grew its own copy
    # would lose the writes the next step reads
    state_tree = ast.parse((MVI / "state.py").read_text(encoding="utf-8"))
    lowering = next(n for n in state_tree.body
                    if isinstance(n, ast.ClassDef) and n.name == "Lowering")
    fields = [n.target.id for n in lowering.body if isinstance(n, ast.AnnAssign)]
    assert len(fields) == len(set(fields)) == 19, f"Lowering declares {fields}"
    for name, (module, owner) in MVI_METHOD_HOME.items():
        tree = ast.parse((MVI / f"{module}.py").read_text(encoding="utf-8"))
        holder = next((n for n in tree.body
                       if isinstance(n, ast.ClassDef) and n.name == owner), None)
        assert holder is not None, f"{module}.py no longer declares {owner}"
        assert name in [n.name for n in holder.body if isinstance(n, ast.FunctionDef)], (
            f"{name} is not a method of {owner}")

    # the driver stays a driver: the opcode chain it used to hold inline is emit.py
    driver = _functions(MVI / "lowering.py")
    assert driver == ["lower_compiled_to_standalone_image"], driver
    assert "elif op ==" not in (MVI / "lowering.py").read_text(encoding="utf-8"), (
        "the opcode chain leaked back into the driver")

    # layering: a module may only import a concern earlier in MVI_MODULES, never a
    # peer or the pass above it - that is what keeps the byte format from knowing
    # anything about the lowering that fills it
    for module in modules:
        tree = ast.parse((MVI / f"{module}.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if not (isinstance(node, ast.ImportFrom) and node.level == 1):
                continue
            dep = (node.module or "").split(".")[0]
            assert dep in MVI_LAYER_RANK, (
                f"{module}.py imports .{node.module}, which is not an mvi module")
            assert MVI_LAYER_RANK[dep] < MVI_LAYER_RANK[module], (
                f"{module}.py imports {dep}, which is not a layer below it")

    # the facade hands out the surface callers need and nothing of the pass internals
    exported = {alias.name for node in ast.parse(source).body
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("mvi.")
                for alias in node.names}
    internals = set(MVI_STEP_HOME) - {"lower_compiled_to_standalone_image"}
    assert exported == set(homes) - internals, (
        f"the facade drifted from the mvi modules: {sorted(exported ^ (set(homes) - internals))}")

    # and only the facade reaches into the package, so `mellowlang.standalone_image`
    # stays the one import path for the image format
    for path in sorted(SRC.rglob("*.py")):
        if MVI in path.parents or path == facade:
            continue
        reaching = {node.module for node in ast.walk(
                        ast.parse(path.read_text(encoding="utf-8")))
                    if isinstance(node, ast.ImportFrom)
                    and (node.module or "").split(".")[0] == "mvi"}
        assert not reaching, f"{path.name} imports {sorted(reaching)}; use standalone_image"


def test_fast_compiler_is_split_by_concern() -> None:
    """fast_compiler.py is a facade; fastlang/ holds the prelude, the emitters, the runner."""
    facade = SRC / "fast_compiler.py"
    assert _line_count(facade) <= 30, "the facade re-exports, it does not transpile"
    source = facade.read_text(encoding="utf-8")
    assert "def " not in source, "the facade holds no logic"
    assert "class " not in source, "the facade declares no types"
    assert "from .fastlang." in source

    modules = sorted(p.stem for p in FASTLANG.glob("*.py") if p.stem != "__init__")
    assert modules == sorted(FL_MODULES), modules
    for module in [*modules, "__init__"]:
        assert _line_count(FASTLANG / f"{module}.py") <= 300, (
            f"fastlang/{module}.py grew past one concern")

    # every module-level name the monolith declared is declared once, in the module that
    # owns its concern - and the mixins are not re-exported, so no caller can rebuild the
    # transpiler from a subset of its emitters
    homes: dict[str, str] = {}
    for module in modules:
        for name in _top_level_names(FASTLANG / f"{module}.py"):
            assert name not in homes, f"{name} is declared in two fastlang modules"
            homes[name] = module
    assert homes == {**FL_MEMBER_HOME, **FL_MIXIN_HOME}, (
        "the fastlang modules drifted from their declared concerns: "
        f"{sorted(set(homes.items()) ^ set({**FL_MEMBER_HOME, **FL_MIXIN_HOME}.items()))}")

    # the class the CLI imports is assembled from exactly the three emitters, in order,
    # and each method still sits on the mixin that owned it in the monolith
    def methods(path: Path, owner: str) -> list[str]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        holder = next((n for n in tree.body
                       if isinstance(n, ast.ClassDef) and n.name == owner), None)
        assert holder is not None, f"{path.name} no longer declares {owner}"
        return [n.name for n in holder.body if isinstance(n, ast.FunctionDef)]

    tp_tree = ast.parse((FASTLANG / "transpiler.py").read_text(encoding="utf-8"))
    tp_class = next(n for n in tp_tree.body
                    if isinstance(n, ast.ClassDef) and n.name == "PyTranspiler")
    assert [b.id for b in tp_class.bases] == [
        "WriterMixin", "StatementMixin", "ExpressionMixin"], (
        f"PyTranspiler assembles {[ast.unparse(b) for b in tp_class.bases]}")
    assert methods(FASTLANG / "transpiler.py", "PyTranspiler") == ["__init__", "transpile"]
    for dotted, (module, owner) in FL_METHOD_HOME.items():
        assert dotted.split(".")[1] in methods(FASTLANG / f"{module}.py", owner), (
            f"{dotted} is not a method of {owner} in fastlang/{module}.py")

    # the driver assembles and delegates; the two dispatch chains live in their own
    # modules and never leak back into the class header or transpile()
    transpiler_src = (FASTLANG / "transpiler.py").read_text(encoding="utf-8")
    assert "isinstance(s," not in transpiler_src and "isinstance(e," not in transpiler_src
    assert "isinstance(s," in (FASTLANG / "statements.py").read_text(encoding="utf-8")
    assert "isinstance(e," in (FASTLANG / "expressions.py").read_text(encoding="utf-8")

    # layering: an emitter may reach the name mangler and nothing else of its peers,
    # so a statement form and an expression form cannot start sharing state
    for module in modules:
        tree = ast.parse((FASTLANG / f"{module}.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if not (isinstance(node, ast.ImportFrom) and node.level == 1):
                continue
            dep = (node.module or "").split(".")[0]
            assert dep in FL_LAYER_RANK, (
                f"{module}.py imports .{node.module}, which is not a fastlang module")
            assert FL_LAYER_RANK[dep] < FL_LAYER_RANK[module], (
                f"{module}.py imports {dep}, which is not a layer below it")

    # the facade hands out the members callers used, and only the facade reaches in
    exported = {alias.name for node in ast.parse(source).body
                if isinstance(node, ast.ImportFrom)
                and (node.module or "").startswith("fastlang.")
                for alias in node.names}
    assert exported == set(FL_MEMBER_HOME), sorted(exported ^ set(FL_MEMBER_HOME))
    for path in sorted(SRC.rglob("*.py")):
        if FASTLANG in path.parents or path == facade:
            continue
        reaching = {node.module for node in ast.walk(
                        ast.parse(path.read_text(encoding="utf-8")))
                    if isinstance(node, ast.ImportFrom)
                    and (node.module or "").split(".")[0] == "fastlang"}
        assert not reaching, f"{path.name} imports {sorted(reaching)}; use fast_compiler"


def test_package_facade_uses_focused_modules() -> None:
    source = (SRC / "package_manager.py").read_text(encoding="utf-8")
    for module in ("config", "metadata", "manifest", "lockfile", "project"):
        assert f"from .packages.{module} import" in source


def test_native_vm_dispatch_and_syscalls_have_explicit_boundaries() -> None:
    module = NATIVE_VM / "mellowvm_module.c"
    syscalls = NATIVE_VM / "mellowvm_syscalls.inc"
    executor = NATIVE_VM / "mellowvm_exec.inc"
    assert syscalls.is_file()
    assert executor.is_file()
    assert '#include "mellowvm_syscalls.inc"' in module.read_text(encoding="utf-8")
    assert '#include "mellowvm_exec.inc"' in module.read_text(encoding="utf-8")
    assert _line_count(module) <= 700
    assert _line_count(syscalls) <= 900
    assert _line_count(executor) <= 800


def test_standalone_compiler_keeps_loop_recognizers_separate() -> None:
    module = STANDALONE / "mellowc.c"
    recognizers = STANDALONE / "mellowc_fastloops.inc"
    source = module.read_text(encoding="utf-8")
    assert recognizers.is_file()
    assert '#include "mellowc_fastloops.inc"' in source
    assert _line_count(module) <= 700
    assert _line_count(recognizers) <= 650
    # the recognizers are file-static helpers with a single translation unit
    fragment = recognizers.read_text(encoding="utf-8")
    assert "mellowlang" not in fragment, "the standalone engine stays C-only"
    for name in ("expr_is_i64_literal", "emit_fast_i64_sum_loop", "emit_fast_string_append_loop"):
        assert f"static int {name}(" in fragment, f"{name} is defined outside the fragment"
        assert f"static int {name}(" not in source, f"{name} leaked back into mellowc.c"


def test_compiler_v3_has_no_legacy_compiler_or_silent_fallback() -> None:
    compiler_dir = SRC / "compiler"
    facade = (compiler_dir / "compiler.py").read_text(encoding="utf-8")
    image_sources = "\n".join(
        (path.read_text(encoding="utf-8"))
        for path in [SRC / "standalone_image.py", *sorted(MVI.glob("*.py"))])

    assert not (compiler_dir / "bytecode.py").exists()
    assert "_BytecodeCompiler" not in facade
    assert "compiler.bytecode" not in image_sources
    assert "v3-ir-bytecode" in facade
