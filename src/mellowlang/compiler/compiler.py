from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, is_dataclass
from threading import RLock
from typing import Any, List, Optional

from ..error_core import MellowLangRuntimeError
from ..ir import IRProgram
from ..parser import parse_program
from ..ast import Call, GetModuleExpr, GetModuleStmt, IfGroup, Index, LoopCount, LoopForEach, LoopForMap, LoopForRange, LoopWhile, RepeatUntil, TryStmt
from .bytecode_backend import BytecodeBackend
from .ir_lowering import IRLowerer, UnsupportedLoweringError
from .optimizer import ControlFlowGraph, DefUseInfo, DominatorTree, IROptimizer, OptimizationSummary, SSAProgram
from .legacy import Compiler as _LegacyCompiler


_COMPILE_CACHE_MAX = 128
_COMPILE_CACHE: "OrderedDict[tuple[str, str | None, bool], CompiledProgram]" = OrderedDict()
_COMPILE_CACHE_LOCK = RLock()
_COMPILE_CACHE_HITS = 0
_COMPILE_CACHE_MISSES = 0


@dataclass(frozen=True)
class CompiledProgram:
    """Compiled Mellow program.

    The stable runtime still executes bytecode, but the compiler now produces and
    retains the full AST -> IR -> bytecode pipeline metadata so tooling can inspect
    or optimize it later.
    """

    bytecode: List[tuple]
    func_table: dict | None = None
    event_table: dict | None = None
    filename: Optional[str] = None
    source_lines: Optional[List[str]] = None
    line_map: Optional[List[int]] = None
    col_map: Optional[List[int]] = None
    end_line_map: Optional[List[int]] = None
    end_col_map: Optional[List[int]] = None
    span_map: Optional[List[dict]] = None
    ast: Any = None
    ir: IRProgram | None = None
    optimized_ir: IRProgram | None = None
    cfg: ControlFlowGraph | None = None
    optimized_cfg: ControlFlowGraph | None = None
    optimization: OptimizationSummary | None = None
    dominator_tree: DominatorTree | None = None
    optimized_dominator_tree: DominatorTree | None = None
    def_use: DefUseInfo | None = None
    optimized_def_use: DefUseInfo | None = None
    ssa_program: SSAProgram | None = None
    optimized_ssa_program: SSAProgram | None = None
    pipeline: str = "legacy"


