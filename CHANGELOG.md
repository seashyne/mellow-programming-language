# Changelog

## Unreleased

### Structure
- Split the 15 native C sources over 300 lines into fragment parents. C cannot split
  one translation unit across import seams, so each parent keeps everything before
  the first seam and `#include`s contiguous `*_partN.inc` slices in order; the
  fragments are never compiled separately, so no CMake or `setup.py` source entry
  changed. Seams are top-level function starts, `/* ── ` section banners, and - for
  the giant dispatch loops - `case` labels inside the switch. Seam detection tracks
  brace, preprocessor, comment and paren depth so a multi-line signature is never
  cut, and every split proves byte-identical reconstruction from parent plus parts.
  - `native/standalone/src/`: `mellowc.c` 11 + 3 parts (150/280/191),
    `mellowc_fastloops.inc` 13 + 3 (274/259/51), `mellowrt_core.c` 31 + 4
    (289/255/252/103), `mellowrt_ledger.c` 17 + 4 (285/253/168/223),
    `mellowrt_storage.c` 41 + 4 (290/250/283/111), `mellowrt_syscalls.c` 56 + 4
    (285/282/290/24) and `mellowrt_main.c` 38 + 2 (194/94).
  - `native/mellowvm/src/`: `mellowvm_module.c` 139 + 2 (266/234), `mellowvm_exec.inc`
    17 + 3 (287/261/127), `mellowvm_storage.inc` 16 + 3 (227/261/281) and
    `mellowvm_syscalls.inc` 12 + 4 (39/255/275/189). The parent keeps the struct,
    opcode table and forward declarations; the second part carries the includes of
    the three subject fragments, which are each parents of their own parts.
  - `native/sm/src/sm_native.c` 20 + 2 (276/106), `native/melv/src/melv_native.c`
    9 + 3 (223/210/199), `native/mmg_gpu/src/renderer_gl.c` 21 + 2 (229/66) and
    `native/mellowllm/src/mellowllm_module.c` 8 + 2 (191/113).
- Every native `.c`/`.h`/`.inc` file is now at most 300 lines. The eight obsolete
  native ceilings are gone from `LINE_CEILINGS`, and
  `tests/language/test_source_structure.py` gained a fragment-manifest test: part
  numbering is contiguous, each parent includes exactly its parts in order, and
  parent and parts both stay at or below 300 lines. `test_native_vm_dispatch...`
  and `test_standalone_compiler...` now read the translation unit through its
  parts instead of the former monolith.
- Verified: the standalone CMake Release build of `mellow` succeeded and CTest
  passed 5/5; all four Python extensions rebuilt in place; `tests/native` passed
  91/91. `native/mmg_gpu` could not be configured on this machine (no pkg-config /
  SDL2), so its split rests on the byte-identical reconstruction rather than a
  compile.
- Split eight more over-long modules along their documented seams, each behind an
  imports-only facade that keeps the old import path and surface:
  - `src/mellowlang/web.py` (510) over `web_groups/`: records, lexing, value helpers,
    parsing, TSX emission, dev-app scaffold and dev server. 115 oracle checks, a
    64-step battery (47 results, 17 refusals) and complete group coverage.
  - `src/mellowlang/desktop_host.py` (471) over `desktop_host_groups/`: parsing, window
    files, Tk actions, runtime/launcher, portable bundle and status. 66 checks, 49 steps.
    `bundle.py` re-anchors `__file__` to the facade - the split's one authored line.
  - `src/mellowlang/mmg_runtime.py` (464) over `mmg_groups/`: parsing, render graph,
    spec entry points, status and the window loop. 57 checks, 31 steps, no exemptions.
  - `src/mellowlang/registry/server.py` (446) over `registry/server_groups/`: manifest
    helpers, `RegistryStore`, `Handler` and the launcher. 68 checks; the 79-step battery
    drives a real `ThreadingHTTPServer` on `127.0.0.1:0`, 16 refusals included.
  - `src/mellowlang/lint.py` (350) over `lint_groups/`: issues/scope chain, visitor and
    API. 69 checks, 138 steps, no refusals or exemptions.
  - `src/mellowlang/ast.py` (332) over `ast_nodes/`: containers, statements and
    expressions, the two node families never importing each other. 260 checks, full
    executable-line coverage of all three modules, and the facade still re-exports the
    `dataclass`/`field`/typing names the historical star-import surface handed out.
  - `src/mellowlang/vm/debugger.py` (366) over `debugger_groups/`: one peer mixin per
    subject, assembled by a `DebuggerMixin` whose body is only the four bases. 105 checks.
  - `src/mellowlang/vm/cbridge.py` (363) over `cbridge_groups/`: the native vocabulary
    and loader, the host adapter and the storage guards. 54 checks and a 105-step battery
    (71 results, 34 refusals). The capability reporters and both runners deliberately
    stay in the facade because callers and tests patch `_load_ext` there; the loader's
    `from ... import _mellowvm` is the split's one authored token, pinned by
    `test_cbridge_structure.py`.
