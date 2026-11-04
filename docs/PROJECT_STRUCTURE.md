# Mellow Project Map

You do not need to understand every directory before working on Mellow. Pick the
area that matches the task and stay inside it.

## Start Here

| Task | Directory |
| --- | --- |
| Change syntax, compiler, CLI, or Python compatibility runtime | `src/mellowlang/` |
| Change the default engine's C extension | `native/mellowvm/` |
| Change the standalone native runtime and `mellow` CLI | `native/standalone/` |
| Change the language contract | `spec/`, `SPEC.md` |
| Add built-in library behavior | `stdlib/` |
| Add or update tests | `tests/` |
| Measure performance or read benchmark reports | `benchmarks/` |
| Work on packages or frameworks | `starter_packages/`, `mellow_packages/`, `frameworks/` |
| Work on integrations | `sdk/`, `plugin_sdk/`, `vscode-extension/` |
| Build releases or deploy services | `packaging/`, `apps/deploy/`, `.github/` |
| Learn the language or add examples | `docs/`, `examples/` |

## Directory Groups

### Language

- `src/mellowlang/` - Compiler v3 pipeline, CLI, compatibility VM, package manager, LSP, and host services.
- `native/` - Native C code, split by execution surface:
  - `native/standalone/` - the full-native compiler and runtime that produce the `mellow` executable; no Python.
  - `native/mellowvm/` - the CPython extension used by `--engine=c`.
  - `native/melv/`, `native/sm/` - asset and codec natives built by `setup.py` and the standalone CMake.
  - `native/mmg_gpu/`, `native/mellowllm/` - optional GPU and LLM natives.
- `spec/` - Machine-readable syntax locks and language conformance material.
- `stdlib/` - Built-in standard-library modules.

### Quality

- `tests/` - Core, native parity, package, CLI, and integration tests.
- `benchmarks/` - Benchmark programs, runners, raw results, and reports.

### Ecosystem

- `starter_packages/` - Source for official starter packages published to the registry.
- `mellow_packages/` - Curated local registry fixtures; installed packages are ignored.
- `frameworks/` - Optional framework packages maintained with the repository.
- `sdk/`, `plugin_sdk/` - Host-language and plugin integration surfaces.

### Apps

- `apps/deploy/` - Registry and service deployment projects, each with its own manifest.

### Tools And Delivery

- `scripts/` - Development, verification, release, and cleanup commands.
- `vscode-extension/` - Editor extension source.
- `project_template/` - Template copied into new user projects.
- `.github/` - CI and GitHub configuration.
- `packaging/` - Native/distribution packaging configuration.
- `packages/npm/` - npm installer wrapper that downloads a built distribution.
- `.qoder/skills/` - Project skills that encode these layout and verification rules for agents.

### Documentation

- `docs/` - Current manuals, specifications, policies, and release notes.
- `examples/` - Small maintained Mellow programs.

## Module Boundaries

Files that grew past a readable size are split along these seams.
`tests/language/test_source_structure.py` carries the line ceilings, so a split
cannot quietly grow back and a new long file has to be declared on purpose.

