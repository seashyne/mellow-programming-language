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

# Any file longer than this must appear in LINE_CEILINGS, so a new oversized
# file is a deliberate decision instead of an accident.
FILE_LENGTH_LIMIT = 1_000

# Largest each long file may become. Lower the number when the file shrinks;
# never raise it to make this test pass - split the file instead.
LINE_CEILINGS: dict[str, int] = {
    "src/mellowlang/cli/commands/agents.py": 1_150,
    "src/mellowlang/package_manager.py": 1_100,
    "src/mellowlang/vm/python_vm.py": 2_000,
    "native/mellowvm/src/mellowvm_exec.inc": 800,
    "native/mellowvm/src/mellowvm_module.c": 700,
    "native/mellowvm/src/mellowvm_storage.inc": 800,
    "native/mellowvm/src/mellowvm_syscalls.inc": 900,
    "native/standalone/src/mellowrt_core.c": 950,
    "native/standalone/src/mellowrt_ledger.c": 975,
    "native/standalone/src/mellowrt_storage.c": 1_000,
    "native/standalone/src/mellowrt_syscalls.c": 975,
    "tests/native/test_full_native_c_cli.py": 1_375,
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
    standalone = (SRC / "standalone_image.py").read_text(encoding="utf-8")

    assert not (compiler_dir / "bytecode.py").exists()
    assert "_BytecodeCompiler" not in facade
    assert "compiler.bytecode" not in standalone
    assert "v3-ir-bytecode" in facade