- Each split carries its own `tests/language/test_<name>_structure.py` - member homes,
  module sizes, one-way layering, exported surface and no outside importers - because
  `test_source_structure.py` sits at its declared 1,100-line ceiling. The language,
  native-parity, workspace-boundary and quality gates pass; the only failure is the
  pre-existing `package_manager.py` ceiling owned by uncommitted work.
- Split `src/mellowlang/agents/control_plane.py` (536 lines) into
  `src/mellowlang/agents/control_plane_groups/`, behind a 38-line imports-only facade
  that keeps the `mellowlang.agents.control_plane` path `agents/__init__.py`, the CLI
  and the tests use. `state.py` owns the state-file path and its JSON read/write pair
  plus the timestamp/slug helpers, `transport.py` the remote test, URL builder and JSON
  HTTP call, `traffic.py` traffic-split normalisation and revision labelling,
  `metrics.py` metric coercion and autoscaling signals, and `alerts.py` alert-rule
  evaluation. `deploy.py` registers deployments and revisions, `inspection.py` lists
  deployments, status, revisions and health, `rollout.py` promotes, rebalances and rolls
  back, and `observability.py` records metrics and manages alert rules. Imports point
  only downwards - `state`/`transport` (0), `traffic`/`metrics` (1),
  `deploy`/`inspection`/`rollout`/`alerts` (2), `observability` (3) - and the facade
  re-exports exactly the 15 public names; the 18 helpers stay package-internal.
- Also proven against `HEAD`: all 33 declarations are byte-identical with equal code
  signatures. A 151-step battery - local registration, revision history, health,
  rollouts with and without a canary, traffic splits including the 0/0 and negative
  normalisations, rollbacks by default and explicitly, metrics history trimming,
  autoscaling in and out, every alert operator, malformed and non-dict state files, and
  a canned remote control plane that answers success, empty body, HTTP JSON error, HTTP
  text error, bad JSON and a network failure - runs against both the monolith and the
  split package in fresh temp trees and agrees step for step, 18 refusals included. The
  battery executes every executable line of all 9 modules; the single exemption is the
  `None` guard in `_upsert_local_deployment`, which `_ensure_revision` always fills
  first. `test_control_plane_structure.py` carries the contract - member homes, module
  sizes, one-way layering, the exported surface and its excluded helpers - in its own
  file because `test_source_structure.py` sits at its declared 1,100-line ceiling.
- Deleted the orphaned `src/mellowlang/core.py` (411 lines): nothing imported its
  `MellowLangEngine`, an early `frinds/core.py` leftover referenced only inside its own
  file, so it was removed rather than split.
- Split `src/mellowlang/agents/registry.py` (544 lines) into
  `src/mellowlang/agents/registry_groups/`, behind a 65-line imports-only facade that
  keeps the `mellowlang.agents.registry` path `agents/__init__.py` and the registry
  tests use. `layout.py` owns the on-disk constants and name normalisation,
  `integrity.py` the hashes, canonical JSON, manifest reader and signature pair,
  `auth.py` the registry URL and read/private tokens, `catalog.py` the manifest reader,
  local version listing and search, `archive.py` the reproducible archive and local
  publish, `graph.py` the dependency graph, `lock.py` `agent.lock`, `install.py`
  extraction and install-from-lock, and `remote.py` the only HTTP client. Imports point
  only downwards - `layout`/`integrity` (0), `auth`/`catalog` (1),
  `archive`/`graph`/`lock` (2), `install` (3), `remote` (4) - and the facade re-exports
  exactly the 31 public names; the 11 helpers stay package-internal rather than
  widening the old surface.