| Area | Boundary |
| --- | --- |
| Host syscalls | `src/mellowlang/host/base.py` holds `HostRegistry`, `HostFunction`, and the public module allowlist. Each syscall group is its own `register_<family>_functions(h)` module under `src/mellowlang/host/families/`; `host/runtime.py` only assembles them in registration order. `families/support.py` keeps the argument predicates shared by more than one family. |
| AI engine | `src/mellowlang/ai_core.py` is a facade over `src/mellowlang/ai/`. One concern per module: `state.py` owns every mutable store (`_MODELS`, `_LLM_MODELS`, `_SESSIONS`, `_RUNTIME_STATE`, `_API_CONFIG`), then `numerics.py`, `network.py`, `language_model.py`, `models.py`, `sessions.py`, `llm_api.py`, `llm_service.py`, and `providers.py` hold the handlers, and only `registration.py` builds `HostFunction` entries. A new AI syscall goes in the module that owns its data plus one line in `registration.py`. |
| IR optimizer | `src/mellowlang/compiler/optimizer.py` is a facade over `src/mellowlang/compiler/optimizations/`. `ir_data.py` owns the nine shared value types (`BasicBlock`, `ControlFlowGraph`, `DominatorTree`, `DefUseInfo`, `PhiNode`, `SSAProgram`, `OptimizationSummary`, `_StackValue`, `_CONST_TOP`); each pass section is one mixin - `graph.py` (CFG, dominators, def-use, SSA), `folding.py`, `dataflow.py`, `rewrite.py`, `gvn.py`, `sccp.py`, `loops.py`, `cleanup.py`, `exprs.py` - and `optimizations/optimizer.py` assembles them into `IROptimizer`, keeping only the op-set constants and `optimize()`. Because `IROptimizer` holds no instance state, a new pass goes in the module that owns its data (or a new mixin plus one entry in the driver's base list). |
| IR lowering | `src/mellowlang/compiler/ir_lowering.py` is a facade over `src/mellowlang/compiler/lowering/`. `tables.py` owns the two lookup tables (`STDLIB_CALLS`, `SYSCALL_ARGUMENTS`), `errors.py` `UnsupportedLoweringError`, and `syscalls.py` the module-call resolver plus the named-argument binder. `driver.py` owns the lowering machine - `_LoopCtx`, the instruction list, the label and temp counters and the loop stack - as `LoweringDriverMixin`; `statements.py` and `expressions.py` are one dispatch chain each; `lowerer.py` assembles the three into `IRLowerer` and defines nothing of its own. Imports point only at a lower rank - `tables`/`errors`/`driver` (0), `syscalls` (1), `statements`/`expressions` (2), `lowerer` (3) - and no module outside the facade may import the package. A new AST statement is a branch in `StatementMixin._stmt`, a new expression form a branch in `ExpressionMixin._expr`, and a new syscall alias a row in `STDLIB_CALLS` (plus `SYSCALL_ARGUMENTS` when it takes named arguments). |
| Grammar parser | `src/mellowlang/parser.py` is a facade over `src/mellowlang/parsing/`. `errors.py` holds `ParseError`, `line_text.py` the line helpers (`_strip_inline_comment`, `_indent_level`, `_split_top_level_commas`, `_split_top_level_assign`, `_collect_multiline_expr`, `_balance_delta`, `_expr_col`, `_rewrite_modern_aliases`), and `expressions.py` assembles `ExpressionAtomMixin` (`expression_atoms.py`) over `ExpressionPostfixMixin` (`expression_postfix.py`) into `ExprParser`, keeping `PRECEDENCE` and `parse_expr`. `block_core.py` owns the driver state (`lines`, `base_indent`, `i`, `stmts`, `raw_nc`), the `BLOCK_RUNS` order, `parse()`, `sub_block()` and the shared condition helpers (`_extract_cond`, `_consume_end`); each statement group is one `_run_*` mixin - `stmt_loops.py` (do/end, numeric for, `while`/`for` aliases, loop forms), `stmt_definitions.py` (skill/on), `stmt_control.py` (try, repeat, loop count, break, continue, the `if` alias and the check chain), `stmt_bindings.py` (keep, import, assign), `stmt_output.py` (print/show/println/write, precision/stop/wait/put/save/load/return), `stmt_calls.py` (`get`/`call`) - and `blocks.py` assembles them, in `BLOCK_RUNS` order, into `BlockParser` with `_parse_block` and `parse_program`. A new statement joins the run whose keyword prefix it shares, or becomes a new run plus one `BLOCK_RUNS` entry placed after the forms it must beat (`line` is passed on, so an alias rewritten by an earlier run stays visible). A new expression form goes in the atom mixin (prefix) or the postfix mixin (suffix). |
| Bytecode interpreter | `src/mellowlang/vm/python_vm.py` is a facade over `src/mellowlang/vm/interp/`. `actions.py` owns the four dispatch results (`_PASS`, `_STEP`, `_NEXT`, `_HALT`) and `execute.py` keeps the driver loop plus `ExecuteMixin.OP_HANDLERS`, the 48-entry opcode to family table that `run()` reads. Each family is one `_exec_*(op, instr)` mixin - `op_bindings.py`, `op_math.py`, `op_io.py`, `op_collections.py`, `op_call.py`, `op_control.py`, `op_import.py` - the storage builtin names are walked by `call_storage.py` through its `STORAGE_GROUPS` order over `call_save.py`, `call_net.py`, `call_fs.py`, and `frame.py` / `errors.py` / `syscalls.py` / `events.py` / `invocation.py` hold the state, raise, syscall and call helpers. `vm.py` assembles them into `MellowLangVM` with `DebuggerMixin` and `StorageMixin` last. A new opcode is one `OP_HANDLERS` entry plus a branch in the family that owns its group; a new storage builtin joins the name group that already answers its prefix. |
| Compile-to-Python fast path | `src/mellowlang/fast_compiler.py` is a facade over `src/mellowlang/fastlang/`. `builtins.py` holds `_MELLOW_BUILTINS_SRC`, the Python prelude every transpiled program starts with, `names.py` the `_py_name` mangler, and `writer.py` `WriterMixin` (`_w`, `_w_raw`, `_new_tmp`). The two dispatch chains are one mixin each: `statements.py` `StatementMixin` (`_stmt`, `_skill_def`, `_import_stmt`) and `expressions.py` `ExpressionMixin` (`_expr`, `_call_expr`). `transpiler.py` assembles those three into `PyTranspiler`, keeping only `__init__` (the indent, buffer and counters) and `transpile()`; `runner.py` holds `FastRunner`, which compiles and execs what the transpiler emitted. Imports point only at a lower layer - leaves (0), emitters (1), the assembled class (2), the runner (3) - so an emitter never reaches a peer and the runner knows only the transpiler, and no module outside the facade may import the package. A new statement or expression form is a branch in the mixin that owns its kind; a new Mellow builtin callable from the fast path is an entry in `_MELLOW_BUILTINS_SRC` plus, when it must also resolve as a bare name, a row in the `_remaps`/`_name_map` tables. |
| Agent CLI | `src/mellowlang/cli/commands/agents.py` is a facade over `src/mellowlang/cli/commands/agent_groups/`. `deps.py` is the lazy import surface the handlers were written against - one `_lazy_attr(package, name)` alias per agent builtin, nothing else - and `support.py` holds the helpers more than one group needs (`_make_agent_runtime`, `_run_agent_package`, `_agent_prompt_context`, `_resolve_agent_package_ref`, `_load_rag_index`, `_print_graph`, `_parse_jsonish`, `_parse_filters`, `_build_backoff`). Each remaining module is one subject of `mellow agent ...`: `runtime.py` (run, workflow, demo, log), `lifecycle.py` (package init/lock/build/publish/install/graph/search, registry login/logout/whoami, secrets), `inspection.py` (prompt, prompt debug, trace, preview), `serve.py` (playground, serve, marketplace, deploy), `control_plane.py` (the hosted plane plus the policy sign/verify pair), `automation.py` (schedule, trigger, webhook, queue, jobs, runner). A group may import `deps` and `support`, never a sibling group. A new agent command goes in the module that owns its subject; a new agent builtin needs one alias in `deps.py`, which is checked against the exports of `mellowlang.agents`. |
| CLI runtime commands | `src/mellowlang/cli/commands/runtime.py` is a facade over `src/mellowlang/cli/commands/runtime_groups/`. `deps.py` keeps the one lazy `pkg_auto_fetch_for_run` alias the run handler was written against and `standalone.py` the native-path answers (`_can_use_standalone_native`, `_standalone_mellow_binary`). `run_config.py` owns `RunSettings` and `build_run_config` - the 180-line config assembly lifted out of `_cmd_run`, one `name = s.name` prologue line per field - so the handler assembles nothing itself. `run.py` holds `_cmd_run`, `suite.py` the test runner (`_iter_test_files`, `_run_one_script`, `_golden_output_for`, `_cmd_test`), and `golden.py` the record/replay/diff trio, which is the only module that calls back into `run`. Imports point only downwards - `deps` (0), `standalone`/`run_config`/`suite` (1), `run` (2), `golden` (3) - and no module outside the facade may import the package. A new option on `mellow run` is a `RunSettings` field plus one prologue line in `build_run_config`, which the gate checks three ways; a new runtime subcommand joins the module that owns its subject and one line in the facade. |
| Scheduler | `src/mellowlang/agents/scheduler.py` is a facade over `src/mellowlang/agents/scheduling/`, one module per subject. `paths.py` owns `SCHEDULER_HOME`, every state file path, `_now_iso`/`_parse_iso` and the JSON/JSONL primitives; `state.py` owns the paired `_load_*`/`_save_*` readers of those files; `cron.py` and `backoff.py` are pure. Above them `jobs.py` (scheduled jobs and triggers), `webhooks.py` (webhooks, filter matching, event emit), `queue.py` (item building, enqueue, submit, read back), `drain.py` (worker drain, dead-letter, retry, queue log and stats), `runner.py` (due-jobs pass and the background loop) and `http_api.py` (the request handler, the server record and the two status readers). Imports only point downwards - `paths`/`backoff` (0), `state`/`cron` (1), `jobs`/`queue` (2), `drain`/`webhooks` (3), `runner`/`http_api` (4) - so no subject can reach into the driver that calls it, and the whole 67-name surface the monolith exported stays on `scheduler.py` for `mellowlang.agents` and the tests. A new state file gets its path in `paths.py` and its pair in `state.py`; a new subject function goes in the module that owns it and one line in the facade. |
| Agent package registry | `src/mellowlang/agents/registry.py` is a facade over `src/mellowlang/agents/registry_groups/`, one module per concern. `layout.py` owns the on-disk constants (`AGENT_ROOT`, `AGENT_REGISTRY_ROOT`, `AGENT_INSTALLED_ROOT`, `AGENT_CACHE_ROOT`, `ARCHIVE_EXT`, `LOCKFILE_NAME`, `REPRO_ZIP_TIMESTAMP`), directory creation and name normalisation, and `integrity.py` the content hashes, canonical JSON, manifest reader and the sign/verify pair. `auth.py` resolves the registry URL and its read/private tokens, `catalog.py` reads a package manifest, lists local versions and searches them, and `archive.py` builds the reproducible archive and publishes it into the local registry. Above them `graph.py` resolves a dependency graph, `lock.py` pins it into `agent.lock`, `install.py` extracts a verified archive dependencies-first, and `remote.py` is the only module that speaks HTTP. Imports only point downwards - `layout`/`integrity` (0), `auth`/`catalog` (1), `archive`/`graph`/`lock` (2), `install` (3), `remote` (4) - and the facade re-exports the 31 public names while the 11 helpers stay package-internal. A new archive format detail belongs to `integrity.py` or `archive.py`, a new registry endpoint to `remote.py`, and a new step in installation to `install.py`. |
| Standalone image | `src/mellowlang/standalone_image.py` is a facade over `src/mellowlang/mvi/`, one module per concern of the `.mvi` file. `ops.py` owns the three lookup tables (`_STANDALONE_OPS`, `_COMPARE_MAP`, `_SYSCALL_NAME_MAP`), `format.py` the magic and version header, the four entry records and `StandaloneImage.to_bytes`, `binary.py` the project-root anchor and the two paths that find the standalone executable, and `consts.py` the constant-pool and span helpers. The pass is `state.py` (`Lowering`, the 19 accumulators the 391-line monolith shared, plus `slot_for` and `enter_scope`), `scopes.py` (the `func_table` rebuild and the per-function slot scan), `emit.py` (`emit_instruction`, one source opcode in and one image opcode out), `entries.py` (function entries, the core-module seed, and the address, jump and module fix-ups) and `lowering.py`, which only runs them in that order. `compile.py` holds the three ways in: compile a source string, compile a file, run an image. Imports point only at a module earlier in that order, so the byte format knows nothing about the pass that fills it, and no module outside the facade may import the package. A new opcode is one `_STANDALONE_OPS` entry plus a branch in `emit_instruction`; a new accumulator is a field on `Lowering`, never a module-level global. |
| Standalone compiler | `native/standalone/src/mellowc.c` scans, parses, and dispatches statements. The while-loop shape recognizers and their fused emitters live in `native/standalone/src/mellowc_fastloops.inc`, included by that one translation unit; a new shape there needs a matching opcode executor in `mellowrt_core.c`. |
| CPython extension | `native/mellowvm/src/mellowvm_module.c` keeps dispatch thin and includes `mellowvm_syscalls.inc`, `mellowvm_exec.inc`, and `mellowvm_storage.inc`. |
| Facades | `src/mellowlang/package_manager.py` re-exports `packages/{config,metadata,manifest,lockfile,project}`; `host/registry.py` and `host/modules.py` stay stable import paths for the split host package. |

`native/**/*.inc` fragments are part of the C surface: like the `.c` and `.h`
files beside them, they must not mention `mellowlang` or reach the Python layer
(`tests/test_workspace_boundaries.py`).

## Root Files

- `README.md`, `SPEC.md`, `CHANGELOG.md`, `LICENSE` - public project documents.
- `pyproject.toml`, `setup.py` - Python tooling and compatibility distribution metadata.
- `main.py`, `mellow.cmd`, `mellow.ps1`, `install.sh` - thin launch/install wrappers.

New implementation code should not be added at the repository root.

## Generated Or Local Only

These should not be committed unless there is a specific fixture reason:

- `.ci-logs/`
- `.ci-tmp/`
- `.mellow/`
- `.mellow-release-gate-work/`
- `.mellow-data-benchmark-*`
- `.tmp_*`
- `outputs/`
- `build/`
- `dist/`
- `node_modules/`
- `.wrangler/` in deployment workspaces
- `mellow_packages/installed/`
- `mellow_agent_packages/`
- `examples/mellow_packages/installed/`
- `native/**/build/`
- `tools/` (vendored toolchains downloaded by benchmark runners)
- root `.mellow_aliases.json`, `.mellow_imports.json`, `.mellow_runtime.json`
- root `mellow.lock` unless it is intentionally used as a project-level fixture
- `mellow_models/`

Run `scripts/clean-worktree.ps1` to preview generated files, then
`scripts/clean-worktree.ps1 -Apply` to remove them.

## Package Data

`mellow_packages/registry/` is currently used as an in-repo registry fixture. Keep only curated package versions there. Installed packages and local cache output belong under `mellow_packages/installed/` and are ignored.

Longer term, prefer this layout:

```text
mellow_packages/
  registry/       curated registry fixtures
  README.md       explains fixture policy
```

Local installs should live outside the repository or under ignored cache directories.

## CLI Code

The CLI should remain modular:

```text
src/mellowlang/cli/
  main.py          thin entrypoint and command dispatch only
  common.py        shared CLI helpers, JSON output, error formatting, lazy imports
  parser.py        argparse definitions
  ux.py            help, guide, ask, aliases
  commands/
    agents.py      facade: re-exports the agent command groups below
    agent_groups/
      deps.py          the lazy alias each agent builtin command imports through
      support.py       shared helpers: runtime builder, package runner, parsers
      runtime.py       run, workflow, demo, and observation-log commands
      lifecycle.py     package, registry, and secret commands
      inspection.py    prompt, prompt debug, trace, and preview commands
      serve.py         playground, serve, marketplace, and deploy commands
      control_plane.py hosted deployments and the policy sign/verify pair
      automation.py    schedule, trigger, webhook, queue, jobs, and runner
    compiler.py    compile and pack commands
    media.py       desktop, MMG, MELV, and state-machine commands
    packages.py    package and registry commands
    project.py     init, new, check, and format commands
    runtime.py     facade: re-exports the runtime command groups below
    runtime_groups/
      deps.py          the lazy package auto-fetch alias the run handler imports through
      standalone.py    the standalone binary lookup and the guard that chooses it
      run_config.py    RunSettings and the RunConfig assembly lifted out of run
      run.py           the run handler
      suite.py         test discovery, the per-script runner, and golden output
      golden.py        record, replay, and diff
    standalone.py  standalone native runtime commands
    system.py      doctor, status, config, bench, security, and native commands
```

`main.py` must not define command handlers. New command families belong in
`cli/commands/`; parser definitions remain in `cli/parser.py`. An agent command
joins the `agent_groups/` module that owns its subject, and the name is added to
the `agents.py` facade so the import path `main.py` uses stays the only one. A
runtime subcommand joins the module in `runtime_groups/` that owns its subject,
and `runtime.py` stays imports-only so `main.py` keeps the single import path.

## Package System

`package_manager.py` is the compatibility facade for existing imports. Focused
implementation lives under `src/mellowlang/packages/`:

```text
packages/
  config.py        registry/auth/trust configuration and aliases
  metadata.py      package names, creators, authors, and versions
  manifest.py      manifest discovery and TOML serialization
  lockfile.py      lockfile, import map, and runtime map handling
  project.py       project roots, presets, local packages, and scaffolding
```

New package features should be implemented in the focused module and exported
through `package_manager.py` only when compatibility requires it.

## VM Code

`vm/python_vm.py` is a facade: it keeps the import path and the module-level
names consumers already use. The interpreter itself is assembled in `vm/interp/`,
one module per opcode family, and services with a separate concern are still
mixed in without changing the public VM class:

```
vm/interp/
  actions.py        the four dispatch results: _PASS _STEP _NEXT _HALT
  execute.py        the driver loop and OP_HANDLERS, the opcode -> family table
  op_bindings.py    PUSH STORE STORE_AUTO STORE_KEEP LOAD SEED GLOBAL_SEED
  op_math.py        ADD SUB MUL DIV, COMPARE BOOL_*, MOD POW
  op_io.py          PRINT PRINTN SHOW_PREC, ASK WAIT RANDOM RANDFLOAT, SAVE SAVE_VAL LOAD_F
  op_collections.py BUILD_LIST BUILD_MAP GETITEM LEN, LIST_HAS LIST_PUT POP
  op_call.py        CALL, SYSCALL, PUSH_FUNC CALL_VAL SLICE
  op_control.py     TRY ENDTRY HALT STOP, JUMP JIF, RETURN ARG
  op_import.py      IMPORT
  call_storage.py   the builtin-name walk and its STORAGE_GROUPS order
  call_save.py      save/load slot builtins      call_net.py  net and websocket builtins
  call_fs.py        directory and file builtins
  frame.py          VM state, value limits, truthiness, sub-VMs
  errors.py         raise, sandbox, trace, exception handling
  syscalls.py       syscall dispatch and budget
  events.py         bt/fsm ticks and emit
  invocation.py     nested call entry (_call_fn) and one-step execution
  vm.py             assembles the mixins into MellowLangVM
```

A new opcode is one `OP_HANDLERS` entry plus a branch in the family that owns
its group; a new storage builtin goes in the name group that already answers
that prefix. `vm.py` keeps `DebuggerMixin` and `StorageMixin` last, so a name
declared by the interpreter always wins over the host mixins beside it.

- `vm/debugger.py` - breakpoints, snapshots, stepping, and watch expressions.
- `vm/storage.py` - sandboxed paths, filesystem permissions, and JSON storage.

Keep the dispatch loop and the family bodies together in `vm/interp/`; move an
opcode out of a family only when it becomes its own group, not because a file
grew.

## Cleanup Rules

- Do not remove or move dirty tracked files without checking `git status`.
- Add ignores before running generators.
- Keep generated package installs out of `mellow_packages/registry/`.
- If a generated output is needed for a test, place it under `tests/fixtures/` and document why.