class Compiler:
    def __init__(self) -> None:
        self._legacy = _LegacyCompiler()

    def compile(self, source: str, *, filename: str | None = None, optimize: bool = True) -> CompiledProgram:
        global _COMPILE_CACHE_HITS, _COMPILE_CACHE_MISSES
        cache_key = (source, filename, bool(optimize))
        with _COMPILE_CACHE_LOCK:
            cached = _COMPILE_CACHE.get(cache_key)
            if cached is not None:
                _COMPILE_CACHE.move_to_end(cache_key)
                _COMPILE_CACHE_HITS += 1
                return cached
            _COMPILE_CACHE_MISSES += 1

        program = self._compile_uncached(source, filename=filename, optimize=optimize)
        with _COMPILE_CACHE_LOCK:
            _COMPILE_CACHE[cache_key] = program
            _COMPILE_CACHE.move_to_end(cache_key)
            while len(_COMPILE_CACHE) > _COMPILE_CACHE_MAX:
                _COMPILE_CACHE.popitem(last=False)
        return program

    @staticmethod
    def clear_cache() -> None:
        global _COMPILE_CACHE_HITS, _COMPILE_CACHE_MISSES
        with _COMPILE_CACHE_LOCK:
            _COMPILE_CACHE.clear()
            _COMPILE_CACHE_HITS = 0
            _COMPILE_CACHE_MISSES = 0

    @staticmethod
    def cache_info() -> dict[str, int]:
        with _COMPILE_CACHE_LOCK:
            return {
                "size": len(_COMPILE_CACHE),
                "max_size": _COMPILE_CACHE_MAX,
                "hits": _COMPILE_CACHE_HITS,
                "misses": _COMPILE_CACHE_MISSES,
            }

    def _compile_uncached(self, source: str, *, filename: str | None = None, optimize: bool = True) -> CompiledProgram:
        lines = source.splitlines()
        ast = None
        ir = None
        optimized_ir = None
        cfg = None
        optimized_cfg = None
        optimization = None
        dominator_tree = None
        optimized_dominator_tree = None
        def_use = None
        optimized_def_use = None
        ssa_program = None
        optimized_ssa_program = None
        try:
            ast = parse_program(lines, filename=filename)
            ir = IRLowerer(filename=filename).lower(ast)
            opt = IROptimizer()
            cfg = opt.build_cfg(ir.instructions)
            dominator_tree = opt.build_dominator_tree(cfg)
            def_use = opt.build_def_use(ir.instructions)
            ssa_program = opt.build_ssa(cfg, dominator_tree, ir.instructions)
            optimized_ir = ir
            optimized_cfg = cfg
            optimized_dominator_tree = dominator_tree
            optimized_def_use = def_use
            optimized_ssa_program = ssa_program
            # The optimizer is still experimental. Its constant propagation can
            # corrupt indexed expressions such as xs[1], so keep those on the
            # unoptimized IR path until that pass is fixed.
            use_optimizer = (
                bool(optimize)
                and not _ast_contains(ast, Index)
                and not _ast_contains_control_flow(ast)
                and not _ast_contains_stateful_stdlib_call(ast)
            )
            if use_optimizer:
                optimized_ir, optimization = opt.optimize(ir)
                optimized_cfg = opt.build_cfg(optimized_ir.instructions)
                optimized_dominator_tree = opt.build_dominator_tree(optimized_cfg)
                optimized_def_use = opt.build_def_use(optimized_ir.instructions)
                optimized_ssa_program = opt.build_ssa(optimized_cfg, optimized_dominator_tree, optimized_ir.instructions)
            bundle = BytecodeBackend().lower(optimized_ir)
            return CompiledProgram(
                bytecode=bundle.bytecode,
                func_table=bundle.func_table,
                event_table=bundle.event_table,
                filename=filename,
                source_lines=lines,
                line_map=bundle.line_map,
                col_map=bundle.col_map,
                end_line_map=bundle.end_line_map,
                end_col_map=bundle.end_col_map,
                span_map=bundle.span_map,
                ast=ast,
                ir=ir,
                optimized_ir=optimized_ir,
                cfg=cfg,
                optimized_cfg=optimized_cfg,
                optimization=optimization,
                dominator_tree=dominator_tree,
                optimized_dominator_tree=optimized_dominator_tree,
                def_use=def_use,
                optimized_def_use=optimized_def_use,
                ssa_program=ssa_program,
                optimized_ssa_program=optimized_ssa_program,
                pipeline="ast-ir-opt-bytecode" if use_optimizer else "ast-ir-bytecode",
            )
        except UnsupportedLoweringError:
            # Fall through to the battle-tested compiler so existing language
            # features keep working while the new IR pipeline expands.
            pass
        except MellowLangRuntimeError:
            raise
        except Exception:
            # The IR/backend path is still expanding. If it cannot lower or
            # emit a valid program yet, preserve stable language behavior by
            # falling back to the legacy bytecode compiler below.
            pass

        try:
            bytecode = self._legacy.compile(lines, filename=filename)
        except MellowLangRuntimeError:
            raise
        except Exception as e:
            raise MellowLangRuntimeError('COMPILER', str(e), None, filename=filename)
        return CompiledProgram(
            bytecode=bytecode,
            func_table=getattr(self._legacy, "functions", None),
            event_table=getattr(self._legacy, "events", None),
            filename=filename,
            source_lines=lines,
            line_map=getattr(self._legacy, 'line_map', None),
            col_map=getattr(self._legacy, 'col_map', None),
            end_line_map=getattr(self._legacy, 'line_map', None),
            end_col_map=getattr(self._legacy, 'col_map', None),
            span_map=None,
            ast=ast,
            ir=ir,
            optimized_ir=optimized_ir,
            cfg=cfg,
            optimized_cfg=optimized_cfg,
            optimization=optimization,
            dominator_tree=dominator_tree,
            optimized_dominator_tree=optimized_dominator_tree,
            def_use=def_use,
            optimized_def_use=optimized_def_use,
            ssa_program=ssa_program,
            optimized_ssa_program=optimized_ssa_program,
            pipeline="legacy",
        )


def _ast_contains(node: Any, node_type: type) -> bool:
    if isinstance(node, node_type):
        return True
    if is_dataclass(node):
        return any(_ast_contains(value, node_type) for value in node.__dict__.values())
    if isinstance(node, (list, tuple)):
        return any(_ast_contains(item, node_type) for item in node)
    if isinstance(node, dict):
        return any(_ast_contains(item, node_type) for item in node.values())
    return False


def _ast_contains_stateful_stdlib_call(node: Any) -> bool:
    if isinstance(node, Call):
        name = str(node.name).lower()
        return name.startswith("money") or name.startswith("data") or name.startswith("ledger")
    if isinstance(node, (GetModuleExpr, GetModuleStmt)):
        return str(node.module).lower() in {"money", "data", "ledger"}
    if is_dataclass(node):
        return any(_ast_contains_stateful_stdlib_call(value) for value in node.__dict__.values())
    if isinstance(node, (list, tuple)):
        return any(_ast_contains_stateful_stdlib_call(item) for item in node)
    if isinstance(node, dict):
        return any(_ast_contains_stateful_stdlib_call(item) for item in node.values())
    return False


def _ast_contains_control_flow(node: Any) -> bool:
    control_nodes = (IfGroup, LoopWhile, LoopForEach, LoopForMap, LoopForRange, LoopCount, RepeatUntil, TryStmt)
    if isinstance(node, control_nodes):
        return True
    if is_dataclass(node):
        return any(_ast_contains_control_flow(value) for value in node.__dict__.values())
    if isinstance(node, (list, tuple)):
        return any(_ast_contains_control_flow(item) for item in node)
    if isinstance(node, dict):
        return any(_ast_contains_control_flow(item) for item in node.values())
    return False