- Also proven against `HEAD`: all 42 declarations are byte-identical and keep their AST;
  every function keeps its code signature (with set constants normalised, since a
  `frozenset`'s `repr` follows hash order). A 92-step battery - sign/verify, reproducible
  archives with ignored files, publish twice, local and dir graphs, cycles, unsatisfied
  dependencies, locks with and without manifests, installs from archive and copy, unsafe
  and corrupt archives, frozen-lock drift in all three forms, auth through env and
  config, and a canned HTTP registry with cache reuse, a checksum mismatch, a private
  scope and a network failure - runs against both the monolith and the split package in
  fresh temp trees and agrees step for step, 18 refusals and 2 raises included. The
  battery executes every executable line of all 9 modules; the single exemption is the
  second archive-path guard in `install.py`, which a zip member with no `..` component
  cannot reach. `test_agent_registry_structure.py` carries the contract - member homes,
  module sizes, one-way layering, the exported surface and its excluded helpers - in its
  own file because `test_source_structure.py` sits at its declared 1,100-line ceiling.
- Split `src/mellowlang/compiler/ir_lowering.py` (597 lines) into
  `src/mellowlang/compiler/lowering/`, behind a 13-line imports-only facade that keeps
  the `mellowlang.compiler.ir_lowering` path `compiler.py` uses. `tables.py` holds the
  vocabulary (`STDLIB_CALLS` with 141 entries, `SYSCALL_ARGUMENTS` with 15), `errors.py`
  `UnsupportedLoweringError`, and `syscalls.py` the module-call resolver and the
  named-argument binder. `driver.py` owns the machine - `_LoopCtx`, the instruction
  list, the label and temp counters, the loop stack and `lower()` - as
  `LoweringDriverMixin`; `statements.py` and `expressions.py` hold one dispatch chain
  each (`_stmt`, `_expr`); `lowerer.py` is a class header assembling the three, and
  defines nothing else. Imports only point downwards - `tables`/`errors`/`driver` (0),
  `syscalls` (1), `statements`/`expressions` (2), `lowerer` (3) - and no module outside
  the facade may import the package. The unused `Optional` import was dropped rather
  than re-exported.
- Also proven against `HEAD`: the 10 functions and 2 classes are byte-identical with
  equal code signatures (masking `CO_METHOD`, which a module-level re-compile of a
  method cannot carry), both tables compare equal, and the assembled `IRLowerer` gets
  every method from its declared mixin. 39 hand-built ASTs - the error paths no
  maintained program reaches, from `TryStmt` and `foreach` unpacking to unknown
  operators, anonymous f-string parts and allowlist misses - and 120 real `.mellow`
  files (101 producing an `IRProgram`, 37 distinct opcodes) lower identically to the
  monolith, down to every instruction's opcode, argument, line and column. The battery
  executes every executable line of all 7 modules, needing no unreachable exemption,
  and stubbing each of the 55 runtime imports, or patching a provider such as
  `dataclasses.dataclass`, changes that battery; the other 9 are annotation-only because
  `from __future__ import annotations` keeps them unevaluated.
  `test_ir_lowering_structure.py` carries the contract - each member's home, the
  assembler's empty body and bases, each module at 300 lines or fewer, the one-way
  layering, the exported surface, and that no other module imports the package - in its
  own file because `test_source_structure.py` sits at its declared 1,100-line ceiling.
- Split `src/mellowlang/cli/commands/runtime.py` (661 lines) into
  `src/mellowlang/cli/commands/runtime_groups/`, behind a 12-line imports-only
  facade that keeps the import path `cli/main.py` already uses. `deps.py` holds the
  lazy `pkg_auto_fetch_for_run` alias, `standalone.py` the standalone-binary lookup
  and the guard that picks it, `run_config.py` `RunSettings` and
  `build_run_config`, `run.py` `_cmd_run`, `suite.py` the per-script runner,
  discovery and golden output, and `golden.py` record/replay/diff, the only module
  that calls back into `run`. Imports only point downwards - `deps` (0),
  `standalone`/`run_config`/`suite` (1), `run` (2), `golden` (3) - and no module
  outside the facade may import the package. The 180-line `RunConfig` assembly
  inside `_cmd_run` became the body of `build_run_config(s: RunSettings)`, opened by
  one `name = s.name` line per field and closed by `return cfg`, so the assembly
  text is byte-identical and the handler now calls it once with every field by
  keyword. `_project_root` was dropped rather than moved: nothing in `src/` or
  `tests/` referenced it.
- Also proven against `HEAD`: the 9 moved definitions are byte-identical with equal
  code signatures, and exactly one copied handler line differs - the lazy
  `from ...fast_compiler` import, which sits a level deeper
  (`from ....fast_compiler`). 97 differential cases agree on both sides (exit code,
  stdout, stderr, escaping error, and `repr` of every constructed config), covering
  34 distinct `RunConfig`s, 5 exit codes, 34 distinct outputs, 94 returned exit
  codes, 3 escaping errors and 79 runs that reached the VM. Statement coverage
  executed every line of all 7 modules; 4 lines are declared unreachable with
  executable proofs - the native guard refuses `json_out`, so its own json branch
  cannot run, and `FastRunner.run` swallows `SystemExit`, so the handler's `except`
  is dead - and stubbing each of the 28 runtime imports, or patching the provider of
  `dataclass`, changes that battery (4 more are annotation-only). Because
  `test_source_structure.py` sits at its declared 1,100-line ceiling,
  `tests/language/test_cli_runtime_structure.py` carries this unit's contract: each
  member's home, the prologue/field/keyword agreement, every module at 300 lines or
  fewer, the one-way layering, the exported surface, and that no other module
  imports the package.
- Split `src/mellowlang/fast_compiler.py` (662 lines) into `src/mellowlang/fastlang/`,
  one module per concern of the compile-to-Python fast path: `builtins.py` holds
  `_MELLOW_BUILTINS_SRC`, the Python prelude every transpiled program starts with,
  `names.py` the `_py_name` mangler, `writer.py` `WriterMixin` (`_w`, `_w_raw`,
  `_new_tmp`), `statements.py` `StatementMixin` (`_stmt`, `_skill_def`, `_import_stmt`),
  `expressions.py` `ExpressionMixin` (`_expr`, `_call_expr`), `transpiler.py` assembling
  the three mixins into `PyTranspiler` with only `__init__` and `transpile()`, and
  `runner.py` `FastRunner` - behind a 17-line imports-only facade that keeps the
  `mellowlang.fast_compiler` import path the CLI commands and tests already use. The
  monolith's methods already sat at class indentation, so each move is verbatim: the
  only text this split authors is a docstring, a future import, a mixin header and the
  import block per module, and `symtable` free-name analysis resolves every name a
  module reads from outside itself instead of a hand-written scope walk. Imports point
  only at a lower layer - leaves, then the two emitters, then the assembled class, then
  the runner - so an emitter cannot reach a peer, and only the facade imports `fastlang`.
- Also proven against `HEAD`: all 4 module-level members and all 10 methods of the two
  classes are the monolith's own code objects (same instruction stream, names, consts,
  docstrings and signatures), `PyTranspiler` assembles
  `WriterMixin/StatementMixin/ExpressionMixin`, and the instance state matches. 98 real
  `.mellow` programs transpile to byte-identical Python (78 produced source, 20 raised
  the same `ParseError`), 54 runnable ones produce identical output, and 86 hand-built
  AST nodes - fed straight to `_stmt`/`_expr`, since the chains hold branches no
  maintained program reaches - render identically including the writer's counters. The
  facade keeps all 5 caller-visible names; the 58 that left are the monolith's own
  import bindings and no file under `src/` or `tests/` imports any of them from
  `fast_compiler`. Statement coverage executed all 320 statement lines of the 7 modules
  (one `except Exception: pass` around a `sys.stdout` restore is declared unreachable,
  docstring statements cannot be traced), and stubbing any of the 49 runtime imports in
  the module that drew it changes that battery; 2 are annotation-only (`Expr`, `Stmt`)
  and 3 are consumed once by a class header (`*Mixin`), which the MRO check covers.
  `test_fast_compiler_is_split_by_concern()` now locks the module set, each member's and
  method's home, the mixin assembly and driver shape, the one-way layering, the exported
  surface, and that no other module imports `fastlang`; that gate file is now declared
  in `LINE_CEILINGS` at 1,100, because each split adds its tables there and the next
  overflow moves the split contracts to their own module rather than raising it again.
