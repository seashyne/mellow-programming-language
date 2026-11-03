"""IR value types shared by every optimization pass."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ...ir import IRInstruction


_CONST_TOP = object()


@dataclass(frozen=True)
class BasicBlock:
    id: int
    label: str
    start: int
    end: int
    instructions: List[IRInstruction]
    predecessors: List[str] = field(default_factory=list)
    successors: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ControlFlowGraph:
    entry_label: str
    blocks: List[BasicBlock]


@dataclass(frozen=True)
class DominatorTree:
    entry_label: str
    dominators: Dict[str, List[str]]
    immediate_dominators: Dict[str, Optional[str]]
    tree_children: Dict[str, List[str]]
    back_edges: List[Tuple[str, str]] = field(default_factory=list)
    natural_loops: Dict[str, List[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class DefUseInfo:
    defs_by_var: Dict[str, List[int]]
    uses_by_var: Dict[str, List[int]]
    ssa_names_by_var: Dict[str, List[str]]
    def_to_uses: Dict[str, List[int]]


@dataclass(frozen=True)
class PhiNode:
    block_label: str
    variable: str
    version: str
    sources: Dict[str, Optional[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class SSAProgram:
    entry_label: str
    phi_nodes: Dict[str, List[PhiNode]]
    instruction_defs: Dict[int, List[str]]
    instruction_uses: Dict[int, List[str]]
    versions_by_var: Dict[str, List[str]]
    rename_order: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class OptimizationSummary:
    passes: List[str]
    instructions_before: int
    instructions_after: int
    labels_removed: int = 0
    constants_folded: int = 0
    constants_propagated: int = 0
    jumps_simplified: int = 0
    branches_pruned: int = 0
    dead_instructions_removed: int = 0
    lvn_rewrites: int = 0
    gvn_rewrites: int = 0
    loop_rewrites: int = 0
    blocks_before: int = 0
    blocks_after: int = 0
    ssa_versions: int = 0
    phi_nodes: int = 0
    sccp_constants: int = 0
    sccp_branches_pruned: int = 0
    loop_invariants_hoisted: int = 0


@dataclass
class _StackValue:
    const: Any = _CONST_TOP
    expr: Any = None
    start: int = -1