- Split `src/mellowlang/standalone_image.py` (668 lines) into
  `src/mellowlang/mvi/`, one module per concern of the `.mvi` file: `ops.py` holds
  the three lookup tables, `format.py` the header, the four entry records and
  `to_bytes`, `binary.py` the project-root anchor and the standalone-executable
  paths, `consts.py` the constant-pool and span helpers, `state.py` the `Lowering`
  accumulators with `slot_for`/`enter_scope`, `scopes.py` the `func_table` rebuild
  and the per-function slot scan, `emit.py` the opcode chain, `entries.py` the
  function entries, core-module seed and the address/jump/module fix-ups,
  `lowering.py` the driver, and `compile.py` the compile-source, compile-file and
  run entry points - behind a 23-line imports-only facade that keeps the
  `mellowlang.standalone_image` import path. The 391-line
  `lower_compiled_to_standalone_image` became that driver plus nine named steps,
  with every enclosing local the blocks shared turned into a `Lowering` field, so
  the cut is a rename and not a rewrite. Imports point only at a lower module in
  that order, and only the facade reaches into the package.
- Also proven against `HEAD`: the 19 module-level members are identical to the
  monolith (instruction stream, names, consts, dataclass fields and values) with
  exactly two declared edits - `_project_root` re-anchored from `parents[2]` to
  `parents[3]`, and `compile_source_to_standalone_image`'s lazy `from .compiler`
  deepened to `from ..compiler`; the 391 lines are accounted for, every non-blank
  line claimed by exactly one emitted block, and each rewritten body's AST is
  equal to the original's after the same rename. 121 differential cases produce
  byte-for-byte identical images or the same error type and message (106
  lowerings, 58 of them from real `.mellow` source, plus the compile/run surface
  and the byte writer), and those images are 61 distinct files from 135 to 9,051
  bytes. Statement coverage executed 336 of the 337 moved statement lines, the one
  gap being unreachable in `HEAD` too, and stubbing any of the 26 runtime imports
  drawn between the modules changes that battery; the other 6 are annotation-only
  because `from __future__ import annotations` keeps them unevaluated.
  `test_standalone_image_format_is_split_by_concern()` now locks each member's and
  step's home, the 19 `Lowering` fields, the one-way layering, the exported surface
  against the package, and that no other module imports `mvi`; the
  `compiler.bytecode` absence check now spans the package rather than the facade.
- Split `src/mellowlang/cli/commands/agents.py` (1,137 lines) into
  `cli/commands/agent_groups/`: `deps.py` keeps the 81 lazy `_lazy_attr` aliases,
  `support.py` the helpers shared across groups, and one module per subject of
  `mellow agent ...` - `runtime.py`, `lifecycle.py`, `inspection.py`, `serve.py`,
  `control_plane.py`, `automation.py` - behind a 52-line imports-only facade. A
  group imports `deps` and `support`, never a sibling group.
- Proven against `HEAD`, not reviewed: 43 definitions moved verbatim, the same
  124-name surface with equal signatures, 127 command invocations with identical
  scrubbed output, and stubbing each of the 107 borrowed bindings changes that
  battery. `LINE_CEILINGS` lost the `agents.py` entry in the same commit, and
  `test_cli_agent_commands_are_split_by_group()` now checks every handler's
  subject module plus that each lazy alias still names an export its target
  package provides.
- Split `src/mellowlang/agents/scheduler.py` (789 lines) into
  `src/mellowlang/agents/scheduling/`: `paths.py` owns `SCHEDULER_HOME`, the
  state-file paths and the time and JSON primitives, `state.py` every paired
  `_load_*`/`_save_*` reader of those files, `cron.py` and `backoff.py` stay pure,
  and `jobs.py`, `webhooks.py`, `queue.py`, `drain.py`, `runner.py`, `http_api.py`
  hold one subject each - behind a 93-line imports-only facade. Imports may only
  point at a lower layer, so no subject can reach into the driver that calls it.
- Also proven against `HEAD`: the 66 functions are byte-identical to the monolith
  (code, names, consts, line spans, source text, signature) with only `__module__`
  and each def's own line changed, the facade still hands out all 67 names the
  monolith owned, 156 scheduler calls match on both sides with the 21 files left in
  the state dir identical byte for byte, 64 of the 66 defs are named by a case and
  the last two reached through one that is, and stubbing each of the 57 sibling
  imports changes that battery. Proving it needed a frozen clock per module and a
  stub `ThreadingHTTPServer` that captures the nested handler and pins
  `date_time_string()`, because the HTTP surface otherwise reads the real wall
  clock. `test_agents_scheduler_is_split_by_subject()` now locks each function's
  home, the whole re-exported surface against `agents/__init__.py` and the tests,
  and the one-way layering.

### Removed
- `src/mellowlang/fast_vm.py` (847 lines, the v1.4.9 compile-to-Python engine).
  Nothing in the repository imported it - no source, test, script, doc, or
  dynamic import string referenced `FastVM` or `mellowlang.fast_vm` - and its
  `FastVM.run()` could not have worked: it catches `_MellowStop`, a class that
  only exists in the source string the generator emits, so a program using
  `stop` raised `NameError` in the host. No other module changed, so the engines
  the project does ship are untouched.

## 2.9.9 - 2026-11-03

### Structure
- Split `src/mellowlang/host/runtime.py` (1,470 lines) into `host/base.py`,
  fourteen `host/families/<name>.py` registration modules, and a 66-line
  assembler that keeps the original registration order. `families/support.py`
  now holds the argument-shape predicates that were duplicated inline.
- Split `native/standalone/src/mellowc.c` (1,210 lines) so the while-loop shape
  recognizers and their fused emitters live in `mellowc_fastloops.inc`, included
  by that one translation unit; CMake is unchanged.
- Both splits are verbatim and proven by before/after equivalence: identical
  204-syscall registry (names, order, costs, bounds) and 7,020 differential host
  calls per side with identical results and errors.

### Gates
- `tests/language/test_source_structure.py` carries `LINE_CEILINGS`: any file
  over 1,000 lines must be declared, and a declared file may not exceed its
  ceiling. Ceilings only move down.
- Added structure tests for the host family seam and the compiler fragment seam.
- The workspace boundary gate now treats `native/standalone/**/*.inc` as C-only
  surface.
- `docs/PROJECT_STRUCTURE.md` documents module boundaries; the project skill
  records the split seams and the rule that `native` requires an explicit
  `cmake --build` before CTest.

### Measured
- Reran the cross-language comparison on optimizer-proof workloads and wrote
  `benchmarks/native_vs_zig/RESULTS_2026-11-02_CROSS-LANGUAGE-HONEST.md`:
  45.9 ns/iter for Mellow against 2.8 for gcc `-O3` on a serialized chain, plus
  the startup floors and the shape cliff the previous table hid.
- Root-caused the native money/ledger throughput defect to the linear
  `heap_find()` scan and the absent GC trigger (553 microseconds per `money_add`
  at 3,000 live blocks against 56 ns on the Python Decimal path).

## 2.9.8 - 2026-11-02

### Native Runtime Services
- Storage, save, fs, and file APIs now lower to `std.*` syscalls and run in C on
  the CPython extension and the standalone executable, so the save-path sandbox
  applies to native programs too.
- Ledger, money, server, and the SM CLI share the native syscall id table.
- The Python VM re-enters its legacy builtins from the syscall instruction on a
  VM-private bytecode copy, keeping the shared compile cache intact.

### Parity Coverage
- Added `tests/fixtures/storage_core.mellow` and the ledger core fixture as the
  shared native/Python parity source.
- Added `examples/native_server.mellow` as the maintained native HTTP example.

### Workspace
- The boundary gate rejects root build artifacts and undocumented `native/`
  surfaces, and generated agent-package output is now ignored.

## 2.9.4 - 2026-06-21

### Runtime Structure
- Split CLI commands, package services, and Python VM debugger/storage into
  focused modules with architecture guard tests.

### ARM64 Portability
- Add standalone C runtime platform metadata and `--runtime-info`.
- Add ARM64 CMake detection and a cross-build/QEMU CI gate.
- Report `generic-c` until optimized architecture kernels exist.

## 2.9.3 - 2026-06-18

### Stability and Documentation
- Add `spec/mellow-2.9.3-stability.json` and `scripts/test-v293-stability.ps1`.
- Extend `mellow release-gate` to run `tests/core`, `tests/language`, and registry smoke tests.
- Add `docs/CORE_DOCS.md`, `docs/LEGACY_BOUNDARIES.md`, and `docs/experimental/README.md`.
- Move agents, MMG, playground, desktop, and hosted-ecosystem docs under `docs/experimental/`.
- Add `tests/language/test_v293_release_contract.py`.

### mellow-sdk
- Add `mellow-sdk` starter package with Python OpenAI SDK-shaped API.
- Add `src/mellowlang/sdk_core.py` host bridge and optional `sdk` Python extra.
- Add `docs/MELLOW_SDK.md`.

## 2.9.2 - 2026-06-16

### Security and Performance Gates
- Add `mellow bench`, `mellow security audit`, and `mellow release-gate`.
- Add release-gate checks for benchmark smoke tests, sandbox enforcement, and official package integrity.
- Make AI agent tool policy default-deny while preserving explicit `--tool` allow behavior.
- Add the Mellow AI security and performance policy document.

### Native Runtime
- Add native LLM tensor batch dispatch plumbing and Python fallback batching.
- Block native storage path traversal before entering the C VM and align native storage source with sandboxed storage paths.

## 2.9.1 - 2026-06-14

### Core LLM
- Add the official `core-llm` package with dataset, training, evaluation,
  generation, completion, chat, checkpoint, backend, and device-planning APIs.
- Add the Mellow-owned native tensor backend foundation with matmul, softmax,
  GELU, and layer-normalization kernels plus a Python reference fallback.
- Add x64 and ARM64 selection to the Windows native build helper.

### Performance
- Add a bounded in-process compiler cache for repeated source compilation.
- Add a fast CLI version path, reducing measured cold version startup from
  roughly 216 ms to roughly 64 ms on the development machine.
- Add batched tensor host calls and separate cold/warm compile benchmarks.

### Native-First Default
- Make the native C VM the default engine for `RunConfig()` and `mellow run`.
- Keep Python fallback enabled for unavailable native builds and runtime features
  without native parity, including debugger, events, and record/replay.
- Preserve `--engine=auto` as a compatibility mode and `--engine=py` as an
  explicit Python override.

## 2.8.0 - 2026-06-13

### Ledger Core
- Add immutable double-entry ledger primitives through `std.ledger`.
- Require every transaction to contain at least two postings whose Decimal amounts sum to zero.
- Add deterministic SHA-256 hash chaining, duplicate transaction protection, balance queries, entry snapshots, and tamper verification.
- Keep ledger creation and posting free of implicit timestamps so replayed inputs produce identical hashes.
- Add strict Python/native parity through the per-run native host bridge.

### Boundaries
- Ledger Core is an in-memory business-rule primitive, not a bank-grade database or payment processor.
- Persistence, authentication, authorization, signatures, external audit storage, and regulatory compliance remain host-application responsibilities.

## 2.7.1 - 2026-06-13

### Native Data Acceleration
- Implement `std.data.where`, `std.data.project`, and `std.data.sum` directly in the C VM.
- Preserve Python VM behavior for comparison operators, `contains`, missing fields, mixed integer/float sums, and non-map rows.
- Align native `None` output with the Python VM while extending strict output parity coverage.
- Add native transform edge-case parity coverage with Python fallback disabled.
- Add `benchmarks/native_data_transform_benchmark.py` for repeatable Python/C engine comparisons.
- Improve the representative where+project+sum workload from about 1.33x native speedup before this patch to about 3.2-4.1x, reaching roughly 8.3-10.8 million rows/second on the development machine.

### Boundaries
- JSONL/CSV parsing, stream handles, SQLite, sandbox path checks, deadlines, and cleanup remain managed by the host bridge.

## 2.7.0 - 2026-06-13

### Native Stdlib Parity
- Add a per-run native host bridge so the C VM can call stateful and optional stdlib services without falling back to the Python VM.
- Add strict native parity for Decimal-backed `std.money`.
- Add strict native parity for bounded JSONL/CSV streams and parameterized SQLite in `std.data`.
- Preserve data batch, record, stream, query, write, path, and time limits in native execution.
- Close native data streams and SQLite handles at the end of every run.
- Enforce storage denial inside the C VM for the finance sandbox profile.
- Stop forcing finance and data sandbox profiles to the Python VM.
- Add native money, JSONL, and SQLite lifecycle tests with fallback disabled.

### Deferred
- Native debugger, event dispatch, and deterministic record/replay parity.
- Native implementations for external database adapters and distributed data execution.

## 2.6.0 - 2026-06-13

### Data Processing Core
- Add bounded streaming readers for JSONL and CSV.
- Add batch projection, filtering, field summation, stream inspection, cancellation, and close operations.
- Add parameterized SQLite query/execute APIs with row limits and read-only query enforcement.
- Add persistent SQLite handles, including in-memory databases for transactional rule workflows.
- Add `--sandbox=data` and CLI controls for batch size, record size, open streams, query rows, and explicit data-write permission.
- Route data-core programs through the Python VM until native data parity is implemented.
- Add fixtures, core tests, an example program, and a 10K/100K/1M-capable benchmark.

### Safety
- Batch size and query results are bounded to provide backpressure.
- Runtime time limits are checked during stream reads and database operations.
- SQL values are bound through placeholders rather than string interpolation.

### Deferred
- Native C VM parity for `std.data`.
- External PostgreSQL/ClickHouse adapters.
- Parallel workers and distributed execution.

## 2.5.0 - 2026-06-13

### Production Scripting Core
- Add Decimal-backed `std.money` helpers for exact money-style rules.
- Add top-level money aliases such as `money(...)`, `money_add(...)`, and `money_format(...)`.
- Add `--sandbox=finance` for stricter rule-script execution: no ask/wait/storage/save/network and Python VM routing until native sandbox parity is complete.
- Teach the IR compiler path to lower money stdlib calls without treating them as user skills.
- Add core tests for money precision and finance sandbox enforcement.

### Deferred
- Native C VM parity for `std.money`.
- A full language-level `decimal` literal/type syntax.
- Audit-log and immutable ledger primitives.

## 2.4.0 - 2026-06-13

### Native Core Parity
- Add `tests/native` as the strict Python VM vs native C VM parity gate for the stable language core.
- Fix the Python-to-C VM bridge so current native extensions can run without accidental `host=` keyword failures.
- Add native C support for compiled `range(...)` calls used by stable `for` loops.
- Report native parity as `stable-core` while keeping debugger, event, and record/replay fallback status explicit.
- Build the native extension in CI before running native parity tests.

### Stable
- Bump package and runtime version to `2.4.0`.
- Keep `frameworks.mellow_ui` in the release verification set.

### Deferred
- Native debugger pause/inspect parity.
- Native event handler execution parity.
- Native record/replay parity.

## 2.3.5 - 2026-06-13

### Release Polish
- Treat `tests/core` as the stable release gate.
- Limit GitHub Actions to stable core tests while legacy and experimental suites are being triaged.
- Add stable-core documentation and a release checklist.
- Add a Windows native build helper script for the optional C extension.
- Make `frameworks.mellow_ui` installable and runnable as a Python framework package.
- Add JSON rendering support for Mellow UI framework previews/tools.

### Deferred
- Full legacy and experimental test suite cleanup.
- Broader native VM parity beyond core execution.
- Packaging binary artifacts for release downloads.

## 2.3.4 - 2026-06-04

### Stable
- Added `tests/core` as the stable language gate.
- Improved `mellow doctor` output and optional feature reporting.
- Split optional dependencies out of the default install.
- Fixed core language regressions around functions, `range(...)`, and indexed values.
- Fixed Windows native VM build issues in source.

### Experimental
- Native VM can run core examples through `--engine=c`, but the Python VM remains needed for record/replay, event handlers, and debugger parity.
- Agent, MMG, desktop, registry, and full legacy test surfaces are not release gates yet.
